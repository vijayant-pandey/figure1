from flask import Blueprint, request
from flask.json import jsonify
from flask_jwt_extended import jwt_required
from figure1.common.types import ScreenTrackingData
from figure1.exceptions.tracking import TrackingException
from figure1.notifications import log_registration_activity_task
from figure1.notifications import log_case_draft_task
from figure1.common.iterable import update_iterable_user
from .domain import handle_views

bp = Blueprint('pro_tracking_endpoint', __name__)


@bp.errorhandler(TrackingException)
def handle_untracked_screen_error(e):
    return jsonify(e.as_dict()), e.rc


@bp.route('/tracking/<user_uid>', methods=['POST'])
@jwt_required()
def track_user_screen(user_uid):
    """
        Handle user events from registration or case creation
        ---
        tags:
         - tracking
        produces:
          - application/json
        parameters:
          - name: user_uid
            in: path
            required: true
            type: string
          - name: body
            in: body
            required: true
            schema:
              properties:
                screen_id:
                  type: string
                  description: The uid for the user submitting the action
                case_data:
                  type: object
                  properties:
                    title:
                      type: string
                      description: Draft case title
                    caption:
                      type: string
                      description: Draft case caption

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

    tracking_data: ScreenTrackingData = ScreenTrackingData.parse_obj(request.json)

    if tracking_data.caseDraftData:
        log_case_draft_task.delay(data=tracking_data, user_uid=user_uid)

    else:
        task = log_registration_activity_task.si(
            user_uid=user_uid,
            screen_id=tracking_data.screenId
        )
        task.link(update_iterable_user.si(user_uid=user_uid))
        task.apply_async()

    return jsonify({}), 200


@bp.route('/tracking/start/<user_uid>', methods=['GET'])
@jwt_required()
def track_user_session_start_endpoint(user_uid):
    """
    User active
    Endpoint that is hit when a user logs in or otherwise indicates they are currently active.
    ---
    tags:
     - tracking
    produces:
      - application/json
    parameters:
      - name: user_uid
        in: path
        required: true
        type: string
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
    return jsonify({}), 200


@bp.route('/tracking/last_seen/<user_uid>', methods=['GET'])
@bp.route('/tracking/last_seen/<user_uid>/screen/<screen_id>', methods=['GET'])
@jwt_required()
def track_last_seen(user_uid, screen_id=None):
    """
    Handle user last seen events
    ---
    tags:
     - tracking
    produces:
      - application/json
    parameters:
      - name: user_uid
        in: path
        required: true
        type: string
      - name: screen_id
        in: path
        required: false
        type: string
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
    return jsonify({}), 200


@bp.route('/tracking/feed_views/<user_uid>', methods=['POST'])
@jwt_required()
def handle_feed_views_endpoint(user_uid):
    """
    Handle user feed views
    ---
    tags:
     - tracking
    produces:
      - application/json
    parameters:
      - name: user_uid
        in: path
        required: true
        type: string
      - name: body
        in: body
        required: true
        schema:
          properties:
            views:
                description: Case views for a given feed
                type: array
                items: object
                properties:
                    feedTypeUuid:
                      type: string
                      required: true
                      description: feed uuid
                    caseUuids:
                      type: array
                      items: string
                      required: true
                      description: List of 1 or more case_uuids considered viewed

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
    handle_views(user_uid=user_uid, feed_data=request.json, detail_views=False)
    return jsonify({}), 200


@bp.route('/tracking/detail_views/<user_uid>', methods=['POST'])
@jwt_required()
def handle_case_detail_views_endpoint(user_uid):
    """
    Handle case detail views by user
    ---
    tags:
     - tracking
    produces:
      - application/json
    parameters:
      - name: user_uid
        in: path
        required: true
        type: string
      - name: body
        in: body
        required: true
        schema:
          properties:
            caseUuids:
              type: array
              required: true
              items: string
              description: List of 1 or more case_uuids
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
    handle_views(user_uid=user_uid, feed_data=request.json, detail_views=True)
    return jsonify({}), 200
