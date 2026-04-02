from datetime import datetime
from flask import Blueprint, request, abort
from flask.json import jsonify
from flask_jwt_extended import jwt_required

from .domain import set_mesh_terms, \
    remove_mesh_terms, \
    set_specialties, \
    remove_specialties, \
    approve_mesh_terms, \
    flag_case_for_moderator, \
    reject_flagged_case, \
    force_set_case_state, \
    clean_mesh_terms, \
    find_publications_for_case

from .mesh_tasks import fetch_mesh_tags_task

bp = Blueprint('moderation_tagging', __name__)


@bp.route('/moderation/tagging/<case_uuid>/publications', methods=['GET'])
@jwt_required()
def get_publications_for_case_endpoint(case_uuid):
    """
    Looks for publications for a case, does not search for mesh terms if they are missing.
    ---
    tags:
     - moderation
    parameters:
     - in: path
       name: case_uuid
       required: true
       type: array
       items:
        type: string
    produces:
     - application/json
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: Set case specialties
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
     """

    find_publications_for_case(case_uuid=case_uuid)
    return jsonify({}), 200


@bp.route('/moderation/tagging/<case_uuid>/clean_mesh', methods=['GET'])
@jwt_required()
def clean_mesh_terms_endpoint(case_uuid):
    """
    Cleans mesh terms on an existing approved case
    ---
    tags:
     - moderation
    parameters:
     - in: path
       name: case_uuid
       required: true
       type: array
       items:
        type: string
    produces:
     - application/json
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: Set case specialties
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
     """

    r = clean_mesh_terms(case_uuid=case_uuid)
    return jsonify(r), 200


@bp.route('/moderation/tagging/<case_uuid>/specialties', methods=['POST'])
@jwt_required()
def update_case_specialties(case_uuid):
    """
    Add or remove Specialties
    This route handles adding and removing case specialties

    ---
    tags:
     - moderation
    parameters:
     - in: path
       name: case_uuid
       required: true
       type: string
     - in: body
       name: specialties
       schema:
         properties:
           remove:
             type: array
             items:
               type: string
           set:
             type: array
             items:
               type: string
         example:
           set:
             - f5138d5b-9a5a-4467-ac0b-fc356d82ae62
           remove:
             - f5138d5b-9a5a-4467-ac0b-fc356d82ae62
    produces:
     - application/json
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: Set case specialties
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
     """

    if not request.is_json:
        return abort(400, 'missing json body')

    data = request.json
    set_specialties_data = data.get('set')
    remove_specialties_data = data.get('remove')
    set_resp = {}
    rem_resp = {}
    if set_specialties_data:
        set_resp = set_specialties(specialties=set_specialties_data, case_uuid=case_uuid)
    if remove_specialties_data:
        rem_resp = remove_specialties(specialties=remove_specialties_data, case_uuid=case_uuid)
    if 'error' in set_resp:
        return jsonify(set_resp), 400
    if 'error' in rem_resp:
        return jsonify(rem_resp), 400
    return jsonify(set_resp, rem_resp)


@bp.route('/moderation/tagging/<case_uuid>/mesh', methods=['POST'])
@jwt_required()
def update_case_mesh_terms(case_uuid):
    """
    Add or remove mesh terms
    This route handles adding and removing mesh terms

    ---
    tags:
     - moderation
    parameters:
     - in: path
       name: case_uuid
       type: string
       required: true
     - in: body
       name: mesh_terms
       schema:
         properties:
           remove:
             type: array
             items:
               type: string
           set:
             type: array
             items:
               type: string
         example:
           set:
             - f5138d5b-9a5a-4467-ac0b-fc356d82ae62
           remove:
             - f5138d5b-9a5a-4467-ac0b-fc356d82ae62
    produces:
     - application/json
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: Set case mesh terms
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
     """

    if not request.is_json:
        return abort(400, 'missing json body')

    data = request.json
    set_mesh_terms_data = data.get('set')
    remove_mesh_terms_data = data.get('remove')
    set_resp = {}
    rem_resp = {}
    if set_mesh_terms_data:
        set_resp = set_mesh_terms(mesh_terms=set_mesh_terms_data, case_uuid=case_uuid)
    if remove_mesh_terms_data:
        rem_resp = remove_mesh_terms(mesh_terms=remove_mesh_terms_data, case_uuid=case_uuid)
    if 'error' in set_resp:
        return jsonify(set_resp), 400
    if 'error' in rem_resp:
        return jsonify(rem_resp), 400
    return jsonify(set_resp, rem_resp)


