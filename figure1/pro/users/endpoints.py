import logging
import os

from celery.exceptions import TimeoutError
from flask import abort
from flask import Blueprint
from flask import current_app
from flask import request
from flask.json import jsonify
from flask_jwt_extended import jwt_required
from jsonschema import ValidationError
from pydantic import validate_email as pydantic_validate_email

from figure1.core import es
from figure1.common.models.validator import Validate
from figure1.common.types import UpdateUserModel
from figure1.common.types.screen_constants import UNKNOWN_SCREEN
from figure1.common.utils import execute_on_return
from figure1.common.utils import s3_utils
from figure1.configuration import es_settings
from figure1.common.activities.user_profile_activities import update_all_activities_task
from figure1.exceptions import FirebaseError
from figure1.exceptions import MFYNotFound
from figure1.exceptions import UserError
from figure1.exceptions import UsernameNotAllowed
from figure1.exceptions.iterable import IterableException
from figure1.exceptions.user import GroupFilterUUIDNotFound
from figure1.pro.users.domain import admin_create_user_internal
from figure1.pro.users.domain import admin_update_user_internal
from figure1.pro.users.domain import check_usernames
from figure1.pro.users.domain import create_anonymous_user
from figure1.pro.users.domain import create_user_internal
from figure1.pro.users.domain import delete_user
from figure1.pro.users.domain import delete_user_profile
from figure1.pro.users.domain import follow_user
from figure1.pro.users.domain import force_user_sync
from figure1.pro.users.domain import generate_password_reset_link
from figure1.pro.users.domain import generate_email_login_link
from figure1.pro.users.domain import get_user_group_filter_by_uuid
from figure1.pro.users.domain import get_user_potential_group
from figure1.pro.users.domain import invite_colleagues
from figure1.pro.users.domain import link_existing_anonymous_user
from figure1.pro.users.domain import refresh_user_saved_cases
from figure1.pro.users.domain import reset_password
from figure1.pro.users.domain import send_login_link
from figure1.pro.users.domain import rewrite_user_metadata
from figure1.pro.users.domain import set_user_uid
from figure1.pro.users.domain import sync_elasticsearch
from figure1.pro.users.domain import sync_public_profile
from figure1.pro.users.domain import unfollow_user
from figure1.pro.users.domain import update_background_image
from figure1.pro.users.domain import update_user_avatar_internal
from figure1.pro.users.domain import update_user_internal
from figure1.pro.users.domain import user_auth_check
from figure1.pro.users.model_methods import get_user_by_email_case_insensitive
from figure1.pro.users.model_methods import get_user_by_username_case_insensitive
from figure1.common.iterable.api import IterableAPI

search_index = es_settings.users_alias
bp = Blueprint('pro_users_endpoint', __name__)
logger = logging.getLogger(__name__)


@bp.errorhandler(ValidationError)
def user_handle_validation_error(e):
    logger.exception("Schema validation failed")
    return jsonify(dict(message="Schema validation failed", validator=e.schema)), 422


@bp.errorhandler(UsernameNotAllowed)
def username_not_allowed(e):
    logger.exception("Username not allowed")
    return jsonify(dict=e.as_dict()), e.rc


@bp.errorhandler(UserError)
def handle_user_error(e):
    logger.exception("%s", e.msg)
    return jsonify(e.as_dict()), e.rc


@bp.errorhandler(FirebaseError)
def handle_firebase_error(e):
    logger.exception("%s", e.msg)
    return jsonify(e.as_dict()), e.rc


@bp.errorhandler(MFYNotFound)
def handle_mfy_not_found(e):
    logger.exception("%s", e.msg)
    return (jsonify(e.as_dict())), e.rc


@bp.errorhandler(TimeoutError)
def handle_celery_timeout_error(e):
    logger.exception("Task timed out", e.msg)
    return jsonify(dict(error="Task timed out")), 408


@bp.errorhandler(IterableException)
def handle_iterable_errors(e):
    logger.exception("%s", e.msg)
    return (jsonify(e.as_dict())), e.rc


@bp.errorhandler(GroupFilterUUIDNotFound)
def handle_group_filter_not_found(e):
    logger.exception("%s", e.msg)
    return (jsonify(e.as_dict())), e.rc


