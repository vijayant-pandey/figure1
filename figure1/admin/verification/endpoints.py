import logging

from flask import Blueprint, abort, request, make_response
from flask.json import jsonify
from flask_jwt_extended import jwt_required

from figure1.admin.verification.domain import create_tag, update_tag, delete_tag, update_verification_status, \
    add_verification_note, update_user_tags, edit_verification
from figure1.core import es
from figure1.common.types.endpoints import VerificationStatusUpdate, VerificationTagUpdate
from figure1.exceptions import InvalidNPINumber

search_index = 'users'

bp = Blueprint('pro_admin_verification_endpoint', __name__)
logger = logging.getLogger(__name__)


@bp.errorhandler(InvalidNPINumber)
def handle_invalid_npi_number_exception(e):
    logger.exception("NPI number validation failed")
    return jsonify(msg="NPI number failed to validate"), e.rc


@bp.route('/verification/edit/<user_uid>', methods=["PATCH"])
@jwt_required()
def edit_verification_endpoint(user_uid):
    """
    Edit the verification info for a user
    Updates the properties given.  Omitted properties will be unmodified.
    ---
    tags:
     - verification admin
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
            moderator_uid:
              type: string
              type: string
              required: true
              description: The uid of the moderator
            flag_for_review:
              type: bool
              required: false
              description: Flag for later review - defaults to false
            first_name:
              type: string
              required: false
              description: The first name of the user
            last_name:
              type: string
              required: false
              description: The last name of the user
            profession_uuid:
              type: string
              required: false
              description: The profession of the user
            specialty_uuid:
              type: string
              required: false
              description: The specialty of the user
            primary_specialty_tree_uuid:
              type: string
              required: false
              description: The primary specialty of the user - deprecates specialty_uuid and profession_uuid
            npi_number:
              type: string
              required: false
              description: The npi number for the user
            medical_license:
              type: string
              required: false
              description: The medical license number for the user
            school_uuid:
              type: string
              required: false
              description: The school of the user
            graduation_year:
              type: string
              required: false
              description: The graduation year of the user
            country_uuid:
              type: string
              required: false
              description: The user's country
            state_uuid:
              type: string
              required: false
              description: The user's state or province
          example:
            moderator_uid: tJMPKzrR4ig3Yejc7cRQGSl8URr1
            flag_for_review: true
            first_name: Test
            last_name: User
            profession_uuid: 7275dbe6-7416-4352-b2d9-ebf3d580cc0d
            specialty_uuid: 692b5170-11fa-4e0c-983c-127bc566bea0
            primary_specialty_tree_uuid: <tree uuid for the user>
            npi_number: 1234567893
            medical_license: 0000000001
            school_uuid: 98d53681-be0a-493e-b603-fea37f961f4e
            graduation_year: 2019
            country_uuid: 0137a074-9139-4187-878b-15a5af6f98ae
            state_uuid: d826ddd1-643c-4c33-b7c7-82d73dede7a6
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

    if 'moderator_uid' not in request.json:
        return abort(400, 'missing moderator_uid')

    moderator_uid = request.json.get('moderator_uid')
    flag_for_review = request.json.get('flag_for_review', False)
    task = edit_verification(moderator_uid=moderator_uid,
                             user_uid=user_uid,
                             flag_for_review=flag_for_review,
                             data=request.json)

    res = task.apply().get()
    return jsonify(res), 200


@bp.route('/verification/note', methods=["POST"])
@jwt_required()
def add_note():
    """
    Add a note to a verification request(s)
    If multiple user_uids are passed in with a flag_for_review flag set, the flag applies to all users passed in.
    ---
    tags:
     - verification admin
    produces:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        schema:
          properties:
            moderator_uid:
              type: string
              type: string
              required: true
              description: The uid of the moderator
            flag_for_review:
              type: bool
              required: false
              description: Flag for later review - defaults to false
            user_uids:
              type: array
              items:
                type: string
              required: true
              description: The uid of user(s) to update
            text:
              type: string
              required: true
              description: The note text to set
          example:
            moderator_uid: tJMPKzrR4ig3Yejc7cRQGSl8URr1
            user_uids: ['NhIWRtGwZsUBLG8lEP4qmcvo5XI3']
            text: "Uploaded photo was blurry"
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
    if 'moderator_uid' not in request.json:
        return abort(400, 'missing moderator_uid')
    if 'user_uids' not in request.json:
        return abort(400, 'missing user_uids')
    if 'text' not in request.json:
        return abort(400, 'missing text')

    moderator_uid = request.json.get('moderator_uid')
    flag_for_review = request.json.get('flag_for_review', False)
    user_uids = request.json.get('user_uids')
    text = request.json.get('text')

    task = add_verification_note(moderator_uid=moderator_uid,
                                 user_uids=user_uids,
                                 flag_for_review=flag_for_review,
                                 text=text)

    res = task.apply().get()
    return jsonify(res), 200


