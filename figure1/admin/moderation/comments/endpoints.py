from flask import Blueprint
from flask import abort
from flask import request
from flask.json import jsonify
from flask_jwt_extended import jwt_required

from figure1.admin.moderation.comments.domain import approve_comment
from figure1.admin.moderation.comments.domain import flag_comment
from figure1.admin.moderation.comments.domain import reject_comment
from figure1.admin.moderation.comments.domain import set_comments_reviewed_status
from figure1.common.types import CommentRejectionReason
from figure1.configuration import es_settings
from figure1.core import es
from figure1.exceptions import AcceptedAnswerError

bp = Blueprint('pro_moderation_comments_endpoint', __name__)


def _populate_comment_case(comment_search_result=None, comment_doc=None):
    """
    Given a comment document, find the case_uuid, get the case, and attach it to a case key
    :param case_uuids:
    :return:
    """

    def _append_search_results(doc, result):
        case = result.get('_source')
        doc['_source'].update(dict(case=case))
        return doc['_source']

    case_uuids = []
    if comment_search_result:

        for item in comment_search_result.get('hits').get('hits'):
            cu = item.get('_source', {}).get('case').get('caseUuid')
            if cu is not None and cu not in case_uuids:
                case_uuids.append(cu)
        if not case_uuids:
            return comment_search_result

    elif comment_doc is not None:
        cu = comment_doc.get('_source', {}).get('case').get('caseUuid')
        if cu is not None and cu not in case_uuids:
            case_uuids.append(cu)
        if not case_uuids:
            return comment_doc
    else:
        raise ValueError("Required arguments not passed")

    resp = es.mget(index=es_settings.cases_alias, body={"ids": case_uuids})

    if comment_search_result:
        for idx, doc in enumerate(zip(comment_search_result.get('hits', {}).get('hits', []), resp.get('docs'))):
            upd = _append_search_results(*doc)
            comment_search_result['hits']['hits'][idx]['_source'] = upd
        return comment_search_result
    elif comment_doc:
        return _append_search_results(doc=comment_doc, result=resp['docs'][0])


@bp.errorhandler(AcceptedAnswerError)
def insufficient_permissions(e):
    return jsonify(e.as_dict()), e.rc


@bp.route('/moderation/comments/<comment_uuid>/approve', methods=["POST"])
@jwt_required()
def approve_comment_endpoint(comment_uuid):
    """
    Approve and republish a comment
    ---
    tags:
     - moderation
    produces:
      - application/json
    parameters:
      - name: comment_uuid
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
              required: false
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

    res = approve_comment(comment_uuid=comment_uuid,
                          moderator_uid=moderator_uid)

    if 'error' in res:
        code = res.get('code', 500)
        return jsonify({'error': res['error']}), code
    else:
        return jsonify(res), 200


@bp.route('/moderation/comments/<comment_uuid>/reject', methods=["POST"])
@jwt_required()
def reject_comment_endpoint(comment_uuid):
    """
    Reject and delete a comment
    ---
    tags:
     - moderation
    produces:
      - application/json
    parameters:
      - name: comment_uuid
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
              enum: ['disrespectful_patient', 'privacy_issue', 'personal_question_comment', 'disrespectful_user',
                'unsupported', 'promotional', 'unprofessional', 'unsupported_language', 'treatment_reference',
                'off_topic', 'no_email']
              required: true
          example:
            moderator_uid: tJMPKzrR4ig3Yejc7cRQGSl8URr1
            reason: unprofessional
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
    reason = request.json.get('reason')
    if not isinstance(reason, str):
        return abort(400, f'Reason must be a string: {reason}')
    reason = reason.upper()

    if reason not in [r.name for r in CommentRejectionReason]:
        return abort(400, f'Reason {reason} is not supported')

    res = reject_comment(comment_uuid=comment_uuid,
                         moderator_uid=moderator_uid,
                         reason=CommentRejectionReason[reason])

    if 'error' in res:
        code = res.get('code', 500)
        return jsonify({'error': res['error']}), code
    else:
        return jsonify(res), 200


@bp.route('/moderation/comments/<comment_uuid>/flag', methods=["POST"])
@jwt_required()
def flag_comment_endpoint(comment_uuid):
    """
    Flag a comment to be reviewed by a moderation manager
    ---
    tags:
     - moderation
    produces:
      - application/json
    parameters:
      - name: comment_uuid
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

    res = flag_comment(comment_uuid=comment_uuid, moderator_uid=moderator_uid)

    if 'error' in res:
        code = res.get('code', 500)
        return jsonify({'error': res['error']}), code
    else:
        return jsonify(res), 200


@bp.route("/moderation/comments/search", methods=['POST'])
@jwt_required()
def search_comments():
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
        results = es.search(body=search_request, index=es_settings.comments_alias, doc_type='_doc')
        merged = _populate_comment_case(comment_search_result=results.copy())
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    return jsonify(merged)


@bp.route("/moderation/comments/search/<comment_uuid>", methods=['GET'])
@jwt_required()
def get_search_comment(comment_uuid):
    """
    Get Comment from Elastic
    ---
    tags:
      - moderation
    produces:
      - application/json
    parameters:
      - name: comment_uuid
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
        results = es.get(index=es_settings.comments_alias, id=comment_uuid)
        orig = _populate_comment_case(comment_doc=results)
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    return jsonify(orig)


@bp.route("/moderation/comments/review", methods=['POST'])
@jwt_required()
def set_comments_reviewed_status_endpoint():
    """
    Review accepted answers.
    ---
    tags:
    - moderation
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
            comment_uuids:
              type: array
              items: object
              required: true
              description: The comments to apply.
            status:
              type: string
              items: object
              required: true
              description: status; reviewed or pending_review
          example:
            moderator_uid: tJMPKzrR4ig3Yejc7cRQGSl8URr1
            comment_uuids:
              - 3dd905d8-a2ce-4030-a89f-8daa78f8bc2b
              - 30bb2a26-e550-45a1-bdbe-477662525112
            status: reviewed

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
        return abort(422, 'missing moderator_uid')
    if 'comment_uuids' not in request.json:
        return abort(422, 'missing comment_uuids')

    if 'status' not in request.json:
        return abort(422, 'missing status')

    moderator_uid = request.json.get('moderator_uid')
    comment_uuids = request.json.get('comment_uuids')
    status = request.json.get('status')

    if status not in ('reviewed', 'pending_review'):
        return abort(400, f'Invalid status')

    res = set_comments_reviewed_status(moderator_uid=moderator_uid,
                                       comment_uuids=comment_uuids,
                                       status=status)

    return jsonify(res), 200
