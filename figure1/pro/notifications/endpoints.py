import logging

from flask import Blueprint
from flask import request
from flask import abort
from flask.json import jsonify
from flask_jwt_extended import jwt_required
from jsonschema import ValidationError

from figure1.common.models.validator import Validate
from figure1.exceptions import NotificationException
from figure1.exceptions.notification import InvalidDeviceLanguage
from figure1.pro.notifications.domain import handle_update_tokens_and_sync
from figure1.pro.notifications.domain import update_user_communication_preferences
from figure1.pro.notifications.domain import reset_user_preferences
from figure1.pro.notifications.domain import sync_user_communication_preferences
from figure1.pro.notifications.domain import get_default_preferences
from figure1.pro.notifications.domain import sync_user_notifications
from figure1.pro.notifications.domain import mark_user_notifications_acknowledged
from figure1.pro.notifications.domain import mark_single_user_notification_acknowledged
from figure1.pro.notifications.domain import handle_update_user_device_notification_and_sync
from figure1.pro.notifications.domain import mark_single_user_notification_read
from figure1.pro.notifications.domain import mark_user_notifications_read

bp = Blueprint('pro_notifications_endpoint', __name__)
logger = logging.getLogger(__name__)


@bp.errorhandler(NotificationException)
def handle_notification_error(e):
    logger.exception("%s", e.msg)
    return jsonify(e.as_dict()), e.rc


@bp.errorhandler(InvalidDeviceLanguage)
def handle_invalid_device_language_error(e):
    logger.exception("%s", e.msg)
    return jsonify(e.as_dict()), e.rc


@bp.route('/notification/preferences/defaults', methods=["GET"])
@jwt_required()
def get_default_notification_preferences():
    """
    Get default preferences
        ---
        tags:
         - notifications
        produces:
          - application/json
        responses:
          default:
            description: Unexpected Failure
          '200':
            description: Scheduled Preferences for Refresh including Defaults
        securityDefinitions:
          JWT:
            type: apiKey
            name: Authorization
            in: header
        security:
          - JWT: []
    """
    return jsonify(get_default_preferences()), 200


@bp.route('/notification/tokens/<user_uid>', methods=["POST"])
@jwt_required()
def update_tokens(user_uid):
    """
       Populates the Firebase Cloud Tokens for each device for a user
       ---
       tags:
        - notifications
       parameters:
          - in: path
            name: user_uid
            required: true
            type: string
            description: The User UID for the Tokens to Update
          - in: body
            name: body
            required: true
            example:
              devices:
                - device_id: dev1
                  device_type: android
                  fcm_token: token string 1
                  device_language: 'pt'
                - device_id: dev2
                  device_type: ios
                  fcm_token: token string 2
                  device_language: 'pt'
       produces:
         - application/json
       responses:
         default:
           description: Unexpected Failure
         '200':
           description: Saved User's FCM Notifications
       securityDefinitions:
         JWT:
           type: apiKey
           name: Authorization
           in: header
       security:
         - JWT: []
       """

    v = Validate()
    try:
        v.validate(json_data=request.json, json_schema='user_devices')
    except ValidationError as ve:
        logging.error(f'Validation failed to load the Device Matrix for User, user_uid=={user_uid}: {ve}')
        return abort(422, f'Invalid request body')

    # Read the body from the Request
    device_tokens = request.json.get('devices')
    res = handle_update_tokens_and_sync(device_user_tokens=device_tokens, user_uid=user_uid)
    return jsonify(res), 200


@bp.route('/notification/device/<user_uuid>', methods=["POST"])
@jwt_required()
def update_user_device_notification(user_uuid):
    """
       Sync device notification settings for a user
       ---
       tags:
        - notifications
       parameters:
          - in: path
            name: user_uuid
            required: true
            type: string
            description: The User UUID for device to update.
          - in: body
            name: body
            required: true
            example:
              device:
                device_id: dev1
                device_type: android
                fcm_token: token string 1
              notification_enabled: true
       produces:
         - application/json
       responses:
         default:
           description: Unexpected Failure
         '200':
           description: success
       securityDefinitions:
         JWT:
           type: apiKey
           name: Authorization
           in: header
       security:
         - JWT: []
       """
    if 'notification_enabled' not in request.json:
        return abort(422, 'Missing notification_enabled.')

    if 'device' not in request.json:
        return abort(422, 'Missing device.')

    v = Validate()
    try:
        v.validate(json_data=request.json, json_schema='user_device')
    except ValidationError as ve:
        logging.error(f'Validation failed to load the Device Matrix for User, user_uid=={user_uuid}: {ve}')
        return abort(422, f'Invalid request body')

    device = request.json.get('device')
    notification_enabled = request.json.get('notification_enabled')
    res = handle_update_user_device_notification_and_sync(device=device,
                                                          notification_enabled=notification_enabled,
                                                          user_uuid=user_uuid)
    return jsonify(res), 200


