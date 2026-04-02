from flask import Blueprint, request, abort
from flask.json import jsonify
from celery.canvas import Signature

from figure1.pro.cases.quiz.domain import submit_quiz_selection, reset_quiz

bp = Blueprint('pro_cases_questions_endpoint', __name__)


@bp.route('/quiz/<content_uuid>/submit', methods=["POST"])
def submit_quiz_selection_endpoint(content_uuid):
    """
    Submit a user's selection to a quiz question.
    A uid is always required, but for ungated content, it will be anonymous.
    ---
    tags:
     - quiz
    produces:
      - application/json
    parameters:
      - name: force_synchronous
        in: query
        description: Set to force synchronous execution
        required: false
        type: boolean
      - name: content_uuid
        in: path
        type: string
        description:  The content_uuid of the quiz that is being answered
        required: true
      - name: body
        in: body
        required: true
        schema:
          properties:
            user_uid:
              type: string
              required: True
              description: The uid of the user submitting the quiz option selection
            option_uuid:
              type: string
              required: True
              description: The question_option_uuid of the quiz option that was selected
            free_form_text:
              type: string
              required: False
              description: The user's response (for free-form text questions only)
          example:
            user_uid: tJMPKzrR4ig3Yejc7cRQGSl8URr1
            option_uuid: 6b49b4dc-4220-41fa-8ef0-2e48749733a0
            free_form_text:  Free form response, only for free form questions.
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: OK
      '404':
        description: User or content uuid not found

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
    if 'option_uuid' not in request.json:
        return abort(400, 'missing option_uuid')

    user_uid = request.json.get('user_uid')
    option_uuid = request.json.get('option_uuid')
    free_form_text = request.json.get('free_form_text')
    force_synchronous = request.args.get("force_synchronous")
    resp = submit_quiz_selection(user_uid=user_uid,
                                 content_uuid=content_uuid,
                                 option_uuid=option_uuid,
                                 free_form_text=free_form_text)
    task = resp.pop('task')
    if not isinstance(task, Signature):
        return jsonify({'error', 'No task returned'})
    if force_synchronous == "true":
        task.apply()
    else:
        task.apply_async()
    return jsonify({}), 200


@bp.route('/quiz/<content_uuid>/reset', methods=["POST"])
def reset_quiz_endpoint(content_uuid):
    """
    Reset a user's quiz selection
    ---
    tags:
     - quiz
    produces:
      - application/json
    parameters:
      - name: content_uuid
        in: path
        type: string
        description:  The content_uuid of the quiz that is being reset
        required: true
      - name: body
        in: body
        required: true
        schema:
          properties:
            user_uid:
              type: string
              required: True
              description: The uid of the user
          example:
            user_uid: tJMPKzrR4ig3Yejc7cRQGSl8URr1
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
    if 'user_uid' not in request.json:
        return abort(400, 'missing user_uid')

    user_uid = request.json.get('user_uid')

    res = reset_quiz(user_uid=user_uid,
                     content_uuid=content_uuid)

    if 'error' in res:
        code = res.get('code', 500)
        return jsonify({'error': res['error']}), code
    else:
        return jsonify(res), 200
