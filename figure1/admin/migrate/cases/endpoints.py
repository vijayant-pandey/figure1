from flask import Blueprint
from flask.json import jsonify
from flask_jwt_extended import jwt_required

from figure1.admin.migrate.cases.tasks import populate_case_queue, migrate_legacy_case, propagate_case_updates, \
    handle_deleted_cases

bp = Blueprint('admin_migrate_cases_endpoint', __name__)


@bp.route('/migrate/legacy/cases/populate_queue')
@jwt_required()
def populate_legacy_case_queue():
    """
    Populates legacy case queue
    Updates q_legacy_case_queue with data needed to determine which legacy cases need updates propagated to pro
    ---
    tags:
     - legacy migration
    produces:
      - application/json
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: Migration task started
        schema:
          properties:
            task_id:
              type: array
              items: []
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    task = populate_case_queue.delay()
    return jsonify({'task_id': task.task_id})


@bp.route('/migrate/legacy/cases/<legacy_id>')
@jwt_required()
def migrate_legacy_case_endpoint(legacy_id):
    """
    Migrate a single legacy case to pro
    ---
    tags:
     - legacy migration
    produces:
      - application/json
    parameters:
      - name: legacy_id
        in: path
        type: string
        required: true
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: Task started
        schema:
          properties:
            task_id:
              type: array
              items: []
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    task = migrate_legacy_case.delay(legacy_id=legacy_id)
    return jsonify({'task_id': task.task_id})


@bp.route('/migrate/legacy/cases/propagate_updates')
@jwt_required()
def propagate_legacy_cases():
    """
    Start a task to propagate legacy cases
    ---
    tags:
     - legacy migration
    produces:
      - application/json
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: Task started
        schema:
          properties:
            task_id:
              type: array
              items: []
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    task = propagate_case_updates.delay()
    return jsonify({'task_id': task.task_id})


@bp.route('/migrate/legacy/cases/handle_deleted_cases')
@jwt_required()
def handle_deleted_cases_endpoint():
    """
    Start a task to handle cases which were deleted in legacy
    Legacy case deletion is handled with a destructive delete from the mongo DB.  Therefore deletions cannot be handled
    during the regular case migration.  Instead, this task iterates through c_legacy_case and updates any case
    which no longer exists in the legacy mongo DB.  Those cases are updated by marking c_case.deleted_at.
    ---
    tags:
     - legacy migration
    produces:
      - application/json
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: Task started
        schema:
          properties:
            task_id:
              type: array
              items: []
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    task = handle_deleted_cases.delay()
    return jsonify({'task_id': task.task_id})
