import os
from datetime import timedelta

from flask import Blueprint
from flask import abort
from flask import current_app
from flask import request
from flask.json import jsonify
from flask_jwt_extended import jwt_required

from figure1.common.helpers.verification import close_expired_empty_change_requests
from figure1.common.iterable import generate_case_summary_task
from figure1.common.types import VerificationType
from figure1.core.firebase import GoogleApi
from figure1.store import UserKeyManagement
from figure1.common.activities.user_profile_activities import update_profile_comments_task
from figure1.common.activities.user_profile_activities import update_profile_cases_task
from figure1.common.activities.user_profile_activities import update_profile_stats_task
from figure1.common.activities.user_profile_activities import update_all_activities_task
from figure1.common.activities.user_profile_activities import verify_user_activity_count_task
from .casecme import sync_case_cme_answers
from .cases import detect_case_language
from .cases import translate_case_content
from .cases import update_all_case_cme_labels
from .communications import migrate_communication_channels
from .firestore import delete_auth_users
from .firestore import delete_firestore_collection
from .migrate_specialties import load_specialty_data
from .notifications import sync_user_notifications
from .specialties import handle_csv_upload
from .specialties import handle_json_upload
from .topics import load_topic_data
from .users import fix_figure1_followers
from .users import run_user_aggregate
from .users import sync_deleted_users
from .users import trigger_iterable_bulk_user_import
from .users import update_user_followers
from .verify import bulk_verify
from .verify import download_and_import_dmd_data_from_s3_to_database
from .verify import import_npi_numbers


bp = Blueprint('pro_tools_endpoints', __name__)


@bp.route('/tools/redis/user_keys', methods=['GET', 'DELETE'])
@jwt_required()
def get_redis_keys_endpoint():
    """
        Get/DELETE a list of keys for a user, or get the value of a key

        If the delete method is used:
          If the redis key is passed, only that key is deleted
          if the user_uuid is passed, all keys for that user are deleted
          If nothing is passed, all user keys are deleted

        If the get method is used:

            If the list parameter is true and user_uuid parameter is set, a list of keys related to that user are
             returned
            If the user_uuid is not passed, and list is true, then all user parameter keys are returned in a list.
            If a redis key is passed, both the user parameter and the list parameter are ignored and the value for
            that key is returned.
        ---
        tags:
         - Backend Tools
        produces:
          - application/json
        parameters:
          - name: user_uuid
            in: query
            required: false
            type: string
          - name: list
            in: query
            required: false
            type: boolean
          - name: redis_key
            in: query
            required: false
            type: string
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
    user_uuid = request.args.get("user_uuid", None)
    redis_key = request.args.get("redis_key", None)
    list_param = request.args.get("list")
    if list_param == "true":
        list_param = True
    else:
        list_param = False

    if request.method == 'DELETE':
        if redis_key:
            ret = UserKeyManagement.delete_keys(redis_key)
        elif user_uuid:
            ret = UserKeyManagement.delete_user_keys(user_uuid=user_uuid)
        else:
            ret = UserKeyManagement.delete_user_keys()

    elif redis_key and request.method == 'GET':
        ret = UserKeyManagement.get_key_value(redis_key)

    elif list_param and user_uuid:
        ret = UserKeyManagement.get_all_user_keys(user_uuid=user_uuid)

    elif list_param:
        ret = UserKeyManagement.get_all_user_keys()
    else:
        ret = "Invalid command combination"

    return jsonify(ret), 200


@bp.route('/tools/v2/specialties/add', methods=["POST"])
@jwt_required()
def handle_specialty_addition_v2():
    """
        Add professions, specialty, or tree entry.

        There is no requirement for the entries to be related to each other. The entries are processed as
        profession first, then specialties, then tree. So tree entries are able to address professions and
        specialties in the same request.
        In the event the profession category is Other HCP or Other Student - the tree entries are added automatically
        since the labels are just the profession name.
        Functionally, this works the same way as csv uploads, but takes a json document instead.

        ---
        tags:
         - Backend Tools
        produces:
          - application/json
        parameters:
          - name: body
            in: body
            required: true
            schema:
              properties:
                professions:
                  type: array
                  items: dict
                specialties:
                  type: array
                  items: dict
                trees:
                  type: array
                  items: dict
              example:
                professions: [{
                                "profession_category": "Other HCP",
                                "profession_name": "Psychologist"
                                }]
                specialties: [{
                                "specialty_name": "Psychologist",
                                "is_valid_case_tag": true,
                                "is_valid_interest": true
                                }]
                trees: [{
                                "profession_name": "Psychologist",
                                "specialty_name": "None",
                                "sub_specialty_name": "Optional",
                                "case_comment_display_label": "Psychologist",
                                "profile_display_label": "Psychologist",
                                "onboarding_display_label": "Psychologist"
                                }]
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
    data = request.json
    professions = data.get("professions", [])
    specialties = data.get("specialties", [])
    tree = data.get("trees", [])
    if professions:
        handle_json_upload(data=professions, upload_type='profession')
    if specialties:
        handle_json_upload(data=specialties, upload_type='specialty')
    if tree:
        handle_json_upload(data=tree, upload_type='tree')
    return jsonify({}), 200


