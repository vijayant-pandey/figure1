import logging

from flask import Blueprint, request, redirect
from flask_jwt_extended import jwt_required

from figure1.pro.legacy.domain import get_pro_case_link

bp = Blueprint('pro_legacy_endpoint', __name__)


@bp.route('/legacy/case_redirect', methods=["POST"])
@jwt_required()
def legacy_case_redirect():
    """
    Redirect a legacy case link to the pro case equivalent.
    Redirects to RFY is the case link is invalid or unsupported.
    ---
    tags:
     - cases
    produces:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        schema:
          properties:
            url:
              type: string
              description: The legacy url
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

    url = request.json.get('url')

    link = get_pro_case_link(legacy_link=url)
    return redirect(link, code=301)
