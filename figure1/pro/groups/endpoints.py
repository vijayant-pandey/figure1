import os
import logging
from celery.canvas import Signature
from flask import Blueprint
from flask import request
from flask import abort
from flask import current_app
from flask.json import jsonify
from flask_jwt_extended import jwt_required

from figure1.configuration import es_settings
from figure1.common.types.groups import GroupUploadModel
from figure1.common.types.groups import GroupUpdateModel
from figure1.common.utils import s3_utils
from figure1.common.utils import execute_on_return
from figure1.exceptions import GroupException
from figure1.exceptions import UserError
from figure1.exceptions import CaseNotFound
from figure1.exceptions import UserUUIDNotFound
from figure1.pro.groups.domain import create_users_group
from figure1.pro.groups.domain import delete_users_group
from figure1.pro.groups.domain import add_members_to_group
from figure1.pro.groups.domain import remove_members_from_group
from figure1.pro.groups.domain import update_groups_avatar_internal
from figure1.pro.groups.domain import get_groups_by_user_uuid
from figure1.pro.groups.domain import get_members_by_group_uuid
from figure1.pro.groups.domain import get_groups
from figure1.pro.groups.domain import get_cases_by_group_uuid
from figure1.pro.groups.domain import add_case_to_group
from figure1.pro.groups.domain import remove_case_from_group
from figure1.pro.groups.domain import import_group_members
from figure1.pro.groups.domain import invite_members_to_group
from figure1.pro.groups.domain import admin_update_group

from figure1.core import es

bp = Blueprint('pro_groups_endpoint', __name__)
logger = logging.getLogger(__name__)


@bp.errorhandler(UserError)
def handle_user_error(e):
    logger.exception("%s", e.msg)
    return jsonify(e.as_dict()), e.rc


@bp.errorhandler(UserUUIDNotFound)
def handle_user_not_found_error(e):
    logger.exception("%s", e.msg)
    return jsonify(e.as_dict()), e.rc


@bp.errorhandler(GroupException)
def handle_group_error(e):
    logger.exception("%s", e.msg)
    return jsonify(e.as_dict()), e.rc


@bp.errorhandler(CaseNotFound)
def handle_case_error(e):
    logger.exception("%s", e.msg)
    return jsonify(e.as_dict()), e.rc


@bp.route('/groups/create', methods=['POST'])
@jwt_required()
def create_new_group():
    """
    this endpoint creates a new group
    ---
    tags:
     - group
    produces:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        schema:
          properties:
            group_description:
              type: string
              description: group's description - optional
              required: false
            group_name:
              type: string
              description: group's name
              required: true
            group_active:
              type: bool
              description: groups active - optional
              required: false
            group_label:
              type: string
              description: group label
              required: true
            group_type:
              type: string
              description: group type - optional
              enum: ["institutional", "user"]
              required: false
            group_creator_uuid:
              type: string
              description: group creator uuid
              required: true
            is_public_group:
              type: bool
              description: True if the group is public, false or null otherwise
              required: false
          example:
            group_name: figure1 group
            group_description: this is figure1 group description
            group_active: false
            group_label: label1
            group_type: user
            group_creator_uuid: "your group_creator_uuid"
            is_public_group: true

    responses:
      default:
        description: Unexpected Failure
      '200':
        description: group created

    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """

    if 'group_name' not in request.json:
        return abort(400, 'missing group_name')

    if 'group_label' not in request.json:
        return abort(400, 'missing group_label')

    if 'group_creator_uuid' not in request.json:
        return abort(400, 'missing group_creator_uuid')

    group_data = GroupUploadModel.parse_obj(request.json)
    res = create_users_group(data=group_data)
    task = res.pop('task')

    return execute_on_return(task, response=res.get('group'))


@bp.route('/groups/delete', methods=['DELETE'])
@jwt_required()
def delete_group():
    """
    Delete a group

    In order to delete an institutional group, all members and cases must first be removed.  For other group types,
    members are removed and cases are marked as deleted.
    ---
    tags:
     - group
    produces:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        schema:
          properties:
            group_uuid:
              type: string
              description: group's uuid
              required: true

          example:
            group_uuid: <group_uuid>

    responses:
      default:
        description: Unexpected Failure
      '200':
        description: group deleted
      '404':
        description: group not found

    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """

    if 'group_uuid' not in request.json:
        return abort(400, 'missing group_uuid')

    group_uuid = request.json.get('group_uuid')
    res = delete_users_group(group_uuid=group_uuid)

    task = res.pop('task')
    return execute_on_return(task, response=res)


