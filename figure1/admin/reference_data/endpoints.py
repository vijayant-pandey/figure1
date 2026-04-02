from tempfile import NamedTemporaryFile
import logging
from flask import Blueprint, jsonify, current_app, request, abort, send_file, make_response
from flask_jwt_extended import jwt_required
import os
from celery.result import EagerResult
from .load_blocked_usernames import load_bad_words

from .tasks_notifications import load_communication_groups_from_csv, \
    load_communication_settings_from_csv

from .load_public_taxonomy_data import update_public_specialty_taxonomy, \
    map_tree_uuid, \
    run_tax_map, \
    get_taxonomy_map, \
    delete_taxonomy_map
from figure1.admin.reference_data import ReferenceDataTasks

bp = Blueprint('admin_reference_data_endpoint', __name__)
logger = logging.getLogger(__name__)


@bp.route('/referencedata/taxonomy/automap', methods=['GET'])
@jwt_required()
def run_automap_endpoint():
    """
    Attempts to map taxonomy to specialty tree. Does not overwrite.

    ---
    tags:
     - admin
    produces:
      - application/json
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
    run_tax_map()
    return jsonify({}), 200


@bp.route('/referencedata/taxonomy', methods=['GET'])
@jwt_required()
def show_taxonomy_map_endpoint():
    """
    Shows the mapping of taxonomy code to specialty

    Returns either a csv or a json structure
    ---
    tags:
     - admin
    produces:
      - text/csv
      - application/json
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

    if str(request.accept_mimetypes) == 'text/csv':
        final = []
        has_header = False
        for resp in get_taxonomy_map():
            if not has_header:
                final.append(','.join(list(dict(resp).keys())))
                has_header = True
            final.append(','.join(list(dict(resp).values())))
        response = make_response("\n".join(final))
        response.mimetype = 'text/csv'
        return response
    else:
        return jsonify(dict(items=list(get_taxonomy_map())))


@bp.route('/referencedata/taxonomy/map', methods=['DELETE', 'POST', 'PUT'])
@jwt_required()
def modify_specialty_taxonomy_map_endpoint():
    """
    Adds, removes or modifies a taxonomy to tree_uuid mapping
    POST - May only add a new mapping, returns an error if the mapping exists
    PUT - Modifies or adds a new mapping, the taxonomy code is used for duplicate detection
    DELETE - Deletes by the taxonomy code

    ---
    tags:
     - admin
    produces:
      - application/json
    parameters:
      - name: taxonomy_code
        in: query
        type: string
        description: Mapping to modify
        required: true
      - name: specialty_tree_uuid
        in: query
        type: string
        description: Tree uuid to map to, only required for POST/PUT
        required: false
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
    taxonomy_code = request.args.get('taxonomy_code')
    specialty_tree_uuid = request.args.get('specialty_tree_uuid')
    if request.method == 'DELETE':
        delete_taxonomy_map(taxonomy_code=taxonomy_code)
    elif request.method == 'POST':
        map_tree_uuid(taxonomy_code=taxonomy_code, tree_uuid=specialty_tree_uuid)
    elif request.method == 'PUT':
        map_tree_uuid(taxonomy_code=taxonomy_code, tree_uuid=specialty_tree_uuid, force=True)
    return jsonify({}), 200


@bp.route('/referencedata/public/taxonomy', methods=['GET'])
@jwt_required()
def load_public_taxonomy_endpoint():
    """
    Load a new taxonomy version - does not overwrite

    Look for the version here
    https://www.nucc.org/index.php/code-sets-mainmenu-41/provider-taxonomy-mainmenu-40/csv-mainmenu-57
    Then use the version number without the dots, for example Version 21.0 becomes 210
    If no number is passed, version 210 is used.
    ---
    tags:
     - admin
    produces:
      - application/json
    parameters:
      - name: version
        in: query
        type: string
        description: Version to load
        required: false
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
    version = request.args.get('version')
    try:
        version = int(version)
    except TypeError:
        version = 210
    if version <= 89 or version >= 300:
        version = 210
    r = update_public_specialty_taxonomy(version=version)
    return jsonify(r), 200