@bp.route('/user/activity/resync', methods=['GET'])
@jwt_required()
def force_user_activity_sync():
    """
    Force the users activity to resync, this should only be necessary when it is incorrect.
    Running without a user_uuid executes on all users and wipes each one. The purge flag does this
    with a single user, purge is set to false by default for a single user.

    ---
    tags:
      - users
    produces:
      - application/json
    parameters:
      - name: user_uuid
        in: query
        type: string
        required: false
    responses:
      default:
        description: Unexpected Failure
      '404':
        description: User ID was not found
      '422':
        description: A semantic error was found in the request.
      '200':
        description: OK
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    user_uuid = request.args.get('user_uuid')
    update_all_activities_task.delay(user_uuid=user_uuid, purge=True)
    return jsonify({}), 200


@bp.route('/user/<user_uid>', methods=['DELETE'])
@jwt_required()
def do_delete_user(user_uid):
    """
    Delete records from a users profile

    ---
    tags:
     - users
    produces:
      - application/json
    parameters:
      - name: user_uid
        in: path
        type: string
        required: true
    responses:
      default:
        description: Unexpected Failure
      '404':
        description: User ID was not found
      '422':
        description: A semantic error was found in the request.
      '200':
        description: OK
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    delete_user(user_uid)
    return jsonify({}), 200


@bp.route('/ungated/user/create', methods=['POST'])
@jwt_required()
def do_create_anonymous_user_endpoint():
    """
    Creates an anonymous user that is used for tracking ungated content

    ---
    tags:
     - user
    produces:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        schema:
          required:
            - user_uid
          properties:
            user_uid:
              type: string
              required: true
            email:
              type: string
              description: User email - Optional
          example:
            email: test@figure1.com
            user_uid: someuidhere
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: User created
        schema:
          properties:
            userUuid:
              type: string

    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    req = request.json
    user_uid = req.get('user_uid')
    email = req.get('email', None)

    logger.info('Starting email validation from signup service')
    iterable_client = IterableAPI()
    validation_test = iterable_client.validate_registration_email(email=email,
                                                                  first_name=None,
                                                                  last_name=None
                                                                  )
    
    if validation_test['status'] == 406:
        logger.info('Reject registration from signup service')
        return jsonify({'error': validation_test}), 406
    
    if not user_uid:
        abort(400, "No user_uid passed")
    resp = create_anonymous_user(user_uid=user_uid, email=email)
    return jsonify(resp)


@bp.route('/admin/user/create', methods=["POST"])
@jwt_required()
def admin_create_user():
    """
    Create a user from the admin tool. This path is slightly different from the normal path because we have to
    create the UID ourselves.

    ---
    tags:
     - admin
    produces:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        schema:
          required:
            - username
            - email
          properties:
            userType:
              type: string
              default: 'USER'
              enum: ['USER',
               'FIGURE1_100',
               'FIGURE1_FRIENDS',
               'FIGURE1_INTERNAL',
               'FIGURE1_OFFICIAL',
               'FIGURE1_PAID_CONTRIBUTOR',
               'FIGURE1_EDITORIAL_PARTNER',
               'FIGURE1_EDITORIAL_SUBSCRIBER',
               'FIGURE1_SPONSORED',
               'FIGURE1_INSTITUTIONAL']
            email:
              type: string
              description: The email of the user to create
            username:
              type: string
              description: The username to create
          example:
            email: test@figure1.com
            username: testuser
            userType: USER
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: User created
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    req = request.json
    if get_user_by_email_case_insensitive(req.get("email")):
        return abort(409, 'Email is already in use')
    if get_user_by_username_case_insensitive(req.get("username")):
        return abort(409, 'Username already in use')
    
    logger.info('Starting email validation from signup service')
    iterable_client = IterableAPI()
    validation_test = iterable_client.validate_registration_email(email=req.get("email"),
                                                                  first_name=None,
                                                                  last_name=None
                                                                  )
    
    if validation_test['status'] == 406:
        logger.info('Reject registration from signup service')
        return jsonify({'error': validation_test}), 406

    r = admin_create_user_internal(email=req.get("email"), username=req.get("username"), user_type=req.get("userType"))
    return jsonify(r), 200