@bp.route('/groups/modify_members', methods=['POST'])
@jwt_required()
def modify_members():
    """
    this endpoint adds members to a group or deletes members from a group
    ---
    tags:
     - group
     - users
    produces:
      - application/json
    parameters:
      - name: action
        in: query
        type: string
        enum: ['add_members', 'remove_members']
        description:
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
          properties:
            group_uuid:
              type: string
              description: group's uuid
              required: true
            users_uuid:
              type: array
              description: users' uuid
              required: true
          example:
            group_uuid: <group_uuid>
            users_uuid: ['user_uuid1' , 'user_uuid2']

    responses:
      default:
        description: Unexpected Failure
      '200':
        description: group created

    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """

    if 'group_uuid' not in request.json:
        return abort(400, 'missing group_uuid')

    if 'users_uuid' not in request.json:
        return abort(400, 'missing users_uuid')

    group_uuid = request.json.get('group_uuid')
    users_uuid = request.json.get('users_uuid')
    action = request.args.get('action')
    force_synchronous = request.args.get('force_synchronous') == 'true'
    if isinstance(users_uuid, list):
        res = {}
        if action == 'add_members':
            res = add_members_to_group(group_uuid=group_uuid, users_uuid=users_uuid)
        elif action == 'remove_members':
            res = remove_members_from_group(group_uuid=group_uuid, users_uuid=users_uuid)
        else:
            abort(422, "action is invalid")

        task = res.pop('task')
        return execute_on_return(task, synchronous=force_synchronous, response=res)
    else:
        abort(422, "users_uuid is not a list")


@bp.route('/groups/invite_members', methods=['POST'])
@jwt_required()
def invite_members():
    """
    Invite members to a group.

    This adds the users to GroupMemberFilter and triggers an iterable event but does not immediately add the user to
    the group.
    ---
    tags:
     - group
     - users
    produces:
      - application/json
    parameters:
      - name: force_synchronous
        in: query
        type: boolean
        required: false
        description: Forces the return to be synchronous
      - name: body
        in: body
        required: true
        schema:
          properties:
            user_uid:
              type: string
              description: The uid of the user initiating the invite
              required: true
            group_uuid:
              type: string
              description: group's uuid
              required: true
            users_uuid:
              type: array
              description: The uuids of the users being invited to the group
              required: true
          example:
            user_uid: <user_uid>
            group_uuid: <group_uuid>
            users_uuid: ['user_uuid1' , 'user_uuid2']

    responses:
      default:
        description: Unexpected Failure
      '200':
        description: group created

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
    if 'group_uuid' not in request.json:
        return abort(400, 'missing group_uuid')
    if 'users_uuid' not in request.json:
        return abort(400, 'missing users_uuid')

    user_uid = request.json.get('user_uid')
    group_uuid = request.json.get('group_uuid')
    users_uuid = request.json.get('users_uuid')
    force_synchronous = request.args.get('force_synchronous') == 'true'
    if isinstance(users_uuid, list):
        res = invite_members_to_group(user_uid=user_uid, group_uuid=group_uuid, users_uuid=users_uuid)
        task = res.pop('task')
        return execute_on_return(task, synchronous=force_synchronous, response=res)
    else:
        abort(422, "users_uuid is not a list")


@bp.route('/admin/users/<user_uuid>/groups', methods=["GET"])
@jwt_required()
def get_groups_given_user(user_uuid):
    """
    this endpoint returns a list of groups given user
    ---
    tags:
     - group
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
    res = get_groups_by_user_uuid(user_uuid)
    return jsonify(res), 200


@bp.route('/admin/groups/<group_uuid>', methods=["POST"])
@jwt_required()
def update_group(group_uuid):
    """
    this endpoint updates a group
    ---
    tags:
     - group
    produces:
      - application/json
    parameters:
      - name: group_uuid
        in: path
        type: string
        required: true
      - name: body
        in: body
        required: true
        schema:
          properties:
            group_description:
              type: string
              description: group's description
              required: false
            group_name:
              type: string
              description: group's name
              required: false
          example:
            group_name: figure1 group
            group_description: this is figure1 group description
    responses:
      default:
        description: Unexpected Failure
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
    group_update = GroupUpdateModel.parse_obj(request.json)
    res = admin_update_group(group_uuid=group_uuid, update=group_update)
    task = res.pop('task')

    return execute_on_return(task, response=res.get('group').dict())


@bp.route('/admin/groups/<group_uuid>/members', methods=["GET"])
@jwt_required()
def get_members_given_group(group_uuid):
    """
    this endpoint returns a list of members given group
    ---
    tags:
     - group
    produces:
      - application/json
    parameters:
      - name: group_uuid
        in: path
        type: string
        required: true
    responses:
      default:
        description: Unexpected Failure
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
    res = get_members_by_group_uuid(group_uuid)
    return jsonify(res), 200


