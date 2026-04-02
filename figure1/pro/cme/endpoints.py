import logging
from flask import Blueprint
from flask.json import jsonify
from flask_jwt_extended import jwt_required

from figure1.exceptions import S3Error, CaseError
from figure1.pro.cme.domain import get_cme_activities

bp = Blueprint('pro_cme_endpoint', __name__)
logger = logging.getLogger(__name__)


@bp.app_errorhandler(CaseError)
def handle_case_error(e):
    logger.exception("%s", e.msg)
    return jsonify(e.as_dict()), e.rc


@bp.route('/cme/activities/<user_uid>', methods=['GET'])
@jwt_required()
def get_cme_activities_endpoint(user_uid):
    """
    Gets a user's CME activities and pushes them to firestore
    ---
    tags:
     - cme
    produces:
      - application/json
    parameters:
      - name: user_uid
        in: path
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
    res = get_cme_activities(user_uid)
    return jsonify(res), 200