@bp.route('/user/create', methods=["POST"])
@jwt_required()
def create_user():
    """
    Create a user
    ---
    tags:
     - users
    produces:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        schema:
          required:
            - email
            - user_uid
          properties:
            user_uid:
              type: string
              description: The user uid of the user to create
            email:
              type: string
              description: The email of the user to create
            first_name:
              type: string
              description: The first name of the user to create - optional
            last_name:
              type: string
              description: The last name of the user to create - optional
            profession_uuid:
              type: string
              description: Tree uuid of user's profession - optional
            country_uuid:
              type: string
              description: country uuid of user's country - optional
            anonymous_uid:
              type: string
              description: anonymous uid for a user if exists - optional
            group_uuid:
              type: string
              description: group uuid - optional
            npi_number:
              type: int
              description: NPI number for a user, verifies on creation.
          example:
            user_uid: <uid string>
            email: test@figure1.com
            country_uuid: <uuid string>
            anonymous_uid: <uid string>
            group_uuid: <uuid string>

    responses:
      default:
        description: Unexpected Failure
      '200':
        description: User created
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """

    if 'user_uid' not in request.json:
        return abort(400, 'missing user_uid')
    if 'email' not in request.json:
        return abort(400, 'missing email')

    user_uid = request.json.get('user_uid')
    email = request.json.get('email').lower()
    first_name = request.json.get('first_name')
    last_name = request.json.get('last_name')
    
    logger.info('Starting email validation from signup service')
    iterable_client = IterableAPI()
    validation_test = iterable_client.validate_registration_email(email=email,
                                                                  first_name=first_name,
                                                                  last_name=last_name
                                                                  )
    
    if validation_test['status'] == 406:
        logger.info('Reject registration from signup service')
        return jsonify({'error': validation_test}), 406
    
    country_uuid = request.json.get('country_uuid')
    anonymous_uid = request.json.get('anonymous_uid')
    group_uuid = request.json.get('group_uuid')
    # optional only used for tracking purposes
    screen_id = request.json.get('screen_id', UNKNOWN_SCREEN)
    user_npi = request.json.get('npi_number', 0)
    profession_uuid = request.json.get('profession_uuid', None)
    res = create_user_internal(user_uid=user_uid,
                               email=email,
                               first_name=first_name,
                               last_name=last_name,
                               profession_uuid=profession_uuid,
                               country_uuid=country_uuid,
                               anonymous_uid=anonymous_uid,
                               group_uuid=group_uuid,
                               screen_id=screen_id,
                               user_npi=user_npi)

    if 'error' in res:
        code = res.get('code', 500)
        return jsonify({'error': res['error']}), code
    return jsonify(res), 200


@bp.route('/user/ungated/anonymous_user/existing_user', methods=["POST"])
@jwt_required()
def link_anonymous_user_with_real_user():
    """
    when a user completes an ungated CME and signs in, they'll be able to find their CME progress in the CME center.
    ---
    tags:
     - users
    produces:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        schema:
          required:
            - anonymous_uid
            - user_uid
          properties:
            anonymous_uid:
              type: string
              description: The user uid of the anonymous user
            user_uid:
              type: string
              description: The user uid of the real user
          example:
            anonymous_uid: <uid string>
            user_uid: <uid string>
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: User created
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """

    if 'user_uid' not in request.json:
        return abort(400, 'missing user_uid')
    if 'anonymous_uid' not in request.json:
        return abort(400, 'missing anonymous_uid')

    user_uid = request.json.get('user_uid')
    anonymous_uid = request.json.get('anonymous_uid')
    res = link_existing_anonymous_user(user_uid=user_uid, anonymous_uid=anonymous_uid)
    return jsonify(res), 200


@bp.route('/user/invite_users', methods=["POST"])
@jwt_required()
def invite_users():
    """
    invite users to join figure1
    ---
    tags:
     - users
    produces:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        schema:
          required:
            - user_uid
            - email
          properties:
            user_uid:
              type: string
              description: The user uid of the user inviting others
            emails:
              type: array
              description: The emails of the users to send invitation to join figure1
          example:
            user_uid: rVfnkWNMQmYWZ7T5bojk4UiK3ek2
            emails: ['helloworld1@figure1.com', 'helloworld2@figure1.com']

    responses:
      default:
        description: Unexpected Failure
      '200':
        description: invite sent
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """

    if 'user_uid' not in request.json:
        return abort(400, 'missing user_uid')
    if 'emails' not in request.json:
        return abort(400, 'missing email')

    user_uid = request.json.get('user_uid')
    emails = request.json.get('emails')
    if isinstance(emails, list):
        res = invite_colleagues(user_uid=user_uid, emails=emails)
        return jsonify(res), 200
    else:
        abort(422, "emails is not a list")


