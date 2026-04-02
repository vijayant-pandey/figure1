import os

from flask import Blueprint
from flask import current_app
from flask import request
from flask.json import jsonify
from flask_jwt_extended import jwt_required

from figure1.common.iterable import generate_iterable_user_object
from figure1.common.iterable import sync_deleted_users_to_iterable_task
from figure1.common.iterable import sync_user_to_iterable
from figure1.common.iterable.api import IterableAPI
from figure1.exceptions import IterableException
from .domain import add_channel
from .domain import parse_csv
from .domain import sync_deleted_users

bp = Blueprint('iterable_admin_api', __name__)


@bp.errorhandler(IterableException)
def handle_iterable_exception(err):
    return jsonify(err.as_dict()), err.rc


@bp.route('/iterable/sync_deleted_users', methods=['GET'])
@jwt_required()
def run_sync_deleted_iterable_users():
    """
    Start a task to ensure the users in iterable are correctly deleted
    ---
    tags:
      - Iterable Control API
    description: Iterable Control API
    responses:
      200:
        description: Iterable Profiles are being updated
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    sync_deleted_users_to_iterable_task.apply_async()
    return jsonify({}), 202


@bp.route('/iterable/<user_uuid>', methods=['GET'])
@jwt_required()
def get_iterable_user_profiles(user_uuid):
    """
    Given a user uuid, show what would be sent to iterable. Does not actually send anything
    ---
    tags:
      - Iterable Control API
    description: Iterable Control API
    parameters:
       - in: path
         name: user_uuid
         required: true
         type: string
    responses:
      200:
        description: Iterable Profiles are being updated
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    u = generate_iterable_user_object(user_uuid=user_uuid)
    return jsonify(u.dict()), 200


@bp.route("/iterable/update/<user_uuid>", methods=["GET"])
@jwt_required()
def update_iterable_profiles(user_uuid):
    """
    Given a user uuid, update this user in iterable, This call is synchronous.
    ---
    tags:
      - Iterable Control API
    description: Iterable Control API
    parameters:
      - in: path
        name: user_uuid
        required: true
        type: string
    responses:
      200:
        description: Iterable Profiles are being updated
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    sync_user_to_iterable(user_uuid=user_uuid)

    return jsonify({'message': 'success'}), 200


@bp.route("/iterable/channel/add/<channel_id>", methods=["POST"])
@jwt_required()
def add_channel_setting_endpoint(channel_id):
    """
        This adds a channel to communication settings so it can be unsubscribed from. This is not visible to the user.

        Required is a channel_id, the communication_uuid is returned. If the channel already exists, that uuid is
        returned

        ---
        tags:
         - Iterable Control API
        parameters:
          - in: path
            name: channel_id
            required: true
            type: integer
          - name: body
            in: body
            required: true
            schema:
              properties:
                name:
                  type: string
                  required: true
              example:
                name: "Channel name"
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
    channel_id = int(channel_id)
    channel_name = request.json.get('name', '')
    resp = add_channel(channel_id=channel_id, channel_name=channel_name)
    return jsonify(resp), 200


@bp.route("/iterable/channel/unsub", methods=["POST"])
@jwt_required()
def unsub_user_channel_endpoint():
    """
        Upload a csv file of email addresses to unsubscribe from a channel.

        The form is <email>,<channel_uuid>,<channel_id>

        One of communication_uuid or channel_id is required, but not both.

        ---
        tags:
         - Iterable Control API
        produces:
          - application/json
        parameters:
          - name: csvupload
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
    file = request.files['csvupload']
    save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'csvupload')
    if os.path.isfile(save_path):
        os.unlink(save_path)
    file.save(save_path)
    resp = parse_csv(filename=save_path)
    return jsonify(resp), 200


@bp.route("/iterable/deleted/sync", methods=['GET'])
@jwt_required()
def sync_deleted_users_endpoint():
    """
       Ensures that users are unsubscribed from all channels

        ---
        tags:
         - Iterable Control API
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
    sync_deleted_users()
    return jsonify({}), 200


@bp.route("/iterable/channel/unsub/all/<email>", methods=["GET"])
@jwt_required()
def unsub_user_channel_all_endpoint(email):
    """
       Unsubscribes a user from all channels

        ---
        tags:
         - Iterable Control API
        produces:
          - application/json
        parameters:
          - name: email
            in: path
            description: email address
            type: string
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
    api = IterableAPI()
    resp = api.unsubscribe_user_from_all_channels(email=email)
    return jsonify(resp.dict()), 200