@bp.route('/tools/v2/specialties/upload/<upload_type>', methods=["POST"])
@jwt_required()
def handle_specialty_upload_v2(upload_type):
    """
        Upload a csv file to add either a profession, specialty, or tree entry.


        1. To add a professions, the upload_type must be 'profession' and the expected format is
        "profession category", "profession name"
        2. To add a specialty, the upload type must be 'specialty' and the expected format is
        "specialty name", "boolean for is valid case tag", "boolean for is valid interest
        3. To add a tree entry, at least the profession name must exist, and the upload type must be 'tree'.
         The expected format is
        "profession name",
        "specialty name (optional)",
        "sub-specialty name (optional)",
        "onboarding displayname",
        "profile display name",
        "case comment display name"

        Make sure the headers are deleted, there is no attempt made to strip the headers.

        The boolean values should contain "true" or "false"

        ---
        tags:
         - Backend Tools
        produces:
          - application/json
        parameters:
          - name: upload_type
            in: query
            description: The type of csv to expect
            required: true
            type: string
            enum: ["profession", "specialty", "tree"]
          - name: csvupload
            in: formData
            description:  The media to upload
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
    if 'specialty_list' not in request.files:
        abort(400)

    file = request.files['csvupload']
    save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'csvupload')
    if os.path.isfile(save_path):
        os.unlink(save_path)
    file.save(save_path)
    results = handle_csv_upload(csv_file_path=save_path, upload_type=upload_type)
    return jsonify(results), 200


@bp.route('/tools/upload_tree', methods=["POST"])
@jwt_required()
def upload_tree():
    """
        DEPRECATED - Upload a csv file to create specialty trees

        Make sure the headers are deleted, there is no attempt made to strip the headers.

        There are 17 fields expected, while some can be empty, they must be in the csv.

        category: str
        profession: str
        specialty: str
        subspecialty: str
        onboarding_display: str
        profile_display: str
        case_comment_display: str
        differential_cancer: bool
        differential_cardiology: bool
        differential_dermatology: bool
        differential_emergencymedicine: bool
        differential_hematology: bool
        differential_neurology: bool
        differential_orthopedics: bool
        differential_pediatrics: bool
        differential_primarycare: bool
        differential_rheumatology: bool

        The category is used initially to for profession selection, in many cases, the profession and category are the
         same, but not in all cases.
        The specialty and subspecialty are optional, but generally it isn't necessary to have a tree entry for just a
        profession.
        The three display fields are friendly names to display for a user in those contexts.

        There is an attempt made to reuse tree_uuids from the previous version of the specialty tree, however if an
         exact match isn't found for the full tree, then a new id is generated.

        ---
        tags:
         - Backend Tools
        produces:
          - application/json
        parameters:
          - name: specialty_tree
            in: formData
            description:  The media to upload
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
    if 'specialty_tree' not in request.files:
        abort(400)

    file = request.files['specialty_tree']
    save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'specialty_tree')
    if os.path.isfile(save_path):
        os.unlink(save_path)
    file.save(save_path)
    results = load_specialty_data(filename=save_path, data_type='tree')
    return jsonify(results), 200


@bp.route('tools/sync/deleted_users', methods=["GET"])
@jwt_required()
def sync_deleted_users_endpoint():
    """
    Sync deleted user status to firebase
    Ensures that auth records are deleted for all users who are marked with a not-null deleted_at value
    ---
    tags:
     - Backend Tools
    produces:
      - application/json
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
    sync_deleted_users()
    return jsonify({'success': 'Started tasks to delete users'}), 200


@bp.route('/tools/upload_topics', methods=["POST"])
@jwt_required()
def upload_topics():
    """
        Upload a csv file to create the list of available topics

        The expected csv structure is
         Column 0: <topic_name:str>
         Columns 1..n:  <mapped_specialties:str>

        ---
        tags:
         - Backend Tools
        produces:
          - application/json
        parameters:
          - name: topic_map
            in: formData
            description:  The csv file with topic information
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
    if 'topic_map' not in request.files:
        abort(400)

    file = request.files['topic_map']
    save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'topic_map')
    if os.path.isfile(save_path):
        os.unlink(save_path)
    file.save(save_path)
    results = load_topic_data(filename=save_path)
    return jsonify(results), 200