@bp.route('/user/<user_uid>/profile', methods=["DELETE"])
@jwt_required()
def delete_user_profile_data(user_uid):
    """
    Delete records from a users profile

    ---
    tags:
     - users
    produces:
      - application/json
    parameters:
      - name: user_uid
        in: path
        type: string
        required: true
      - name: body
        in: body
        required: true
        schema:
          properties:
            interests:
              type: array
              items: string
              description: User interests, as specialty_tree_uuid values
            experience:
              type: array
              items: string
              description: List of user experience uuids to delete
            affiliations:
              type: array
              items: string
              description: List of user affiliation uuids to delete
            education:
              type: array
              items: string
              description: List of user education uuids to delete

          example:
            interests: ['d13dafd0-bf4e-4386-9186-3ef13505b9e8']
            experience: ['uuid']
            education: ['uuid']
            affiliations: ['uuid']
    responses:
      default:
        description: Unexpected Failure
      '404':
        description: User ID was not found
      '422':
        description: A semantic error was found in the request.
      '200':
        description: OK
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """

    res = delete_user_profile(user_uid=user_uid, data=request.json)
    if 'error' in res:
        code = res.get('code', 500)
        return jsonify({'error': res['error']}), code

    return jsonify(res), 200


@bp.route('/admin/user/<user_uid>', methods=["POST"])
@jwt_required()
def admin_update_user(user_uid=None):
    """
    This endpoint is a superset of the normal update user endpoint, the additional value this endpoint takes is the
    user_type enum. Everything else is passed into the update_user endpoint.
    userType is used to change the type of the user. Normally this would be used for upgrading a normal user to
    another type of user, but works the other way too.

    ---
    tags:
     - admin
    produces:
      - application/json
    parameters:
      - name: user_uid
        in: path
        type: string
        required: true
      - name: body
        in: body
        required: true
        schema:
          id: updateUserDoc
      - name: force_synchronous
        in: query
        type: boolean
        required: false
        description: Forces the return to be synchronous
    responses:
      default:
        description: Unexpected Failure
      '404':
        description: User ID was not found
      '422':
        description: A semantic error was found in the request.
      '200':
        description: OK
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    user_type = request.json.pop("userType")
    force_synchronous = request.args.get('force_synchronous') == 'true'

    update = UpdateUserModel.parse_obj(request.json)

    res = admin_update_user_internal(user_type=user_type, user_uid=user_uid, user_update=update)
    task = res.pop('task')
    return execute_on_return(task, synchronous=force_synchronous, response=res)


@bp.route('/user/<user_uid>', methods=["POST"])
@jwt_required()
def update_user(user_uid):
    """
    Update a user
    All fields are optional, if there is no experience for example, then either do not send it or send an empty array.

    For experience, education, and affiliations, they accept only lists of maps. For each map, if the uuid is included,
    it is considered an update. If there is no uuid included, a new row is appended. Note that including an invalid UUID
    will just cause a failure, it will not create a new entry. If there is no end year included, then the assumption
     is that this is a current event.
     Each map must have the description field and the startYear field, the other fields are optional.

    Specialties and interests both take lists of tree_uuids and are included as part of the MFY feed.
    ---
    tags:
     - users
    produces:
      - application/json
    parameters:
      - name: user_uid
        in: path
        type: string
        required: true
      - name: force_synchronous
        in: query
        type: boolean
        required: false
        description: Forces the return to be synchronous
      - name: body
        in: body
        required: true
        schema:
          id: updateUserDoc
          properties:
            userType:
              type: string
              description: This is ignored unless it is passed through the admin update user endpoint.
              default: 'USER'
              enum: ['USER',
               'FIGURE1_100',
               'FIGURE1_FRIENDS',
               'FIGURE1_INTERNAL',
               'FIGURE1_OFFICIAL',
               'FIGURE1_PAID_CONTRIBUTOR',
               'FIGURE1_EDITORIAL_PARTNER',
               'FIGURE1_EDITORIAL_SUBSCRIBER',
               'FIGURE1_SPONSORED',
               'FIGURE1_INSTITUTIONAL']
            caseCommentDisplayName:
              type: string
              description: Custom name to display in cases/comments made by this user - takes place of specialty
            graduationDate:
              type: string
              description: graduation date for the user
            profileDisplayName:
              type: string
              description: Display label for the profile - takes the place of specialty/subspecialty
            profileLink:
              type: string
              description: External link in profile, not available to all users
            profileLinkText:
              type: string
              description: Text used to describe the profile link
            caseFeedEnabled:
              type: bool
              description: Show case feed only if true, otherwise show about + case feed
            caseFeedTitle:
              type: string
              description: Only shown if case feed is enabled - title for the case feed
            disclosureText:
              type: string
              description: Disclosure text, only available to specific user types
            sponsoredContentEnabled:
              type: bool
              description: Determines if a user is served sponsored content
            userBio:
              type: string
              description: Short user bio
            userPracticeLocation:
              type: string
              description: Location of user practice
            userPracticeHospital:
              type: string
              description: Hospital of user practice
            firstName:
              type: string
              description: Users first name
            lastName:
              type: string
              description: Users last name
            userDisplayName:
              type: string
              description: Preferred name to display
            username:
              type: string
              description: The new username for the user
            email:
              type: string
              description: The new email for the user
            specialties:
              type: array
              items: string
              description: The secondary specialties of the user, as tree_uuid values
            primarySpecialty:
              type: string
              description: Primary specialty for a user as treeUuid - displays for comments/profile etc
            userCustomSpecialty:
              type: string
              description: Used to allow a user to enter a specialty if they cannot find a match
            userCustomSchool:
              type: string
              description: Used to allow a user to enter a school manually if they cannot find a match
            interests:
              type: array
              items: string
              description: User interests, as specialty_tree_uuid values
            experience:
              type: array
              items: dict
              description: List of user experiences, experienceUuid should only be included for updates
            affiliations:
              type: array
              items: dict
              description: List of user affiliations, affiliationUuid should only be included for updates
            education:
              type: array
              items: dict
              description: List of user education, educationUuid should only be included for updates
            onboardingCompleted:
              type: boolean
              description: True if the user has completed onboarding, otherwise False
            onboardingInterestsCompleted:
              type: boolean
              description: True if the user has completed setting interests in onboarding, otherwise False

          example:
            userType: USER
            firstName: My First Name
            lastName: My Last Name
            profileLink: https://google.ca
            profileLinkText: This links to google
            disclosureText: subdermal application only - institutional users only
            caseCommentDisplayName: Show this in comments and case uploads - institutional users only
            profileDisplayName: Show this in the profile page replacing the specialty/profession
            caseFeedEnabled: true
            caseFeedTitle: This is a case feed
            username: figure1user
            sponsoredContentEnabled: False
            userBio: Something about me
            userPracticeLocation: Free-form text - should be a city or region
            userPracticeHospital: Free-form text - should be name of hospital
            userDisplayName: Public name displayed on comments and posts
            interests: ['d13dafd0-bf4e-4386-9186-3ef13505b9e8']
            specialties: ['d13dafd0-bf4e-4386-9186-3ef13505b9e8', 'c1dddaa0-0e47-4c2c-84f1-4843c3abd99a']
            primarySpecialty: 'treeUuid'
            experience: [{'location': 'free-form',
                          'description': 'free-form',
                          'startYear': 2011,
                          'endYear': 2011,
                          'experienceUuid': 'existing experience uuid'}]
            education: [{'location': 'free-form',
                          'description': 'free-form',
                          'startYear': 2011,
                          'educationUuid': "0000"}]
            affiliations: [{'location': 'free-form',
                          'description': 'free-form',
                          'startYear': 2011,
                          'endYear':2011,
                          'affiliationUuid': 'UUID of existing affiliation'}]
            onboardingCompleted: True
            onboardingInterestsCompleted: True
            graduationDate: "YYYY-MM-DD"
    responses:
      default:
        description: Unexpected Failure
      '404':
        description: User ID was not found
      '422':
        description: A semantic error was found in the request.
      '200':
        description: OK
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """

    force_synchronous = request.args.get('force_synchronous') == 'true'
    if 'specialties' in request.json and not request.json['specialties']:
        request.json.update({'specialties': []})

    update = UpdateUserModel.parse_obj(request.json)
    res = update_user_internal(user_uid=user_uid, user_update=update)
    if 'error' in res:
        code = res.get('code', 500)
        return jsonify({'error': res['error']}), code

    task = res.pop('task')
    return execute_on_return(task, synchronous=force_synchronous, response=res)


@bp.route('/user/<user_uuid>/sync')
@jwt_required()
def synchronize_public_profile(user_uuid=None):
    """
    This endpoint pushes the backend public user data for a given user_uuid to the userProfileDB
    ---
    tags:
     - users
    produces:
      - application/json
    parameters:
      - name: user_uuid
        in: path
        type: string
        required: true
    responses:
      default:
        description: Unexpected Failure
      '404':
        description: user_uuid was not found
        schema:
          message: string
      '200':
        description: Task created to sychronize user data to userProfileDB
        schema:
          message: string
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    if user_uuid:
        ret = sync_public_profile(user_uuid=user_uuid)
        if 'error' in ret:
            return jsonify(ret), 400
        else:
            return jsonify(ret), 200