@bp.route('/verification/state', methods=["POST"])
@jwt_required()
def update_state():
    """
    Update the state of a verification request(s)
    If multiple user_uids are passed in with a flag_for_review flag set, the flag applies to all users passed in
    ---
    tags:
     - verification admin
    produces:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        schema:
          properties:
            moderator_uid:
              type: string
              required: true
              description: The uid of the moderator
            flag_for_review:
              type: bool
              required: false
              description: Flag for later review - defaults to false
            user_uids:
              type: array
              items:
                type: string
              required: false
              description: The uid of user(s) to update
            state:
              type: string
              enum: ["pending",
               "updated_info",
                "info_needed",
                "verified",
                "unverifiable",
                "review_required",
                "rejected"]
              required: false
              description: The new state to set
          example:
            moderator_uid: tJMPKzrR4ig3Yejc7cRQGSl8URr1
            user_uids: ['NhIWRtGwZsUBLG8lEP4qmcvo5XI3']
            state: verified
            flag_for_review: true
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

    status_update = VerificationStatusUpdate.parse_obj(request.json)

    task = update_verification_status(status_update=status_update)
    res = task.apply().get()
    return jsonify(res), 200


@bp.route('/verification/tag', methods=["POST"])
@jwt_required()
def update_tags():
    """
    Update the tags on a verification request(s)
    The tags given will overwrite previous values.  If a previous tag is to be preserved it should be included in the
    request.  Passing an empty array for 'tags' will clear all tags.
    ---
    tags:
     - verification admin
    produces:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        schema:
          properties:
            moderator_uid:
              type: string
              required: true
              description: The uid of the moderator
            user_uids:
              type: array
              items:
                type: string
              required: false
              description: The uid of user(s) to update
            tag_uuids:
              type: array
              items:
                type: string
              required: true
              description: The list of tags to assign to the user's verification request
          example:
            moderator_uid: tJMPKzrR4ig3Yejc7cRQGSl8URr1
            user_uids: ['NhIWRtGwZsUBLG8lEP4qmcvo5XI3']
            tag_uuids: ['8581f339-b178-40eb-87af-6bc05e2400f4', '4adadf1b-47c8-44d0-a764-d3aa4cef10b7']
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

    verification_update = VerificationTagUpdate.parse_obj(request.json)

    update_user_tags(tag_update=verification_update)
    return jsonify({}), 200


@bp.route("/verification/search", methods=['POST'])
@jwt_required()
def search_users():
    """
    Search
    ---
    tags:
      - verification admin
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
    if request.method == 'POST':
        search_request = request.json

        try:
            results = es.search(body=search_request, index=search_index, doc_type='_doc')
        except Exception as e:
            return make_response(jsonify({'error': str(e)}), 400)
        return jsonify(results)


@bp.route("/verification/search/<user_uuid>", methods=['GET'])
@jwt_required()
def get_search_user(user_uuid):
    """
    Get User from Elastic
    ---
    tags:
      - verification admin
    produces:
      - application/json
    parameters:
      - name: user_uuid
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
    try:
        results = es.get(index=search_index, id=user_uuid)
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    return jsonify(results)


@bp.route('/verification/tag/manage', methods=["POST"])
@jwt_required()
def manage_tags():
    """
    Modify the verification tags available in the system
    ---
    tags:
     - verification admin
    produces:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        schema:
          properties:
            moderator_uid:
              type: string
              type: string
              required: true
              description: The uid of the moderator
            actions:
              type: array
              items:
                type: object
                properties:
                  action:
                    type: string
                    enum: ['create', 'edit', 'delete']
                    description: The action to perform
                    required: true
                  uuid:
                    type: string
                    description: The uuid of the tag to modify.  Required for 'edit', 'delete'
                  name:
                    type: string
                    description: The name of the tag to use.  Required for 'create', 'edit'
              description:  The tag changes to make
              required: true
          example:
            moderator_uid: tJMPKzrR4ig3Yejc7cRQGSl8URr1
            actions:
              - action: create
                name: "Need photo"
              - action: update
                name: "ID required"
                uuid: 10386a76-f586-4af2-8fba-a330be31d151
              - action: delete
                uuid: 8087c785-2b86-4a84-90be-ca5b3432e329
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

    if 'moderator_uid' not in request.json:
        return abort(400, 'missing moderator_uid')

    moderator_uid = request.json.get('moderator_uid')

    for a in request.json.get('actions', []):
        action = a.get('action')
        name = a.get('name')
        uuid = a.get('uuid')

        if action == 'create':
            if name is None:
                return abort(400, f'missing name')
            res = create_tag(moderator_uid=moderator_uid, name=name)

        elif action == 'update':
            if uuid is None:
                return abort(400, f'missing uuid')
            if name is None:
                return abort(400, f'missing name')
            res = update_tag(moderator_uid=moderator_uid, uuid=uuid, name=name)

        elif action == 'delete':
            if uuid is None:
                return abort(400, f'missing uuid')
            res = delete_tag(moderator_uid=moderator_uid, uuid=uuid)

        else:
            return abort(400, f'invalid action: {action}')

        if 'error' in res:
            code = res.get('code', 500)
            return jsonify({'error': res['error']}), code

    return jsonify('Tags updated'), 200
