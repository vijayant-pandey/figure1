import os

from flask import Blueprint
from flask import abort
from flask import current_app
from flask import request
from flask.json import jsonify
from flask_jwt_extended import jwt_required

from figure1.admin.moderation.cases.domain import add_case_edit
from figure1.admin.moderation.cases.domain import add_case_media_edit
from figure1.admin.moderation.cases.domain import add_case_note
from figure1.admin.moderation.cases.domain import add_partner_case_settings
from figure1.admin.moderation.cases.domain import approve_case
from figure1.admin.moderation.cases.domain import approve_reject_case_edit
from figure1.admin.moderation.cases.domain import approve_reject_case_media_edit
from figure1.admin.moderation.cases.domain import flag_case
from figure1.admin.moderation.cases.domain import reject_case
from figure1.admin.moderation.cases.domain import remove_paging_from_case
from figure1.admin.moderation.cases.domain import set_case_labels
from figure1.admin.moderation.cases.domain import set_case_state
from figure1.common.types.case import CaseRejectionReason
from figure1.common.types.case import ModerationCaseEdit
from figure1.configuration import es_settings
from figure1.core import es
from figure1.exceptions import CaseError

bp = Blueprint('pro_moderation_cases_endpoint', __name__)
case_index_alias = es_settings.cases_alias


@bp.app_errorhandler(CaseError)
def handle_case_error(e):
    return jsonify(e.as_dict()), e.rc


@bp.route('/moderation/cases/<case_uuid>/approve', methods=["POST"])
@jwt_required()
def approve_case_endpoint(case_uuid):
    """
    Approve a case that is awaiting moderation
    ---
    tags:
     - moderation
    produces:
      - application/json
    parameters:
      - name: case_uuid
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
              required: true
              description: The uid of the moderator
          example:
            moderator_uid: tJMPKzrR4ig3Yejc7cRQGSl8URr1
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

    res = approve_case(case_uuid=case_uuid,
                       moderator_uid=moderator_uid)

    if 'error' in res:
        code = res.get('code', 500)
        return jsonify({'error': res['error']}), code
    else:
        return jsonify(res), 200


@bp.route('/moderation/cases/<case_uuid>/reject', methods=["POST"])
@jwt_required()
def reject_case_endpoint(case_uuid):
    """
    Reject a case that is awaiting moderation
    ---
    tags:
     - moderation
    produces:
      - application/json
    parameters:
      - name: case_uuid
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
              required: true
              description: The uid of the moderator
            reason:
              type: string
              enum: ['selfie', 'inappropriate_content', 'suspected_homework', 'underage_nudity', 'tineye',
                'delete_no_email', 'need_clinical_info', 'not_direct_care', 'inappropriate_paging',
                'non_clinical_photos', 'unsupported_language']
              required: true
          example:
            moderator_uid: tJMPKzrR4ig3Yejc7cRQGSl8URr1
            reason: need_clinical_info
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
    if 'reason' not in request.json:
        return abort(400, 'missing reason')

    moderator_uid = request.json.get('moderator_uid')
    reason = request.json.get('reason')
    if not isinstance(reason, str):
        return abort(400, f'Reason must be a string: {reason}')
    reason = reason.upper()

    if reason not in [r.name for r in CaseRejectionReason]:
        return abort(400, f'Reason {reason} is not supported')

    res = reject_case(case_uuid=case_uuid,
                      moderator_uid=moderator_uid,
                      reason=CaseRejectionReason[reason])

    if 'error' in res:
        code = res.get('code', 500)
        return jsonify({'error': res['error']}), code
    else:
        return jsonify(res), 200


@bp.route('/moderation/cases/<case_uuid>/flag', methods=["POST"])
@jwt_required()
def flag_case_endpoint(case_uuid):
    """
    Flag a case to be reviewed by a moderation manager
    ---
    tags:
     - moderation
    produces:
      - application/json
    parameters:
      - name: case_uuid
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
              required: true
              description: The uid of the moderator
          example:
            moderator_uid: tJMPKzrR4ig3Yejc7cRQGSl8URr1
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

    res = flag_case(case_uuid=case_uuid, moderator_uid=moderator_uid)

    if 'error' in res:
        code = res.get('code', 500)
        return jsonify({'error': res['error']}), code
    else:
        return jsonify(res), 200


@bp.route('/moderation/cases/<case_uuid>/remove_paging', methods=["POST"])
@jwt_required()
def remove_paging_endpoint(case_uuid):
    """
    remove paging from a case by a moderation manager
    ---
    tags:
     - moderation
    produces:
      - application/json
    parameters:
      - name: case_uuid
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
              required: true
              description: The uid of the moderator
          example:
            moderator_uid: <moderator_uid>
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

    res = remove_paging_from_case(case_uuid=case_uuid, moderator_uid=moderator_uid)
    return jsonify(res), 200