@bp.route('/referencedata/comm/settings/update', methods=['POST'])
@jwt_required()
def update_communication_settings():
    """
        Upload a csv file to add or update communication settings - the groups included must be added first
        Make sure the headers are deleted, there is no attempt made to strip the headers.

        ---
        tags:
         - admin
        produces:
          - application/json
        parameters:
          - name: communication_settings
            in: formData
            description:  The media to upload
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
    if 'communication_settings' not in request.files:
        abort(400)

    file = request.files['communication_settings']
    save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'communication_settings')
    if os.path.isfile(save_path):
        os.unlink(save_path)
    file.save(save_path)
    load_communication_settings_from_csv(filename=save_path)
    return jsonify({}), 200


@bp.route('/referencedata/comm/groups/update', methods=['POST'])
@jwt_required()
def update_communication_group_settings():
    """
    Upload a csv file to add communication groups

    ---
    tags:
     - admin
    produces:
      - application/json
    parameters:
      - name: communication_groups
        in: formData
        description:  The media to upload
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
    if 'communication_groups' not in request.files:
        abort(400)

    file = request.files['communication_groups']
    save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'communication_groups')
    if os.path.isfile(save_path):
        os.unlink(save_path)
    file.save(save_path)
    load_communication_groups_from_csv(filename=save_path)
    return jsonify({}), 200


@bp.route('/referencedata/blockedusernames', methods=['POST'])
@jwt_required()
def update_blocked_usernames():
    """
    Csv file to update blocked words in the following form:
    Header
    <forbidden_word>, <disallowed_word,

    Forbidden words are blocked when part of other words as well as on their own. Disallowed words are only blocked
    when they are not part of another word.
    ---
    tags:
     - admin
    produces:
      - application/json
    parameters:
      - name: usernames_file
        in: formData
        description:  The bad words to upload
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

    if 'usernames_file' not in request.files:
        abort(400)
    usernames_file = request.files['usernames_file']
    save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'usernames_file')
    if os.path.isfile(save_path):
        os.unlink(save_path)
    usernames_file.save(save_path)
    load_bad_words(filename=save_path)
    return jsonify({}), 200


@bp.route('/referencedata/sync/<task>', methods=['POST'])
@jwt_required()
def sync_reference_data(task=None):
    """
    Primarily pushes data into firestore from the database. In some cases, an elasticsearch index is also rebuilt.
    If the clean attribute is set, then the collection is wiped or data is synced using merge=False

    ---
    tags:
     - admin
    produces:
      - application/json
    parameters:
      - name: task
        in: path
        description:  The name of the task to run
        type: string
        required: true
        enum: ['specialties',
            'feed_types',
            'labels',
            'locales',
            'schools',
            'notifications',
            'countries',
            'standalone_emails',
            'topics',
            'promotion_channels',
            'groups']
      - name: clean
        in: query
        description: Optionally drop old reference data before reloading - defaults to false
        type: bool
        required: false
      - name: synchronous
        in: query
        description: Optionally force a task to run synchronously
        type: bool
        required: false

    responses:
      default:
        description: Unexpected Failure
      '404':
        description: Task unknown or no task name passed
      '200':
        description: Task complete
      '202':
        description: Sync task started
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

    clean_data = request.args.get('clean', False)
    force_synchronous = request.args.get('synchronous', False)
    if force_synchronous == 'true':
        force_synchronous = True
    else:
        force_synchronous = False

    if clean_data == 'true':
        clean_data = True
    else:
        clean_data = False
    if task:
        if task in ReferenceDataTasks.__members__:
            t = ReferenceDataTasks[task].value
            if force_synchronous:
                resp: EagerResult = t.apply(kwargs={'clean': clean_data})
                return jsonify(dict(result=resp.result, status=resp.status)), 200
            else:
                task_id = t.apply_async(kwargs={'clean': clean_data})
                return jsonify(dict(task_id=task_id.id)), 202
        else:
            abort(404)
    abort(404)