@bp.route('/user/<username>/sync/username')
@jwt_required()
def synchronize_public_profile_from_username(username):
    """
    This endpoint pushes the backend public user data for a given username to the userProfileDB
    ---
    tags:
     - users
    produces:
      - application/json
    parameters:
      - name: username
        in: path
        type: string
        required: true
    responses:
      default:
        description: Unexpected Failure
      '404':
        description: Username was not found
        schema:
          message: string
      '200':
        description: Task created to sychronize user data to userProfileDB
        schema:
          message: string
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    ret = sync_public_profile(username=username)
    return jsonify(ret), 200


@bp.route('/user/validate/username/<username>', methods=["GET"])
@jwt_required()
def validate_username(username):
    """
    Determines if a username is valid and available
    ---
    tags:
     - users
    produces:
      - application/json
    parameters:
      - name: username
        in: path
        type: string
        required: true
    responses:
      default:
        description: Unexpected Failure
      '409':
        description: Username is already in use
      '200':
        description: Username is valid
        schema:
          message: string
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    v = Validate()
    v.validate(json_data={"username": username}, json_schema='user')
    check_usernames(username=username)
    if get_user_by_username_case_insensitive(username):
        return abort(409, 'Username is already in use')

    return jsonify(dict(message='Username is valid')), 200