@bp.route('/admin/groups', methods=["GET"])
@jwt_required()
def get_all_groups():
    """
    this endpoint returns a list of groups
    ---
    tags:
     - group
    produces:
      - application/json
    responses:
      default:
        description: Unexpected Failure
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
    res = get_groups()
    return jsonify(res), 200


@bp.route('/admin/groups/<group_uuid>/cases', methods=["GET"])
@jwt_required()
def get_cases_given_group(group_uuid):
    """
    this endpoint returns a list of group cases
    ---
    tags:
     - group
    produces:
      - application/json
    parameters:
      - name: group_uuid
        in: path
        type: string
        required: true
    responses:
      default:
        description: Unexpected Failure
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
    res = get_cases_by_group_uuid(group_uuid)
    return jsonify(res), 200


@bp.route('/admin/groups/modify_case', methods=['POST'])
@jwt_required()
def modify_case():
    """
    this endpoint adds a case to a group or deletes a case from a group
    ---
    tags:
     - group
    produces:
      - application/json
    parameters:
      - name: action
        in: query
        type: string
        enum: ['add_case', 'remove_case']
        description:
        required: true
      - name: body
        in: body
        required: true
        schema:
          properties:
            group_uuid:
              type: string
              description: group's uuid
              required: true
            case_uuid:
              type: string
              description: case's uuid
              required: true

          example:
            group_uuid: <group_uuid>
            case_uuid: <case_uuid>

    responses:
      default:
        description: Unexpected Failure
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
    if 'group_uuid' not in request.json:
        return abort(400, 'missing group_uuid')

    if 'case_uuid' not in request.json:
        return abort(400, 'missing case_uuid')

    group_uuid = request.json.get('group_uuid')
    case_uuid = request.json.get('case_uuid')
    action = request.args.get('action')

    if action == 'add_case':
        add_case_to_group(group_uuid=group_uuid, case_uuid=case_uuid)
    elif action == 'remove_case':
        remove_case_from_group(group_uuid=group_uuid, case_uuid=case_uuid)
    else:
        abort(422, 'Invalid action: ' + str(action))

    return jsonify({}), 200


@bp.route('/groups/<group_uuid>/avatar', methods=["POST"])
@jwt_required()
def upload_group_avatar(group_uuid):
    """
    Uploads and sets an avatar for a group
    ---
    tags:
     - group
    produces:
      - application/json
    parameters:
      - name: group_uuid
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

    temp_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], group_uuid)
    r = s3_utils.upload_image_to_s3(file=file, upload_dir=f'groups/{group_uuid}/avatar', temp_dir=temp_dir)
    updated_group = update_groups_avatar_internal(group_uuid=group_uuid, url=r['photo_url'])
    return jsonify(updated_group.dict()), 200


@bp.route('/groups/import_members', methods=["POST"])
@jwt_required()
def import_members_endpoint():
    """
    Imports a list of group members from a csv file

    The expected csv structure is
     Column 0: npi_number
     Column 1: first_name
     Column 2: last_name
     Column 3: email_address
     Column 4: group_uuid
     Column 5: primary specialty tree_uuid
     Column 6: country_uuid
    ---
    tags:
     - group
    produces:
      - application/json
    parameters:
      - name: group_members_list
        in: formData
        description:  The csv file with group members data
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
    if 'group_members_list' not in request.files:
        abort(400)

    file = request.files['group_members_list']
    save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'group_members_list')

    try:
        if os.path.isfile(save_path):
            os.unlink(save_path)
        file.save(save_path)
    except OSError:
        abort(500, 'Unable to save the group members list file.')

    res = import_group_members(save_path)
    return jsonify(res), 200


@bp.route("/admin/groups/search", methods=['POST'])
@jwt_required()
def search_groups_endpoint():
    """
    Search
    ---
    tags:
     - group
    consumes:
      - application/json
    parameters:
      - name: request
        in: body
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

    search_request = request.json
    results = es.search(body=search_request, index=es_settings.groups_alias)
    return jsonify(results)


@bp.route('/admin/groups/<group_uuid>', methods=["GET"])
@jwt_required()
def get_group_endpoint(group_uuid):
    """
    Gets a group from Elastic
    ---
    tags:
     - group
    consumes:
      - application/json
    parameters:
      - name: group_uuid
        in: path
        type: string
        required: true
    responses:
      '200':
        description: Elasticsearch Result
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
      """

    results = es.get(id=group_uuid, index=es_settings.groups_alias)
    return jsonify(results)