@bp.route('/moderation/cases/<case_uuid>/note', methods=["POST"])
@jwt_required()
def case_note_endpoint(case_uuid):
    """
    Add a moderation note to a case
    ---
    tags:
     - moderation
    produces:
      - application/json
    parameters:
      - name: case_uuid
        in: path
        type: string
        description:
        required: true
      - name: body
        in: body
        required: true
        schema:
          properties:
            moderator_uid:
              type: string
              required: true
              description: The uid of the moderator
            text:
              type: string
              required: true
              description: The contents of the note.
          example:
            moderator_uid: tJMPKzrR4ig3Yejc7cRQGSl8URr1
            text: I think the case may require more details.
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
    if 'text' not in request.json:
        return abort(400, 'missing note text')

    moderator_uid = request.json.get('moderator_uid')
    text = request.json.get('text')

    res = add_case_note(case_uuid=case_uuid,
                        moderator_uid=moderator_uid,
                        text=text)

    if 'error' in res:
        code = res.get('code', 500)
        return jsonify({'error': res['error']}), code
    else:
        return jsonify(res), 200


@bp.route('/moderation/cases/<case_uuid>/edit', methods=["POST"])
@jwt_required()
def add_case_edit_endpoint(case_uuid):
    """
    Submit an edited title, caption, diagnosis or language for a case - this endpoint does not change the state of the
    case.
    ---
    tags:
     - moderation
    produces:
      - application/json
    parameters:
      - name: case_uuid
        in: path
        type: string
        description:
        required: true
      - name: suggested_edit
        in: query
        description: If set, the edit will await approval or rejection from a moderation manager.  Otherwise, the edit
          will be applied immediately.
        required: false
        default: true
      - name: body
        in: body
        required: true
        schema:
          properties:
            moderator_uid:
              type: string
              required: true
              description: The uid of the moderator
            content_uuid:
              type: string
              required: false
              description: The uuid of the case content which should be updated.  If null, the first
                content of the case will be edited.
            title:
              type: string
              required: false
              description: The new title to set.  Null if a change is not required.
            caption:
              type: string
              required: false
              description: The new caption to set.  Null if a change is not required.
            language:
              type: string
              required: false
              description: The new case language to set.  Null if a change is not required.
            diagnosis:
              type: string
              required: false
              description: The new caption to set.  Null if a change is not required.
            case_classification:
              type: enum
              required: false
              description: Case classification, can be medical or nonmedical, null if no change
              values: ['medical', 'nonmedical']
          example:
            moderator_uid: tJMPKzrR4ig3Yejc7cRQGSl8URr1
            content_uuid: ad66b280-0fef-4bdd-b9b9-54d9327f1768
            title: Heart Failure - Optimizing Therapy and Patient Communication
            language: EN_US
            diagnosis:  Edited case diagnosis
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
    edit = ModerationCaseEdit.parse_obj(dict(case_uuid=case_uuid,
                                             suggested_edit=request.args.get('suggested_edit', default=False),
                                             **request.json))
    res = add_case_edit(case_edit=edit)
    return jsonify(res), 200