@bp.route('/moderation/tagging/<case_uuid>/mesh/approve', methods=['POST'])
@jwt_required()
def approve_case_mesh_terms(case_uuid):
    """
    Approve Case Mesh terms
    This route handles approving mesh terms
    Passing in a publish_date is optional, if it is set in the future, then the case will not appear in the feed until
    this date.

    ---
    tags:
     - moderation
    parameters:
     - in: path
       name: case_uuid
       type: string
       required: true
     - in: body
       name: approve-mesh
       schema:
         properties:
           moderator_uid:
             type: string
           publish_date:
             type: string
             required: false
             description: The date that you want this case to appear in the 'YYYY-MM-DD' form.
         example:
           moderator_uid: <uid string>
    produces:
     - application/json
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: Approve mesh terms
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
     """

    if not request.is_json:
        return abort(400, 'missing json body')

    data = request.json
    moderator_uid = data.get('moderator_uid')
    publish_date = data.get('publish_date', None)
    if not moderator_uid:
        return abort(400, 'Moderator UID is required')

    if publish_date:
        try:
            publish_date = datetime.strptime(publish_date, '%Y-%m-%d')
        except ValueError:
            return jsonify({'error': 'Datetime format invalid'}), 422

        set_resp = approve_mesh_terms(case_uuid=case_uuid, moderator_uid=moderator_uid, publish_date=publish_date)
    else:
        set_resp = approve_mesh_terms(case_uuid=case_uuid, moderator_uid=moderator_uid)
    if 'error' in set_resp:
        return jsonify(set_resp), 400
    return jsonify(set_resp), 200


@bp.route('/moderation/tagging/<case_uuid>/flag', methods=['POST'])
@jwt_required()
def flag_case_for_review(case_uuid):
    """
    Flag a case for review

    ---
    tags:
     - moderation
    parameters:
     - in: path
       name: case_uuid
       type: string
       required: true
     - in: body
       name: flag
       schema:
         properties:
           moderator_uid:
             type: string
           note:
             type: string
         example:
           moderator_uid: <uid string>
           note: <Why case is flagged - this is optional>
    produces:
     - application/json
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: Case has been flagged
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
     """

    if not request.is_json:
        return abort(400, 'missing json body')

    data = request.json
    moderator_uid = data.get('moderator_uid')
    note = data.get('note')
    if not moderator_uid:
        return abort(400, 'Moderator UID is required')
    set_resp = flag_case_for_moderator(case_uuid=case_uuid, moderator_uid=moderator_uid, case_note=note)
    if 'error' in set_resp:
        return jsonify(set_resp), 400
    return jsonify(set_resp), 200


@bp.route('/moderation/tagging/<case_uuid>/reject', methods=['POST'])
@jwt_required()
def do_reject_flagged_case(case_uuid):
    """
    Reject a flagged case back to moderators queue.

    ---
    tags:
     - moderation
    parameters:
     - in: path
       name: case_uuid
       type: string
       required: true
     - in: body
       name: flag
       schema:
         properties:
           moderator_uid:
             type: string
           note:
             type: string
         example:
           moderator_uid: <uid string>
           note: <Why case is rejected - optional>
    produces:
     - application/json
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: Flagged case has been rejected
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
     """

    if not request.is_json:
        return abort(400, 'missing json body')

    data = request.json
    moderator_uid = data.get('moderator_uid')
    note = data.get('note')
    if not moderator_uid:
        return abort(400, 'Moderator UID is required')
    set_resp = reject_flagged_case(case_uuid=case_uuid, moderator_uid=moderator_uid, case_note=note)
    if 'error' in set_resp:
        return jsonify(set_resp), 400
    return jsonify(set_resp), 200


@bp.route('/moderation/tagging/<case_uuid>/state/update', methods=['POST'])
@jwt_required()
def do_force_pass_mesh(case_uuid):
    """
    This endpoint modifies the tag to PENDING_TAGGING regardless of the state of mesh

    ---
    tags:
     - moderation
    parameters:
     - in: path
       name: case_uuid
       type: string
       required: true
     - in: body
       name: state update
       schema:
         properties:
           moderator_uid:
             type: string
         example:
           moderator_uid: <uid string>
    produces:
     - application/json
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: Case state updated to PENDING_TAGGING
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
     """

    if not request.is_json:
        return abort(400, 'missing json body')

    data = request.json
    moderator_uid = data.get('moderator_uid')
    if not moderator_uid:
        return abort(400, 'Moderator UID is required')
    set_resp = force_set_case_state(case_uuid=case_uuid)
    if 'error' in set_resp:
        return jsonify(set_resp), 400
    return jsonify(set_resp), 200


@bp.route('/moderation/tagging/<case_uuid>/mesh/submit/<force>', methods=['POST'])
@jwt_required()
def do_submit_case_for_mesh(case_uuid, force):
    """
    Send a case uuid through mesh
    This endpoint allows for directly submitting a case_uuid for mesh. If it fails, it will not be retried,
    if it succeeds, the state will change to PENDING_TAGGING.
    The force boolean makes it actually hit the mesh api regardless of the mesh execution environment, this isn't
    necessary in production environments, but may be in order to reproduce issues in dev environments.

    ---
    tags:
     - moderation
    parameters:
     - in: path
       name: force
       required: true
       type: boolean
     - in: path
       name: case_uuid
       required: true
       type: string
    produces:
     - application/json
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: Case submitted
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
     """
    force = True if force == 'true' else False
    result = fetch_mesh_tags_task.apply(kwargs=dict(case_uuid=case_uuid, force=force))
    r = result.get()
    return jsonify(r), 200