@bp.route('/user/validate/email/<email>', methods=["GET"])
@jwt_required()
def validate_email(email):
    """
    Determines if an email address is valid and available
    ---
    tags:
     - users
    produces:
      - application/json
    parameters:
      - name: email
        in: path
        type: string
        required: true
    responses:
      default:
        description: Unexpected Failure
      '422':
        description: Email format is invalid
      '409':
        description: Email is already in use
      '200':
        description: Email is valid
        schema:
          message: string
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    email = email.lower()
    pydantic_validate_email(email)
    user = get_user_by_email_case_insensitive(email)
    if user:
        return abort(409, 'Email is already in use')

    return jsonify(dict(message='Email is valid')), 200


@bp.route('/admin/user/<user_uid>/background', methods=["POST"])
@jwt_required()
def do_set_background_image(user_uid):
    """
    Uploads a background image for an institutional user
    ---
    tags:
     - admin
    produces:
      - application/json
    parameters:
      - name: user_uid
        in: path
        type: string
        required: true
      - name: picture
        in: formData
        type: file
        required: true
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: OK
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    if 'picture' not in request.files:
        abort(400)

    file = request.files['picture']
    if file.filename == '':
        abort(400)

    temp_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], user_uid)
    r = s3_utils.upload_image_to_s3(file=file, upload_dir=f'users/background_image/{user_uid}', temp_dir=temp_dir)

    if 'error' in r:
        return jsonify({'error': r['error']}), 500
    task = update_background_image(user_uid, r['photo_url'])
    task.apply_async()
    return jsonify({}), 200


@bp.route('/user/<user_uid>/avatar', methods=["POST"])
@jwt_required()
def update_user_avatar(user_uid):
    """
    Uploads and sets an avatar for a user
    ---
    tags:
     - users
    produces:
      - application/json
    parameters:
      - name: user_uid
        in: path
        type: string
        required: true
      - name: picture
        in: formData
        type: file
        required: true
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: OK
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    if 'picture' not in request.files:
        abort(400)

    file = request.files['picture']
    if file.filename == '':
        abort(400)

    temp_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], user_uid)
    r = s3_utils.upload_image_to_s3(file=file, upload_dir=f'users/avatar/{user_uid}', temp_dir=temp_dir)

    if 'error' in r:
        return jsonify({'error': r['error']}), 500
    task = update_user_avatar_internal(user_uid, r['photo_url'])
    task.apply_async()
    return jsonify({}), 200


@bp.route('/user/<user_uid>/follow/sync', methods=["GET"])
@jwt_required()
def do_follow_sync(user_uid):
    """
    Sync user followers and following
    User_uid is the user to be synced
    ---
    tags:
     - disabled
    produces:
      - application/json
    parameters:
      - name: user_uid
        in: path
        type: string
        required: true
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: User Sync task created
        schema:
          message: string
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    return jsonify({}), 200


@bp.route('/user/<user_uid>/follow/<user_uuid>', methods=["GET"])
@jwt_required()
def do_follow_user(user_uid, user_uuid):
    """
    Follow a user
    User_uid is the user who is requesting the follow, user_uuid is the user being followed
    ---
    tags:
     - users
    produces:
      - application/json
    parameters:
      - name: user_uid
        in: path
        type: string
        required: true
      - name: user_uuid
        in: path
        type: string
        required: true
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: User Followed
        schema:
          message: string
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    ret = follow_user(user_uuid=user_uuid, user_uid=user_uid)
    if 'error' in ret:
        return jsonify(ret), 500
    else:
        return jsonify(ret), 200


@bp.route('/user/<user_uid>/unfollow/<user_uuid>', methods=["GET"])
@jwt_required()
def do_unfollow_user(user_uid, user_uuid):
    """
    UnFollow a user
    User_uid is the user who is requesting the unfollow, user_uuid is the user being unfollowed
    ---
    tags:
     - users
    produces:
      - application/json
    parameters:
      - name: user_uid
        in: path
        type: string
        required: true
      - name: user_uuid
        in: path
        type: string
        required: true
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: User Followed
        schema:
          message: string
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    ret = unfollow_user(user_uuid=user_uuid, user_uid=user_uid)
    if 'error' in ret:
        return jsonify(ret), 500
    else:
        return jsonify(ret), 200