@bp.route('/notification/preferences/<user_uid>', methods=["GET"])
@jwt_required()
def refresh_user_notifications_preferences(user_uid):
    """
        Requests a Refresh of Preferences to Firestore

        Populates the User's Preferences in Firebase based on saved backend
        copy of preferences. If new defaults or types have been created since
        last invocation those will also be computed and pushed back to Firestore
        ---
        tags:
         - notifications
        parameters:
           - in: path
             name: user_uid
             required: true
             type: string
             description: The User UID for Preferences to Update
        produces:
          - application/json
        responses:
          default:
            description: Unexpected Failure
          '200':
            description: Scheduled Preferences for Refresh including Defaults
        securityDefinitions:
          JWT:
            type: apiKey
            name: Authorization
            in: header
        security:
          - JWT: []
    """
    res = sync_user_communication_preferences(user_uid=user_uid)
    return jsonify(res), 200


@bp.route('/notification/preferences/<user_uid>', methods=["POST"])
@jwt_required()
def update_user_notifications_preferences(user_uid):
    """
        Updates a User's Notification Preferences

        Given a setting uuid, apply this for the user, the list
        ---
        tags:
         - notifications
        parameters:
           - in: path
             name: user_uid
             required: true
             type: string
             description: The User UID for Preferences to Update
           - in: body
             name: body
             required: true
             example:
               preferences:
                 - communication_uuid: <uuid>
                   setting: true

        produces:
          - application/json
        responses:
          default:
            description: Unexpected Failure
          '200':
            description: Preferences Updated
        securityDefinitions:
          JWT:
            type: apiKey
            name: Authorization
            in: header
        security:
          - JWT: []
    """

    provided_preferences = request.json.get('preferences')
    res = update_user_communication_preferences(user_uid=user_uid, preference_list=provided_preferences)
    return jsonify(res), 200


@bp.route('/notification/preferences/<user_uid>', methods=["DELETE"])
@jwt_required()
def reset_user_notification_preferences(user_uid):
    """
        Resets the User's notification preferences

        Resets the User's notification preferences back to their defaults and pushes
        the fully reset preferences back to the Firestore collection for that user.
        ---
        tags:
         - notifications
        parameters:
           - in: path
             name: user_uid
             required: true
             type: string
             description: The User UID for Preferences to Update
        produces:
          - application/json
        responses:
          default:
            description: Unexpected Failure
          '200':
            description: Scheduled Preferences for Refresh including Defaults
        securityDefinitions:
          JWT:
            type: apiKey
            name: Authorization
            in: header
        security:
          - JWT: []
    """

    res = reset_user_preferences(user_uid=user_uid)
    return jsonify(res), 200


@bp.route('/email/preferences/<user_uid>', methods=["POST"])
@jwt_required()
def do_set_email_preferences(user_uid):
    """
        Set Users email preferences

        Takes a list of email_uuids and whether it is enabled or now
        ---
        tags:
         - disabled
        parameters:
           - in: path
             name: user_uid
             required: true
             type: string
             description: The User UID for to update email preferences for
           - in: body
             name: body
             required: true
             example:
               preferences:
                 - email_uuid: ucau1
                   enabled: true
                 - email_uuid: ucau2
                   enabled: false

        produces:
          - application/json

        responses:
          default:
            description: Unexpected Failure
          '200':
            description: Scheduled Preferences for Refresh including Defaults
        securityDefinitions:
          JWT:
            type: apiKey
            name: Authorization
            in: header
        security:
          - JWT: []
    """

    return jsonify({}), 200