@bp.route('/tools/bulk_verify', methods=["POST"])
@jwt_required()
def bulk_verify_endpoint():
    """
    Loads a list of users from a file and marks them as verified.

    Users are marked as verified and history records are created.  However iterable, mixpanel events and activity
    notifications are not created.  Legacy users are blocked from future migrations to avoid overwriting this state.

    The expected file structure is a list of user_uuids, one per line


    If a verification_type is given, a verification record will be created for users who are missing one, with the
    given verification_type.  If missing, these users will report as errors instead.
    ---
    tags:
     - Backend Tools
    produces:
      - application/json
    parameters:
      - name: user_list
        in: formData
        description:  The csv file with user uuids
        type: file
        required: true
      - name: moderator_uid
        in: query
        description:  The user making the verification changes
        type: string
        required: true
      - name: verification_type
        in: query
        description:  The verification_type to use for users without a verification record.  If missing, these users
          will not be updated
        type: string
        required: false
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
    if 'user_list' not in request.files:
        abort(400)

    file = request.files['user_list']
    save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'user_list')
    if os.path.isfile(save_path):
        os.unlink(save_path)
    file.save(save_path)

    moderator_uid = request.args.get('moderator_uid')
    verification_type = request.args.get('verification_type')
    if verification_type:
        if verification_type and verification_type.upper() not in [t.name for t in VerificationType]:
            return abort(422, 'Invalid verification_type')
        verification_type = VerificationType[verification_type.upper()]

    results = bulk_verify(filename=save_path,
                          moderator_uid=moderator_uid,
                          verification_type=verification_type)
    return jsonify(results), 200


@bp.route('/tools/trigger_bulk_iterable_import', methods=["GET"])
@jwt_required()
def trigger_bulk_iterable_import_endpoint():
    """
    Looks for the flag in user_state call requires_iterable_sync and goes through in chunks of 100 until it is finished
    syncing users to iterable.
    This operates as a chain of tasks, so it will continue until there are none left. If there is an Overloaded
    exception thrown by iterable, it will wait for the retry backoff to resume the chain.

    ---
    tags:
     - Backend Tools
    produces:
      - application/json
    parameters:
      - name: chunk_size
        in: query
        required: false
        type: int
        description: How many users to process in a chunk - there are 30 seconds between each chunk
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
    chunk_size = request.args.get("chunk_size", 100)
    trigger_iterable_bulk_user_import(chunk_size=chunk_size)
    return jsonify({}), 200


@bp.route('/tools/detect_case_language', methods=["GET"])
@jwt_required()
def detect_case_language_endpoint():
    """
    Detect case language given a case_uuid

    ---
    tags:
     - Backend Tools
    produces:
      - application/json
    parameters:
      - name: case_uuid
        in: query
        required: true
        type: string
        description: Detect case language for this case_uuid
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
    case_uuid = request.args.get("case_uuid")
    resp = detect_case_language(case_uuid=case_uuid)
    if not isinstance(resp, str):
        return jsonify(resp.code), 200
    return jsonify(resp), 200


@bp.route('/tools/translate', methods=["GET"])
@jwt_required()
def translate_case_endpoint():
    """
    Detect case language given a case_uuid

    ---
    tags:
     - Backend Tools
    produces:
      - application/json
    parameters:
      - name: case_uuid
        in: query
        required: true
        type: string
        description: Translate case to english for this case_uuid
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
    case_uuid = request.args.get("case_uuid")
    translate_case_content(case_uuid=case_uuid)
    return jsonify({}), 200