@bp.route('/moderation/cases/<case_uuid>/edit/media/<media_uuid>/<moderator_uid>', methods=["POST"])
@jwt_required()
def add_case_media_edit_endpoint(case_uuid, media_uuid, moderator_uid):
    """
    Submit an edited image for a case - this endpoint does not change the state of the case
    ---
    tags:
     - moderation
    produces:
      - application/json
    parameters:
      - name: case_uuid
        in: path
        type: string
        description:
        required: true
      - name: media_uuid
        in: path
        type: string
        description:
        required: true
      - name: moderator_uid
        in: path
        type: string
        description:
        required: true
      - name: suggested_edit
        in: query
        type: boolean
        description: If set, the edit will await approval or rejection from a moderation manager.  Otherwise, the edit
          will be applied immediately.
        required: false
      - name: picture
        in: formData
        type: file
        description:
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

    suggested_edit = request.args.get('suggested_edit')
    if suggested_edit:
        if suggested_edit.lower() == 'true':
            suggested_edit = True
        else:
            suggested_edit = False
    else:
        suggested_edit = False
    file = request.files['picture']
    temp_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], moderator_uid)

    res = add_case_media_edit(case_uuid=case_uuid,
                              media_uuid=media_uuid,
                              moderator_uid=moderator_uid,
                              suggested_edit=suggested_edit,
                              file=file,
                              temp_dir=temp_dir)

    if 'error' in res:
        code = res.get('code', 500)
        return jsonify({'error': res['error']}), code
    else:
        return jsonify(res), 200


@bp.route('/moderation/cases/<case_uuid>/edit/<string:action>/<edit_uuid>', methods=["POST"])
@jwt_required()
def approve_reject_case_edit_endpoint(case_uuid, action, edit_uuid):
    """
    Approve or reject a suggested edit to a case - this endpoint does not change the state of the case.
    ---
    tags:
     - moderation
    produces:
      - application/json
    parameters:
      - name: case_uuid
        in: path
        type: string
        description:
        required: true
      - name: edit_uuid
        in: path
        type: string
        description:
        required: true
      - name: action
        in: path
        type: string
        enum: ['approve', 'reject']
        description:
        required: true
      - name: body
        in: body
        required: true
        schema:
          properties:
            moderator_uid:
              type: string
              required: true
              description: The uid of the moderator
          example:
            moderator_uid: tJMPKzrR4ig3Yejc7cRQGSl8URr1
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

    if action not in ['approve', 'reject']:
        return abort(400, f'invalid action: {action}')

    res = approve_reject_case_edit(case_uuid=case_uuid,
                                   moderator_uid=moderator_uid,
                                   edit_uuid=edit_uuid,
                                   action=action)

    if 'error' in res:
        code = res.get('code', 500)
        return jsonify({'error': res['error']}), code
    else:
        return jsonify(res), 200


@bp.route('/moderation/cases/<case_uuid>/edit/<string:action>/media/<edit_uuid>', methods=["POST"])
@jwt_required()
def approve_reject_case_media_edit_endpoint(case_uuid, action, edit_uuid):
    """
    Approve or reject a suggested edit to case media. Note that this endpoint does not change the state of the case.
    ---
    tags:
     - moderation
    produces:
      - application/json
    parameters:
      - name: case_uuid
        in: path
        type: string
        description:
        required: true
      - name: edit_uuid
        in: path
        type: string
        description:
        required: true
      - name: action
        in: path
        type: string
        enum: ['approve', 'reject']
        description:
        required: true
      - name: body
        in: body
        required: true
        schema:
          properties:
            moderator_uid:
              type: string
              required: true
              description: The uid of the moderator
          example:
            moderator_uid: tJMPKzrR4ig3Yejc7cRQGSl8URr1
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

    if action not in ['approve', 'reject']:
        return abort(400, f'invalid action: {action}')

    res = approve_reject_case_media_edit(case_uuid=case_uuid,
                                         moderator_uid=moderator_uid,
                                         media_edit_uuid=edit_uuid,
                                         action=action)

    if 'error' in res:
        code = res.get('code', 500)
        return jsonify({'error': res['error']}), code
    else:
        return jsonify(res), 200


@bp.route("/moderation/cases/search", methods=['POST'])
@jwt_required()
def search_cases():
    """
    Search
    ---
    tags:
      - moderation
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

    try:
        results = es.search(body=search_request, index=case_index_alias, doc_type='_doc')
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    return jsonify(results)


@bp.route("/moderation/cases/search/<case_uuid>", methods=['GET'])
@jwt_required()
def get_search_case(case_uuid):
    """
    Get Case from Elastic
    ---
    tags:
      - moderation
    produces:
      - application/json
    parameters:
      - name: case_uuid
        in: path
        type: string
        description:
        required: true
    responses:
      '200':
        description: Elasticsearch Document
      '404':
        description: Document not found
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
      """

    results = es.get(index=case_index_alias, id=case_uuid)
    return jsonify(results)


