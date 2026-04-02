from flask import Blueprint, abort, request, make_response
from flask.json import jsonify
from flask_jwt_extended import jwt_required

from figure1.common.firebase import do_firebase_sync
from figure1.common.types import FirebaseAction
from figure1.common.token_rotator import run_token_rotator_task

bp = Blueprint('pro_admin_tools_endpoint', __name__)


@bp.route('/tools/firebase_sync', methods=["POST"])
@jwt_required()
def firebase_sync():
    """
    Creates do_firebase_sync tasks
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
            firebase_model:
              type: string
              required: true
              description: The firebasemodel to sync
            uuids:
              type: array
              items:
                type: string
              required: true
              description: The uuids of the documents to sync
            action:
              type: string
              enum: ["SET", "DELETE"]
              description: The type of firebase action to perform
            merge:
              type: boolean
              description: Sets the merge value to use on the firebase operation
          example:
            firebase_model: 'model_name'
            uuids: ['8ff09ad0-886d-4930-ac59-eca9a1926a06']
            action: 'SET'
            merge: true
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
    if 'firebase_model' not in request.json:
        return abort(400, 'missing firebase_model')
    if 'uuids' not in request.json:
        return abort(400, 'missing uuids')

    firebase_model = request.json.get('firebase_model')
    uuids = request.json.get('uuids')
    action = request.json.get('action', 'SET').upper()
    merge = request.json.get('merge', True)

    task_ids = []
    for uuid in uuids:
        t = do_firebase_sync.delay(uuid=uuid,
                                   firebasemodel=firebase_model,
                                   action=FirebaseAction[action],
                                   merge=merge)
        task_ids.append(t.task_id)

    return make_response(jsonify({'task_ids': task_ids}), 202)


@bp.route('/tools/rotate_token', methods=['POST'])
@jwt_required()
def trigger_token_rotation():
    """
    Manually trigger the JWT token rotation task
    
    ---
    tags:
     - Backend Tools
    produces:
      - application/json
    responses:
      default:
        description: Unexpected Failure
      '202':
        description: Token rotation task started
        schema:
          properties:
            task_id:
              type: string
              description: The Celery task ID
            message:
              type: string
              description: Success message
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    try:
        task = run_token_rotator_task.delay()
        return jsonify({
            'task_id': task.id,
            'message': 'Token rotation task started successfully'
        }), 202
    except Exception as e:
        logger.error(f"Failed to trigger token rotation: {e}")
        return jsonify({'error': 'Failed to trigger token rotation'}), 500
