import logging

from flask import Blueprint, request
from flask.json import jsonify
from flask_jwt_extended import jwt_required
from .domain import search_users, search_cases

bp = Blueprint('pro_search_endpoint', __name__)


@bp.route('/search/users', methods=["POST"])
@jwt_required()
def do_search_user():
    """
    Post a search to users index
    ---
    tags:
     - search
    produces:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        schema:
          properties:
            search_term:
              type: string
              required: true
              description: search term
            search_cursor:
              type: integer
              description: starting point for the search - used for scrolling

          example:
            search_term: elbow
            search_cursor: 0
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

    if request.json:
        data = request.json
        search_term = data.get('search_term')
        search_cursor = data.get('search_cursor')
        r = search_users(search_term=search_term, search_cursor=search_cursor)
        if 'error' in r:
            return jsonify(r), 500
        else:
            return jsonify(r), 200
    else:
        return jsonify({}), 422


@bp.route('/search/cases', methods=["POST"])
@jwt_required()
def do_search_cases():
    """
    Post a search to a case index
    ---
    tags:
     - search
    produces:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        schema:
          properties:
            search_term:
              type: string
              required: true
              description: search term
            search_cursor:
              type: integer
              description: starting point for the search - used for scrolling
            search_index:
              type: array
              items: string
              description: The is the feed_uuid to search
            search_user_uid:
              type: string
              required: true
              description: The uid of the user performing the search
          example:
            search_term: elbow
            search_user_uid: <some uid>
            search_cursor: 0
            search_index:
              - <feed_type_uuid>
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

    if request.json:
        data = request.json
        search_term = data.get('search_term')
        search_cursor = data.get('search_cursor')
        search_index = data.get('search_index', [])
        search_user_uid = data.get('search_user_uid', "")
        r = search_cases(search_term=search_term,
                         search_cursor=search_cursor,
                         search_index=search_index,
                         user_uid=search_user_uid)
        if 'error' in r:
            return jsonify(r), 500
        else:
            return jsonify(r), 200
    else:
        return jsonify({}), 422