@bp.route('/user/auth_check', methods=['POST'])
@jwt_required()
def do_user_auth_check():
    """
    Determines the login path required for a user.
    Determines if a user is an unmigrated legacy user and if so checks login credentials.
    Returns a 'status' indicating how the login should be handled.
    ---
    tags:
     - users
    produces:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        schema:
          properties:
            email:
              type: string
              description: The user's email address
              required: false
            username:
              type: string
              description: The user's username
              required: false
            password:
              type: string
              description: The user's password
              required: true
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: OK
      '404':
        description: User not found
      '500':
        description: Error checking user auth
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    if 'password' not in request.json:
        return abort(400, 'missing password')

    username = request.json.get('username')
    email = request.json.get('email')
    password = request.json.get('password')

    res = user_auth_check(email=email,
                          username=username,
                          password=password)
    return jsonify(res), 200


@bp.route('/admin/user/get_password_reset_link', methods=['POST'])
@jwt_required()
def get_user_password_reset_link_endpoint():
    """
    Returns the password reset link - for admin use only
    If the user is an unmigrated legacy user, creates a firebase auth record first, then returns the link
    ---
    tags:
     - users
    produces:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        schema:
          properties:
            email:
              type: string
              description: The user's email address
              required: false
            username:
              type: string
              description: The user's username
              required: false
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: OK
        resetLink: <>
      '404':
        description: User not found
      '500':
        description: Error resetting password

    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    req = request.json
    resp = generate_password_reset_link(email=req.get("email"), username=req.get("username"))
    return jsonify(resp), 200


@bp.route('/admin/user/get_email_login_link', methods=['POST'])
@jwt_required()
def get_user_email_login_link_endpoint():
    """
    Returns an email login link
    If the user is an unmigrated legacy user, creates a firebase auth record first, then returns the link
    ---
    tags:
     - users
    produces:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        schema:
          properties:
            email:
              type: string
              description: The user's email address
              required: false
            username:
              type: string
              description: The user's username
              required: false
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: OK
        resetLink: <>
      '404':
        description: User not found
      '500':
        description: Error generating login link

    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    req = request.json
    resp = generate_email_login_link(email=req.get("email"), username=req.get("username"))
    return jsonify(resp), 200


@bp.route('/user/password_reset', methods=['POST'])
@jwt_required()
def do_password_reset():
    """
    Send a password reset email
    If the user is an unmigrated legacy user, creates a firebase auth record first.
    ---
    tags:
     - users
    produces:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        schema:
          properties:
            email:
              type: string
              description: The user's email address
              required: false
            username:
              type: string
              description: The user's username
              required: false
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: OK
      '404':
        description: User not found
      '500':
        description: Error sending password reset email
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    username = request.json.get('username')
    email = request.json.get('email')

    res = reset_password(email=email,
                         username=username)
    return jsonify(res), 200


@bp.route('/user/email_login_link', methods=['POST'])
@jwt_required()
def do_generate_email_login_link():
    """
    Send an email login link

    If the user is an unmigrated legacy user, creates a firebase auth record first.
    ---
    tags:
     - users
    produces:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        schema:
          properties:
            email:
              type: string
              description: The user's email address
              required: false
            username:
              type: string
              description: The user's username
              required: false
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: OK
      '404':
        description: User not found
      '500':
        description: Error sending email login link
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    username = request.json.get('username')
    email = request.json.get('email')
    res = send_login_link(email=email, username=username)
    return jsonify(res), 200


@bp.route('/user/legacy/set_user_uid', methods=['POST'])
@jwt_required()
def do_set_user_uid():
    """
    Sets the user_uid for a user
    Only valid for users who are currently missing a user_uid.  Intended for use when migrating legacy users.
    if anonymous_uid found, push the cme anonymous user progress to the legacy user.
    ---
    tags:
     - users
    produces:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        schema:
          properties:
            email:
              type: string
              description: The user's email address
              required: false
            user_uid:
              type: string
              description: The user's username
              required: false
            anonymous_uid:
              type: string
              description: The user uid of the anonymous user - optional
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: OK
      '404':
        description: User not found
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    email = request.json.get('email')
    user_uid = request.json.get('user_uid')
    anonymous_uid = request.json.get('anonymous_uid')

    res = set_user_uid(anonymous_uid=anonymous_uid, email=email, user_uid=user_uid)
    return jsonify(res), 200