@bp.route("/moderation/cases/<case_uuid>/<state>", methods=['POST'])
@jwt_required()
def do_set_case_state(case_uuid, state):
    """
    Set a case to this state
    ---
    tags:
     - moderation
    produces:
      - application/json
    parameters:
      - name: case_uuid
        in: path
        type: string
        description:
        required: true
      - name: state
        in: path
        type: string
        description:
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
    res = set_case_state(case_uuid=case_uuid, state=state)
    return jsonify(res)


@bp.route('/moderation/cases/<case_uuid>/labels', methods=['POST'])
@jwt_required()
def set_case_labels_endpoint(case_uuid):
    """
    Update the case labels for a case
    ---
    tags:
     - moderation
    produces:
      - application/json
    parameters:
      - name: case_uuid
        in: path
        type: string
        description: The case_uuid to update
        required: true
      - name: body
        in: body
        required: true
        schema:
          properties:
            moderator_uid:
              type: string
              required: true
              description: The uid of the moderator
            label_uuids:
              type: array
              items: object
              required: true
              description: The case labels to apply.  Old case labels will be replaced.
          example:
            moderator_uid: tJMPKzrR4ig3Yejc7cRQGSl8URr1
            label_uuids:
              - 3dd905d8-a2ce-4030-a89f-8daa78f8bc9b
              - 30bb2a26-e550-45a1-bdbe-477662521112

    responses:
      default:
        description: Unexpected Failure
      '200':
        description: OK
      '404':
        description: Case or moderator could not be found
      '422':
        description: Case is in an invalid state
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    if 'moderator_uid' not in request.json:
        return abort(422, 'missing moderator_uid')
    if 'label_uuids' not in request.json:
        return abort(422, 'missing label_uuids')

    moderator_uid = request.json.get('moderator_uid')
    label_uuids = request.json.get('label_uuids')

    res = set_case_labels(case_uuid=case_uuid,
                          moderator_uid=moderator_uid,
                          label_uuids=label_uuids)

    return jsonify(res), 200


@bp.route('/moderation/cases/<case_uuid>/partner_settings', methods=['POST'])
@jwt_required()
def update_partner_case_endpoint(case_uuid):
    """
    Update partner cases with some additional settings
    The external_link_url is checked for validity, but not to ensure it points anywhere
    All properties are optional, if they already exist on the case, they will be overwritten. To remove a property,
    set it to the string "delete"
    If external_link_text is added without a url, it is ignored. However if and external_link_url is added with
    no external_link_text, the url is used as link text. To remove both properties, set the external_link_text
    to "delete".
    The case_uuid must exist, however the state is not specifically checked, so this can also be added to approved
    cases.
    ---
    tags:
     - moderation
    produces:
      - application/json
    parameters:
      - name: case_uuid
        in: path
        type: string
        description: The case_uuid to update
        required: true
      - name: body
        in: body
        required: true
        schema:
          properties:
            moderator_uid:
              type: string
              required: true
              description: The uid of the moderator
            external_link_text:
              type: string
              required: false
              description: Set text for external link
            external_link_url:
              type: string
              required: false
              description: Set url for external link
            sponsored_text:
              type: string
              required: false
              description: Set sponsored text
            disclosure_text:
              type: string
              required: false
              description: Set disclosure text
          example:
            moderator_uid: tJMPKzrR4ig3Yejc7cRQGSl8URr1
            external_link_url: "https://www.google.ca"
            external_Link_text: "Click to go to google"
            sponsored_text: "A google case"
            disclosure_text: "Sponsored by google"

    responses:
      default:
        description: Unexpected Failure
      '200':
        description: OK
      '404':
        description: Case or moderator could not be found
      '422':
        description: Case is in an invalid state
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """

    if 'moderator_uid' not in request.json:
        return abort(422, 'missing moderator_uid')

    moderator_uid = request.json.get('moderator_uid')
    res = add_partner_case_settings(case_uuid=case_uuid, moderator_uid=moderator_uid, data=request.json)

    return jsonify(res), 200
