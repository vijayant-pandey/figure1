import os

from flask import Blueprint, request, abort, current_app
from flask.json import jsonify
from flask_jwt_extended import jwt_required

from figure1.admin.migrate.users.domain import upload_specialty_mapping
from figure1.admin.migrate.users.tasks import populate_user_queue, migrate_legacy_user, propagate_user_updates, \
    migrate_communication_preferences, migrate_saved_cases

bp = Blueprint('admin_users_endpoint', __name__)


@bp.route('/migrate/legacy/users/upload_specialty_mapping', methods=['POST'])
@jwt_required()
def upload_specialty_mapping_endpoint():
    """
    Uploads a csv file to create legacy specialty mappings

    The expected csv structure is:
    <legacy_profession:str>
    <legacy_specialty:str>
    <pro_category:str>
    <pro_profession:str>
    <pro_specialty:str>
    <pro_subspecialty:str>
    ---
    tags:
     - legacy migration
    produces:
      - application/json
    parameters:
      - name: specialty_map
        in: formData
        description:  The specialty csv file
        type: file
        required: true
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
    if 'specialty_map' not in request.files:
        abort(400)

    file = request.files['specialty_map']
    save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'legacy_specialty_map.csv')
    if os.path.isfile(save_path):
        os.unlink(save_path)
    file.save(save_path)

    upload_specialty_mapping(filename=save_path)
    return jsonify({'success': 'updated'})


@bp.route('/migrate/legacy/users/populate_queue')
@jwt_required()
def populate_legacy_user_queue():
    """
    Populates legacy user queue
    Unlike the scheduled task, this endpoint syncs all legacy users instead of just recently updated users.
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
    task = populate_user_queue.delay(all_users=True)
    return jsonify({'task_id': task.task_id})


@bp.route('/migrate/legacy/users/propagate_updates')
@jwt_required()
def propagate_legacy_users():
    """
    Start a task to propagate legacy users
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
    task = propagate_user_updates.delay()
    return jsonify({'task_id': task.task_id})


@bp.route('/migrate/legacy/users/<legacy_id>')
@jwt_required()
def migrate_legacy_user_endpoint(legacy_id):
    """
    Migrate a single legacy user to pro
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
    task = migrate_legacy_user.delay(legacy_id=legacy_id, force=True)
    return jsonify({'task_id': task.task_id})


@bp.route('/migrate/legacy/users/communication_preferences')
@jwt_required()
def migrate_communication_preferences_endpoint():
    """
    Start a task to update the communication preferences for unmigrated users

    Does not sync users to iterable, only sets requires_iterable_sync=True if needed
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
    task = migrate_communication_preferences.delay()
    return jsonify({'task_id': task.task_id})


@bp.route('/migrate/legacy/users/saved_cases')
@jwt_required()
def migrate_saved_cases_endpoint():
    """
    Start a task to update the saved cases for legacy users
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
    task = migrate_saved_cases.delay()
    return jsonify({'task_id': task.task_id})