@bp.route('/user/<user_uid>/force_sync', methods=['GET'])
@jwt_required()
def force_user_sync_endpoint(user_uid):
    """
    Force a user to sync to firestore
    ---
    tags:
      - users
    produces:
      - application/json
    parameters:
      - name: user_uid
        in: path
        type: string
        description:
        required: true
    responses:
      '200':
        description: Task started
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
      """

    force_user_sync(user_uid=user_uid)
    return jsonify({}), 200


@bp.route('/user/feed/metadata', methods=['GET'])
@jwt_required()
def feed_metadata_sync_endpoint():
    """
    Write user(s) feed metadata
    ---
    tags:
      - users
    produces:
      - application/json
    parameters:
      - name: user_uid
        in: query
        type: string
        description:
        required: false
      - name: username
        in: query
        type: string
        description: username to write feed metadata for
        required: false
      - name: user_type
        in: query
        type: string
        description: Write feed metadata for everyone in these user types
        required: false
    responses:
      '200':
        description: Task started
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
      """
    user_uid = request.args.get("user_uid")
    username = request.args.get("username")
    user_type = request.args.get("user_type")
    rewrite_user_metadata(user_uid=user_uid, username=username, user_type=user_type)
    return jsonify({})


@bp.route('/user/savedcase/sync', methods=['GET'])
@jwt_required()
def refresh_saved_cases_endpoint():
    """
    Trigger a refresh of a users saved cases, not passing a user means sync all cases.
    ---
    tags:
      - users
    produces:
      - application/json
    parameters:
      - name: user_uuid
        in: query
        type: string
        description:
        required: false

    responses:
      '200':
        description: Task started
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
      """
    user_uuid = request.args.get("user_uuid")
    refresh_user_saved_cases(user_uuid=user_uuid)
    return jsonify({})


@bp.route("/user/<user_uid>", methods=['GET'])
@jwt_required()
def get_search_user(user_uid):
    """
    Get User from Elastic
    ---
    tags:
      - admin
    produces:
      - application/json
    parameters:
      - name: user_uid
        in: path
        type: string
        description:
        required: true
    responses:
      '200':
        description: Elasticsearch Resultset
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
      """
    user_uuid_res = es.search(index=search_index,
                              body={"query": {"term": {"userUid": user_uid}}},
                              params={'_source_includes': 'userUuid'})
    if len(user_uuid_res.get('hits', {}).get('hits', [])) == 1:
        user_uuid = user_uuid_res.get('hits').get('hits')[0]
        r = es.get(index=search_index, id=user_uuid.get('_id'))
        return jsonify(r)
    else:
        return jsonify({'error': 'No results returned'})


@bp.route('/user/<user_uuid>/sync_elasticsearch')
@jwt_required()
def synchronize_elasticsearch_doc(user_uuid=None):
    """
    Syncs user data to Elastic
    ---
    tags:
     - admin
    produces:
      - application/json
    parameters:
      - name: user_uuid
        in: path
        type: string
        required: true
    responses:
      default:
        description: Unexpected Failure
      '404':
        description: user_uuid was not found
        schema:
          message: string
      '200':
        description: Sync completed
        schema:
          message: string
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    sync_elasticsearch(user_uuid=user_uuid)
    return jsonify({})


@bp.route('/user/potential_group', methods=['GET'])
@jwt_required()
def get_user_potential_group_by_uuid_endpoint():
    """
    Get user potential group
    ---
    tags:
      - users
    produces:
      - application/json
    parameters:
      - name: group_filter_uuid
        in: query
        type: string
        description:
        required: true
    responses:
      '200':
        description: success
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
      """
    if 'group_filter_uuid' not in request.args:
        abort(400, 'Missing group_filter_uuid.')

    group_filter_uuid = request.args.get('group_filter_uuid')

    group_filter = get_user_group_filter_by_uuid(group_filter_uuid)
    email, group_uuid = group_filter.user_email, group_filter.group_uuid
    potential_group = get_user_potential_group(email, group_uuid)

    return jsonify({'userEmail': email, 'potentialGroup': potential_group}), 200
