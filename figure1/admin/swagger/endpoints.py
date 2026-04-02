from flask import Blueprint, current_app
from flask.json import jsonify
from flask_jwt_extended import jwt_required, create_access_token, decode_token
from jwt import ExpiredSignatureError, InvalidSignatureError
from figure1.common.models.db import BackendToken
from datetime import timedelta
import logging

from figure1.common.token_rotator import validate_token

logger = logging.getLogger(__name__)
bp = Blueprint('admin_api_auth', __name__)


@bp.route("/protected", methods=["GET"])
@jwt_required()
def protected():
    """
    Protected content method.
    ---
    tags:
      - auth
    description: Protected content method. Can not be seen without valid token.
    responses:
      200:
        description: User successfully accessed the content.
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    resp = jsonify({"protected": " - you saw me!"})
    resp.status_code = 200
    return resp


@bp.route("/fetch", methods=["GET"])
def fetch():
    """
    User authenticate method.
    ---
    tags:
      - auth
    description: Authenticate user with supplied credentials.
    responses:
      200:
        description: User successfully logged in.
      400:
        description: User login failed.
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """

    token = BackendToken.get_text_token()
    if validate_token(_token=token):
        resp = jsonify({"token": token})
        resp.headers.extend({'jwt-token': token})
        return resp
    else:
        with current_app.app_context():
            token = create_access_token(identity="figure1-firebase",
                                        expires_delta=timedelta(seconds=3200))
            if validate_token(_token=token):
                logger.info("Token validated")
                resp = jsonify({"Token generated": token})
                resp.headers.extend({'jwt-token': token})
                resp.headers.extend({'Authorized': 'Bearer ' + token})
                return resp
    return jsonify({'error': 'Failed to generate valid tokens'})