@bp.route('/tools/updatefollower', methods=["GET"])
@jwt_required()
def force_update_user_follower_following():
    """
    Updates a users follow/followers collections

    ---
    tags:
     - Backend Tools
    produces:
      - application/json
    parameters:
      - name: user_uuid
        in: query
        required: false
        type: string
        description: Update followers/following for this user
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
    user_uuid = request.args.get("user_uuid")
    update_user_followers(user_uuid=user_uuid)
    return jsonify({}), 200


@bp.route('/tools/import_npi_numbers', methods=["POST"])
@jwt_required()
def import_npi_numbers_endpoint():
    """
    Imports a list of NPI numbers for users from a csv file

    The expected csv structure is
     Column 0: <username:str>
     Column 1: <email:str>
     Column 2: <npi_number:str>

    Either username or email can be used.  The username is checked first, and if a match is not found a lookup is
    performed with the email.  If a verification record does not exist for the user, it is not created.

    ---
    tags:
     - Backend Tools
    produces:
      - application/json
    parameters:
      - name: npi_list
        in: formData
        description:  The csv file with npi data
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

    if 'npi_list' not in request.files:
        abort(400)

    file = request.files['npi_list']
    save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'npi_list')
    if os.path.isfile(save_path):
        os.unlink(save_path)
    file.save(save_path)

    res = import_npi_numbers(filename=save_path)
    return jsonify(res), 200


@bp.route('/tools/delete_firestore_collection', methods=["GET"])
@jwt_required()
def delete_firestore_collection_endpoint():
    """
    Delete a firestore collection.
    ---
    tags:
     - Backend Tools
    produces:
      - application/json
    parameters:
      - name: collection_name
        in: query
        required: true
        type: string
        description: The name of the collection to delete
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
    collection_name = request.args.get('collection_name')
    if not collection_name:
        abort(400)

    if GoogleApi.is_production():
        abort(403, 'Not allowed for production environment')

    task = delete_firestore_collection.delay(collection_name=collection_name)
    return jsonify({'task_id': task.task_id})


@bp.route('/tools/force_user_aggregation', methods=["GET"])
@jwt_required()
def run_case_summary_aggregation_endpoint():
    """
    Generate user aggregate events for case summary. Passing in a user_uuid ignores force and limit.
    ---
    tags:
     - Backend Tools
    produces:
      - application/json
    parameters:
      - name: user_uuid
        in: query
        type: string
        required: false
        description: The user_uuid to run an aggregate event for
      - name: limit
        in: query
        required: false
        type: integer
        description: How many users to affect
      - name: force
        in: query
        required: false
        type: boolean
        description: Force task to run even if it isn't scheduled too.

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
    force = request.args.get('force', 'false')
    limit = request.args.get('limit', 0)
    user_uuid = request.args.get('user_uuid')
    if user_uuid:
        generate_case_summary_task(user_uuid=user_uuid)
        return jsonify({}), 200
    if force.lower() == 'true':
        force = True
    else:
        force = False

    if int(limit):
        limit = limit
    else:
        limit = 0
    generate_case_summary_task(limit=limit, force=force)
    return jsonify({}), 200


@bp.route('/tools/delete_firebase_auth', methods=["GET"])
@jwt_required()
def delete_firebase_auth():
    """
    Deletes all authentication records in firebase.
    To confirm deletion, pass value 'confirm', otherwise will be run as a dry run.
    ---
    tags:
     - Backend Tools
    produces:
      - application/json
    parameters:
      - name: confirm
        in: query
        required: false
        type: string
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
    confirm = request.args.get('confirm', '')

    if not isinstance(confirm, str) or confirm.lower() != 'confirm':
        dry_run = True
    else:
        dry_run = False

    if GoogleApi.is_production():
        abort(403, 'Not allowed for production environment')

    task = delete_auth_users.delay(dry_run=dry_run)
    return jsonify({'task_id': task.task_id,
                    'dry_run': dry_run})


@bp.route('/tools/fix_figure1_followers', methods=["GET"])
@jwt_required()
def fix_figure1_followers_endpoint():
    """
    Fixes invalid followers state of the figure 1 account.

    Finds all firestore profiles where `figure1` is listed as a follower, and move the doc to the following
    subcollection instead.
    ---
    tags:
     - Backend Tools
    produces:
      - application/json
    parameters:
      - name: user_uuid
        in: query
        required: false
        type: string
        description: Update followers/following for this user.  If null, updates all users following figure1.
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
    user_uuid = request.args.get("user_uuid")
    fix_figure1_followers(user_uuid=user_uuid)
    return jsonify({}), 200


