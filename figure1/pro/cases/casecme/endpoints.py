from flask import Blueprint, request, abort, make_response
from flask.json import jsonify
from flask_jwt_extended import jwt_required

from .casecme import create_new_question_set
from .casecme import submit_user_case_cme_answers
from .casecme import update_questions

bp = Blueprint('pro_case_cme_endpoint', __name__)


@bp.route('/cme/case/sync/<question_set_uuid>', methods=['GET'])
@jwt_required()
def sync_case_cme_questions_endpoint(question_set_uuid):
    """Syncs questions to firestore
    ---
    tags:
     - admin
    produces:
      - application/json
    parameters:
      - name: question_set_uuid
        in: path
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
    update_questions(question_set_uuid=question_set_uuid)
    return jsonify({}), 200


@bp.route('/admin/create_question_set', methods=['POST'])
@jwt_required()
def create_new_question_set_endpoint():
    """Creates or modifies a set of questions

    Add a new set of questions.

    A set of questions is a map of questions and answers that allow for arbitrary paths through. For example, question
    1 may have two answers, if answer 1 is selected, the next question might be question 3, if answer 2 is selected,
    the next question might be question 5. The next_question field on the question object should be considered the
    default, next question entries from the answers should override it.

    If there is no next_question on either the question object or the selected answer, it should be considered the last
    question in the set.

    If a question label is referenced that isn't in the body, the link is not created. The match is a simple text match.

    Display order is set on three levels, once for the question, once for the answer_group and once for the answer.
    This isn't explicitly enforced as a required field, but the frontend will not know how to display them if it is
    not set.

    A question type is a hint for the frontend, but it is not enforced on the backend. Essentially, a radio question
    type indicates there should only be one answer per answer group, a checkboxlist means there can be multiple
    answers per answer group, and freeform indicates the user must write in something, so there is only one answer
    group and one answer.

    An answer_group is a selection of answers that can be multi-selected, each answer group is mutually exclusive
    meaning that you cannot select an answer from more than one answer group.

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
          properties:
            question_set_label:
              type: string
              required: true
              description: This is a human readable reference for the set of questions - it is not exposed otherwise
            questions:
              type: array
              items:
                type: object
                properties:
                  question_type:
                    type: enum
                    options: ['freeform', 'radio', 'checkboxlist']
                    required: true
                    description: Type of question, freeform is a text box, radio only allows one answer,
                      checkboxlist allows for multi-select as well as mutually exclusive, and freeform answers
                  question_text:
                    type: string
                    required: true
                  question_label:
                    type: string
                  display_order:
                    type: number
                  next_question_label:
                    type: string
                    description: Default next question label, can be overridden by answer next question
                  answer_groups:
                    type: array
                    items:
                      type: object
                      properties:
                        answer_group_display_order:
                          type: int
                        answer_group_heading:
                          type: str
                        answers:
                          type: array
                          items:
                            type: object
                            properties:
                              answer_text:
                                type: string
                              answer_suggested_text:
                                type: string
                              next_question_label:
                                type: string
                              answer_display_order:
                                type: int
                              answer_has_extra_input:
                                type: bool
          example:
            question_set_label: Name of question set
            questions: [
                {
                    "question_text": "A question",
                    "question_type": "checkboxlist",
                    "question_label": "q1",
                    "display_order": 1,
                    "answer_groups": [
                    {
                        "answer_group_display_order": 1,
                        "answer_group_heading": "Heading for this group",
                        "answers": [
                            {
                            "answer_text": "first answer option",
                            "answer_display_order": 1,
                            "next_question_label": "q2"
                            },
                            {
                             "answer_text": "second answer option",
                             "answer_display_order": 2,
                             "next_question_label": "q2"
                             }
                        ]
                    },
                    {
                        "answer_group_display_order": 2,
                        "answer_group_heading": "Heading for second group",
                        "answers": [
                            {
                            "answer_text": "third answer",
                            "answer_display_order": 1,
                            "next_question_label": "q2"
                            }
                        ]
                    }
                    ]
                },

                {
                    "question_text": "Question 2",
                    "question_type": "freeform",
                    "question_label": "q2",
                    "display_order": 2,
                    "answer_groups": [
                    {
                        "answer_group_display_order": 1,
                        "answer_group_heading": "This is another group",
                        "answers": [
                        {
                            "answer_text": "this is an answer",
                            "answer_display_order": 1,
                            "answer_suggested_text": "Type this for example",
                        }
                        ]
                    }
                    ]
                }
            ]
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
    request_data = request.json
    a = create_new_question_set(request_data)
    return jsonify(a.dict()), 200


@bp.route('/cme/case/<case_uuid>/submit', methods=['POST'])
@jwt_required()
def submit_user_answer_endpoint(case_uuid):
    """Submit user answers to questions for case CMEs

    Takes a list of one or more questions and answers.
    ---
    tags:
     - admin
    produces:
      - application/json
    parameters:
      - name: case_uuid
        in: path
        required: true
      - name: body
        in: body
        required: true
        schema:
          properties:
            degree_type:
              type: enum
              items: ['M.D.', 'D.O.']
              description: Type of degree for this user

            user_uid:
              type: string
              required: true
              description: The user_uid submitting the question
            questions:
              type: array
              items:
                type: object
                properties:
                  question_uuid:
                    type: string
                    required: true
                  answer_uuid:
                    type: string
                    required: false
                  answer_text:
                    type: string
                    required: false

          example:
            user_uid: 'user uid string'
            questions: [{
                "question_uuid": "uuid of the question being answered",
                "answer_uuid": "The uuid of the answer, not applicable for free-form answers",
                "answer_text": "The text of a free form answer"
                }
            ]
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
    req = request.json
    user_uid = req.get('user_uid')
    questions = req.get('questions', [])
    degree_type = req.get('degree_type', 'M.D.')
    submit_user_case_cme_answers(user_uid=user_uid, case_uuid=case_uuid, questions=questions, degree_type=degree_type)
    return jsonify({})
