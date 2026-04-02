import logging
from typing import List

from dogpile.cache.api import NO_VALUE
from flask import Blueprint
from flask import abort
from flask import jsonify
from flask import request
from flask_httpauth import HTTPTokenAuth
from flask_jwt_extended import jwt_required

from figure1.cache_config import cache_region
from figure1.common.iterable import IterableSupportedWebHooks
from figure1.common.iterable import IterableWebHookBase
from figure1.exceptions.reference import CommunicationSettingNotFound
from .communications import email_subscribe
from .communications import get_differentials
from .domain import create_api_user
from .domain import get_case_by_uuid
from .domain import get_new_case_by_user
from .domain import get_rfy_data_feed
from .domain import get_valid_token
from .domain import push_to_user_update_queue
from .domain import update_user_subscriptions
from .recommended_datafeed import get_recommended

bp = Blueprint('api_endpoint', __name__)
auth = HTTPTokenAuth()
logger = logging.getLogger('figure1.api')


@bp.errorhandler(CommunicationSettingNotFound)
def handle_communication_setting_not_found(e):
    logger.exception("Communication setting not found %s", e.msg)
    return e.as_dict(), e.return_code


def verify_token(token):
    """
    Verify the token is valid, return True if valid, False if not
    :param token:
    :return:
    """
    ob = get_valid_token(token)
    if ob:
        return ob.as_dict()
    return NO_VALUE


@bp.before_request
def check_auth_headers():
    if not request.headers.get('x-api-key'):
        abort(401)
    api_key = request.headers.get('x-api-key')
    k = cache_region.get_or_create(key=api_key, creator=get_valid_token, creator_args=((api_key,), {}))
    if k is NO_VALUE or k is None:
        abort(401)


@bp.route('/create/apiuser', methods=['POST'])
@jwt_required()
def create_user():
    """
    Create an api user token
    ---
    tags:
     - api
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

    r = create_api_user()
    return jsonify(r), 200


@bp.route('/iterable/update', methods=['POST'])
@bp.route('/unsubscribe', methods=['POST'])
def handle_iterable_webhooks():
    """
    This handles webhooks sent from iterable
    ---
    tags:
     - api
    produces:
      - application/json

    responses:
      default:
        description: Unexpected Failure
      '200':
        description: OK
    securityDefinitions:
      API:
        type: apiKey
        name: Authorization
        in: header
    security:
      - API: []
    """
    content: IterableWebHookBase = IterableWebHookBase.parse_obj(request.json)
    if content.eventName == IterableSupportedWebHooks.emailSend.value:
        push_to_user_update_queue(iterable_data=content)
    else:
        update_user_subscriptions(iterable_data=content)
    return jsonify(content.dict()), 200


@bp.route('/iterable/feed/recommended/<user_uuid>', methods=['GET'])
def get_recommended_for_you_endpoint(user_uuid):
    """
    Iterable recommended for you datafeed. Returns 10 items.
    ---
    tags:
     - api
    produces:
      - application/json
    parameters:
      - name: user_uuid
        in: path
        type: string
        required: true
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: OK
    securityDefinitions:
      API:
        type: apiKey
        name: Authorization
        in: header
    security:
      - API: []
    """

    data = get_rfy_data_feed(user_uuid=user_uuid)
    return jsonify(data), 200


@bp.route('/iterable/feed/weekly/<user_uuid>', methods=['GET'])
def get_weekly_case_recommendation(user_uuid):
    """
    Iterable weekly case recommendation. Returns 1 case.
    ---
    tags:
     - api
    produces:
      - application/json
    parameters:
      - name: user_uuid
        in: path
        type: string
        required: true
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: OK
    securityDefinitions:
      API:
        type: apiKey
        name: Authorization
        in: header
    security:
      - API: []
    """

    data = get_recommended(user_uuid=user_uuid)
    return jsonify(data), 200


@bp.route('/iterable/feed/new/<user_uuid>', methods=['GET'])
def get_new_case_recommendation(user_uuid):
    """
    Iterable new case recommendation. Returns 1 case.
    ---
    tags:
     - api
    produces:
      - application/json
    parameters:
      - name: user_uuid
        in: path
        type: string
        required: true
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: OK
    securityDefinitions:
      API:
        type: apiKey
        name: Authorization
        in: header
    security:
      - API: []
    """

    data = get_new_case_by_user(user_uuid=user_uuid)
    return jsonify(data), 200


@bp.route('/iterable/feed/<case_uuid>', methods=['GET'])
def get_case_by_uuid_endpoint(case_uuid):
    """
    Given a case_uuid, return it. Returns 404 if the case cannot be found or is in the wrong state.
    ---
    tags:
     - api
    produces:
      - application/json
    parameters:
      - name: case_uuid
        in: path
        type: string
        required: true
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: OK
    securityDefinitions:
      API:
        type: apiKey
        name: Authorization
        in: header
    security:
      - API: []
    """

    case = get_case_by_uuid(case_uuid=case_uuid)
    if case:
        return jsonify(case), 200
    else:
        abort(404)


@bp.route('/communication/list_differentials', methods=['GET'])
def get_differential_list_endpoint():
    """
    Gets a list of the available differentials
    ---
    tags:
     - api
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
    res = list(get_differentials())
    return jsonify({"differentials": res})


@bp.route('/communication/subscribe', methods=['POST'])
def communication_subscribe_endpoint():
    """
    Subscribe an email address to a list of communication settings

    Supports subscribing users and non-users.  If a user is subscribed, their user_communication_settings are updated.
    If a non-user is subscribed we don't store this data, instead they're only subbed in iterable.
    ---
    tags:
     - api
    produces:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        schema:
          properties:
            email:
              type: string
              description:  The email of the user that is subscribing
              required: true
            communication_uuids:
              type: array
              items:
                type: string
              description:  The communication_uuid of the settings to subscribe to
              required: true
          example:
            email: test@figure1.com
            communication_uuids:
                - 7e2a2aac-629e-444e-8668-b8eaaf75171e
                - 8bc8a7e8-7c85-43dd-8c4d-3da5e1f8ccd9
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
    if 'email' not in request.json:
        return abort(422, 'missing email')
    if 'communication_uuids' not in request.json:
        return abort(422, 'missing communication_uuids')

    email = request.json.get('email')
    communication_uuids = request.json.get('communication_uuids')
    if isinstance(communication_uuids, List):
        uuid_list = communication_uuids
    elif isinstance(communication_uuids, str):
        uuid_list = [x.strip() for x in communication_uuids.split(',')]
    else:
        return abort(422, 'Invalid format for communication_uuids')

    email_subscribe(email=email, communication_uuids=uuid_list)
    return jsonify({'success': 'User subscribed'})