@bp.route('/tools/migrate_communication_channels', methods=["GET"])
@jwt_required()
def migrate_communication_channels_endpoint():
    """
    Migrates communication channels to r_communication_channel
    ---
    tags:
     - Backend Tools
    produces:
      - application/json
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
    migrate_communication_channels()
    return jsonify({}), 200


@bp.route('/tools/generate_aggregate', methods=["GET"])
@jwt_required()
def user_aggregate_endpoint():
    """
    Re-generates the profiles for the last 12 months of users. Takes a long time to run since it is heavy to run for
    elasticsearch.
    ---
    tags:
     - Backend Tools
    produces:
      - application/json
    parameters:
      - name: skip_backfill
        in: query
        type: boolean
        required: false
        description: If set to true, just update the profiles in queue, otherwise updates all users in the last year
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
    skip_backfill = False
    skip = request.args.get('skip_backfill')
    if isinstance(skip, str) and skip.lower() == 'true':
        skip_backfill = True

    res = run_user_aggregate(skip_backfill=skip_backfill)
    return jsonify(res), 200


@bp.route('/tools/sync/user_notifications', methods=["GET"])
@jwt_required()
def sync_user_notifications_endpoint():
    """
    Syncs user notifications to firestore
    ---
    tags:
     - Backend Tools
    produces:
      - application/json
    parameters:
      - name: user_uuid
        in: query
        required: false
        type: string
        description: Sync notifications for this user.  If null, syncs all users with notifications
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
    user_uuid = request.args.get("user_uuid")
    sync_user_notifications(user_uuid=user_uuid)
    return jsonify({}), 200


@bp.route('/tools/verification/cleanup')
@jwt_required()
def trigger_cleanup_empty_verification_endpoint():
    """
    Runs the task to cleanup empty verifications
    ---
    tags:
     - Backend Tools
     - Verification Tools
    produces:
      - application/json
    parameters:
      - name: close_from
        in: query
        type: int
        required: false
        description: Now() minus this many hours to close verifications too. For example, close_from=2 means that
            verification requests opened up to 2 hours ago will be closed. Defaults to 2 days.
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
    cf = request.args.get('close_from', default=48, type=int)
    close_expired_empty_change_requests(close_from=timedelta(hours=cf))
    return jsonify({}), 200


@bp.route('/tools/update_case_cme_labels', methods=["GET"])
@jwt_required()
def update_case_cme_labels():
    """
    Updates all case cme labels for all cases in firebase.
    ---
    tags:
     - Backend Tools
    produces:
      - application/json
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
    res = update_all_case_cme_labels()
    if 'error' in res:
        return jsonify(res), 500
    return jsonify(res), 200


@bp.route('/tools/sync/case_cme_answers', methods=["GET"])
@jwt_required()
def sync_case_cme_answers_endpoint():
    """
    Starts a task to sync all case cme answers to firestore
    ---
    tags:
     - Backend Tools
    produces:
      - application/json
    responses:
      default:
        description: Unexpected Failure
      '202':
        description: OK
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    task = sync_case_cme_answers.delay()
    return jsonify({'task_id': task.task_id}), 202


@bp.route('/tools/sync/activity/cases/<offset>', methods=["GET"])
@jwt_required()
def sync_all_profile_cases_endpoint(offset):
    """
    Starts a task to sync all cases to the author's profile
    ---
    tags:
     - Backend Tools
    produces:
      - application/json
    parameters:
      - name: offset
        in: path
        type: int
        required: false
        description: Start from here instead of the beginning
    responses:
      default:
        description: Unexpected Failure
      '202':
        description: OK
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    try:
        offset = int(offset)
    except ValueError:
        offset = 0
    task = update_profile_cases_task.delay(offset=offset)
    return jsonify({'task_id': task.task_id}), 202


@bp.route('/tools/sync/activity/comments/<offset>', methods=["GET"])
@jwt_required()
def sync_all_profile_comments_endpoint(offset):
    """
    Starts a task to sync all comments to the author's profile
    ---
    tags:
     - Backend Tools
    produces:
      - application/json
    parameters:
      - name: offset
        in: path
        type: int
        required: false
        description: Start from here instead of the beginning
    responses:
      default:
        description: Unexpected Failure
      '202':
        description: OK
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    try:
        offset = int(offset)
    except ValueError:
        offset = 0
    task = update_profile_comments_task.delay(offset=offset)
    return jsonify({'task_id': task.task_id}), 202