@bp.route('/activity/<user_uid>', methods=["GET", "POST"])
@jwt_required()
def sync_user_notifications_endpoint(user_uid):
    """
       Syncs activity center user notifications for a user
        ---
        tags:
         - notifications
        parameters:
           - in: path
             name: user_uid
             required: true
             type: string
             description: The User UID to sync user notifications for
        produces:
          - application/json
        responses:
          default:
            description: Unexpected Failure
          '200':
            description: Scheduled a refresh of Activity Center for a User
        securityDefinitions:
          JWT:
            type: apiKey
            name: Authorization
            in: header
        security:
          - JWT: []
    """
    if request.method == 'POST':
        res = mark_user_notifications_read(user_uid=user_uid)
        return jsonify(res), 200
    elif request.method == 'GET':
        res = sync_user_notifications(user_uid=user_uid)
        return jsonify(res), 200
    else:
        return jsonify({}), 422


@bp.route('/activity/<user_uid>/acknowledged', methods=["POST"])
@jwt_required()
def mark_user_notifications_acknowledged_endpoint(user_uid):
    """
        Marks all activity center user notifications for a user as acknowledged
        ---
        tags:
         - notifications
        parameters:
           - in: path
             name: user_uid
             required: true
             type: string
             description: The User UID whose notifications will be marked as acknowledged
        produces:
          - application/json
        responses:
          default:
            description: Unexpected Failure
          '200':
            description: Acknowledged all activity center notifications for user
        securityDefinitions:
          JWT:
            type: apiKey
            name: Authorization
            in: header
        security:
          - JWT: []
    """

    res = mark_user_notifications_acknowledged(user_uid=user_uid)
    return jsonify(res), 200


@bp.route('/activity/<user_uid>/read', methods=["POST"])
@jwt_required()
def mark_user_notifications_read_endpoint(user_uid):
    """
        Marks all activity center user notifications for a user as read
        ---
        tags:
         - notifications
        parameters:
           - in: path
             name: user_uid
             required: true
             type: string
             description: The User UID whose notifications will be marked as read
        produces:
          - application/json
        responses:
          default:
            description: Unexpected Failure
          '200':
            description: Read all activity center notifications for user
        securityDefinitions:
          JWT:
            type: apiKey
            name: Authorization
            in: header
        security:
          - JWT: []
    """

    res = mark_user_notifications_read(user_uid=user_uid)
    return jsonify(res), 200


@bp.route('/activity/<user_uid>/acknowledged/<notification_uuid>', methods=["POST"])
@jwt_required()
def mark_single_user_notification_acknowledged_endpoint(user_uid, notification_uuid):
    """
        Marks a single activity center user notifications as acknowledged
        ---
        tags:
         - notifications
        parameters:
           - in: path
             name: user_uid
             required: true
             type: string
             description: The User UID who is marking the notification as acknowledged
           - in: path
             name: notification_uuid
             required: true
             type: string
             description: The UUID of the notification to mark as acknowledged
        produces:
          - application/json
        responses:
          default:
            description: Unexpected Failure
          '200':
            description: Acknowledged a single activity center user notification
        securityDefinitions:
          JWT:
            type: apiKey
            name: Authorization
            in: header
        security:
          - JWT: []
    """

    res = mark_single_user_notification_acknowledged(user_uid=user_uid, notification_uuid=notification_uuid)
    return jsonify(res), 200


@bp.route('/activity/<user_uid>/read/<notification_uuid>', methods=["POST"])
@jwt_required()
def mark_single_user_notification_read_endpoint(user_uid, notification_uuid):
    """
        Marks a single activity center user notification as read
        ---
        tags:
         - notifications
        parameters:
           - in: path
             name: user_uid
             required: true
             type: string
             description: The User UID who is marking the notification as read
           - in: path
             name: notification_uuid
             required: true
             type: string
             description: The UUID of the notification to mark as read
        produces:
          - application/json
        responses:
          default:
            description: Unexpected Failure
          '200':
            description: Read a single activity center user notification
        securityDefinitions:
          JWT:
            type: apiKey
            name: Authorization
            in: header
        security:
          - JWT: []
    """

    res = mark_single_user_notification_read(user_uid=user_uid, notification_uuid=notification_uuid)
    return jsonify(res), 200