@bp.route('/tools/sync/activity/stats/<offset>', methods=["GET"])
@jwt_required()
def sync_all_profile_activity_stats_endpoint(offset):
    """
    Starts a task to sync all status to the respective profiles
    ---
    tags:
     - Backend Tools
    produces:
      - application/json
    parameters:
      - name: offset
        in: path
        type: int
        required: false
        description: Start from here instead of the beginning
    responses:
      default:
        description: Unexpected Failure
      '202':
        description: OK
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    try:
        offset = int(offset)
    except ValueError:
        offset = 0
    task = update_profile_stats_task.delay(offset=offset)
    return jsonify({'task_id': task.task_id}), 202


@bp.route('/tools/sync/activity/<user_uuid>', methods=["GET"])
@jwt_required()
def sync_all_profile_activity_by_user_endpoint(user_uuid):
    """
    Starts a task to sync a single user
    ---
    tags:
     - Backend Tools
    produces:
      - application/json
    parameters:
      - name: user_uuid
        in: path
        type: string
        required: false
        description: user uuid
    responses:
      default:
        description: Unexpected Failure
      '202':
        description: OK
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    task = update_all_activities_task.delay(user_uuid=user_uuid)
    return jsonify({'task_id': task.task_id}), 202


@bp.route('/tools/sync/activity/<user_uuid>/verify', methods=["GET"])
@jwt_required()
def verify_profile_activity_count_by_user_endpoint(user_uuid):
    """
    Verifies the total activity count matches the number of documents. Wipes and re-syncs if it doesn't match
    ---
    tags:
     - Backend Tools
    produces:
      - application/json
    parameters:
      - name: user_uuid
        in: path
        type: string
        required: false
        description: user uuid
    responses:
      default:
        description: Unexpected Failure
      '202':
        description: OK
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    task = verify_user_activity_count_task.delay(user_uuid=user_uuid)
    return jsonify({'task_id': task.task_id}), 202


@bp.route('/tools/import_dmd_data', methods=["POST"])
@jwt_required()
def import_dmd_data_endpoint():
    """
    Import DMD data into database from a csv file in a S3 DMD data bucket (e.g. pro-figure1-dev/dmd/dmd_data.csv)
    All DMD data files should exist in a S3 bucket given environment (e.g. pro-figure1-dev/dmd)

    All DMD data files should be csv files with a header list:
    [ user_uuid,email,first_name,last_name,npi_number,profession,speciality,subspecialty,country,state,
      practice_hospital,practice_location,graduation_date,school,
      DMD_HCP_TYPE,DMD_DGID,DMD_FIRSTNAME,DMD_LASTNAME,
      DMD_DEGREE,DMD_PRIMARY_SPECIALTY,DMD_SPECIALTY_LONG_DESCRIPTION,DMD_NPI,DMD_STATE ]

    Note: Ideally, the user_uuid needs to be unique;
          When duplicate objects(rows) of the same user_uuid are encountered,
          non-user_uuid attributes are overwritten as the objects are encountered.

    The expected csv structure is
        Column 0: user_uuid, Required
        Column 1: email, Required
        Column 2: first_name, Optional
        Column 3: last_name, Optional
        Column 4: npi_number, Optional
        Column 5: profession, Optional
        Column 6: speciality, Optional
        Column 7: subspecialty, Optional
        Column 8: country, Optional
        Column 9: state, Optional
        Column 10: practice_hospital, Optional
        Column 11: practice_location, Optional
        Column 12: graduation_date, Optional; Ideally, this date should be a date_string in any valid ISO 8601 format
        Column 13: school, Optional
        Column 14: DMD_HCP_TYPE, Optional
        Column 15: DMD_DGID, Optional
        Column 16: DMD_FIRSTNAME, Optional
        Column 17: DMD_LASTNAME, Optional
        Column 18: DMD_DEGREE, Optional
        Column 19: DMD_PRIMARY_SPECIALTY, Optional
        Column 20: DMD_SPECIALTY_LONG_DESCRIPTION, Optional
        Column 21: DMD_NPI, Optional
        Column 22: DMD_STATE, Optional
    ---
    tags:
     - Backend Tools
    produces:
      - application/json
    parameters:
      - name: body
        in: body
        description:  The csv file name with DMD data (e.g. dmd_data.csv)
        required: true
        schema:
          properties:
            dmd_data_file_name:
              type: string
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: It returns Dict contains ImportErrorCount, ImportErrors, ImportUpdatedCount,
                     if all data have been processed.
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """

    if 'dmd_data_file_name' not in request.json:
        abort(400)

    filename = request.json['dmd_data_file_name']
    res = download_and_import_dmd_data_from_s3_to_database(filename=filename)
    return jsonify(res), 200
