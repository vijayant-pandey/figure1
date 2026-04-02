import logging
import json
from flask import Blueprint, request, abort, make_response
from flask.json import jsonify
from flask_jwt_extended import jwt_required

from figure1.core import managed_session
from figure1.common.models.db import PromotionMethods
from psycopg2 import IntegrityError
from figure1.common.elasticsearch import update_promotions, legacy_case_list_update as case_list_update, \
    update_moderation_case_detail

bp = Blueprint('explorer_cases', __name__)


@bp.route('/promotion/channel/<channel_uuid>', methods=['DELETE'])
@jwt_required()
def delete_channel(channel_uuid):
    """
    Delete Channel
    ---
    tags:
      - promotion
    parameters:
      - name: channel_uuid
        in: path
        type: string
        required: true
    responses:
      '200':
        description: Channel Deleted
        schema:
          deleted: string
      '400':
        description: Channel uuid in use by another promotion
        schema:
          error: string
      default:
        description: Failed to delete promotion
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    try:
        PromotionMethods().delete_channel(channel_uuid=channel_uuid)
    except IntegrityError as ie:
        return make_response(jsonify({'error': "This channel uuid is in use by other promotions - delete these first"}),
                             400)
    except Exception as e:
        return make_response(jsonify({'error': str(e)}))
    return make_response(jsonify({'deleted': channel_uuid}), 200)


@bp.route('/promotion/<promotion_uuid>', methods=['DELETE'])
@jwt_required()
def delete_promotion(promotion_uuid):
    """
    Delete Promotion
    ---
    tags:
      - promotion
    parameters:
      - name: promotion_uuid
        in: path
        type: string
        required: true
    responses:
      '200':
        description: Promotion Deleted
        schema:
          deleted: string
      default:
        description: Failed to delete promotion
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    try:
        pr = PromotionMethods().get_promotion(promotion_uuid=promotion_uuid)
        case_list = []
        for c in pr['cases']:
            case_list.append(c['case_id'])
        if case_list:
            case_list_update.delay(case_id_list=case_list)
        PromotionMethods().delete_promotion(promotion_uuid=promotion_uuid)
    except Exception as e:
        abort(500, "Failed to delete Promotion")
    return jsonify({'deleted': promotion_uuid})


@bp.route('/promotion/<promotion_uuid>/<case_id>', methods=['DELETE'])
@jwt_required()
def delete_case(promotion_uuid, case_id):
    """
    Delete Promotion
    ---
    tags:
      - promotion
    parameters:
      - name: promotion_uuid
        in: path
        type: string
        required: true
      - name: case_id
        in: path
        type: string
        required: true
    responses:
      '200':
        description: Case Deleted
        schema:
          deleted: string
      default:
        description: Failed to delete case
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    try:
        case_list_update.delay(case_id_list=[case_id])
        PromotionMethods().delete_case(case_id=case_id, promotion_uuid=promotion_uuid)
    except Exception as e:
        abort(500, "Failed to delete Case")

    return jsonify({'deleted': case_id})


@bp.route('/promotion/case/<case_uuid>', methods=['GET'])
@jwt_required()
def promotions_by_case(case_uuid):
    """
    Get Promotions by Case ID
    ---
    tags:
      - promotion
    parameters:
      - in: path
        name: case_uuid
        type: string
        required: true
    responses:
      default:
        description: "Unexpected Error"
      '200':
        description: "Promotion List"
        schema:
          properties:
            promotion_uuid:
              type: string
            channel_uuid:
              type: string
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    pr_list = PromotionMethods().get_promotions_by_case(case_id=case_uuid)
    return jsonify(pr_list)


@bp.route('/promotions', methods=['GET'])
@jwt_required()
def get_promotions():
    """
    Get All Promotions
    ---
    tags:
      - promotion
    produces:
      - application/json
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: Promotion List
        schema:
          properties:
            channel_uuid:
              type: string
            promotion_uuid:
              type: string
            promotion_name:
              type: string
            promotion_notes:
              type: string
            promotion_publish_date:
              type: string
              format: date
            promotion_tags:
              type: array
              items: []
            channel_uuid:
              type: string
            cases:
              type: array
              items:
                $ref: '#/definitions/Case'
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    pr_list = []
    for p in PromotionMethods().get_all_promotions():
        pr_list.append(p)
    return jsonify(pr_list)


@bp.route('/promotion/<promotion_uuid>', methods=['GET'])
@jwt_required()
def get_promotion(promotion_uuid):
    """
    Get Promotion
    ---
    tags:
      - promotion
    parameters:
      - name: promotion_uuid
        in: path
        type: string
        required: true
    responses:
      '200':
        description: Promotion Returned
        schema:
          properties:
            channel_uuid:
              type: string
            promotion_uuid:
              type: string
            promotion_name:
              type: string
            promotion_notes:
              type: string
            promotion_publish_date:
              type: string
              format: date
            promotion_tags:
              type: array
              items: []
            channel_uuid:
              type: string
            cases:
              type: array
              items:
                $ref: '#/definitions/Case'
      default:
        description: Failed to fetch promotion
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    r = PromotionMethods().get_promotion(promotion_uuid=promotion_uuid)
    return jsonify(r)


@bp.route('/promotion/channel', methods=['POST'])
@jwt_required()
def add_or_update_promotion_channel():
    """
    Add or Update promotion Channel
    ---
    tags:
      - promotion
    parameters:
      - in: body
        name: postChannel
        schema:
          id: postChannel
          example:
            channel_name: Twitter
          required:
            - channel_name
          properties:
            channel_name:
              type: string
    responses:
      default:
        description: "Unexpected Error"
      '200':
        description: "Channel Returned"
        schema:
          properties:
            channel_name:
              type: string
            channel_uuid:
              type: string
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    req = request.json
    if not req:
        abort(400, 'Requires JSON body')
    if 'channel_name' not in req:
        abort(400, 'Invalid Body')
    channel_name = req['channel_name']
    return jsonify(PromotionMethods().get_or_add_channel(channel=channel_name))


@bp.route('/promotion/channels', methods=['GET'])
@jwt_required()
def get_channels():
    """
    Get all channels
    ---
    tags:
      - promotion
    responses:
      default:
        description: "Unexpected Error"
      '200':
        description: "List of channels"
        schema:
          properties:
            channel_name:
              type: string
            channel_uuid:
              type: string
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    try:
        return jsonify(PromotionMethods().get_all_channels())
    except Exception as e:
        return make_response(jsonify({'error': str(e)}), 400)


@bp.route('/promotion', methods=['POST'])
@jwt_required()
def handle_promotion():
    """
    Add promotion
    ---
    tags:
      - promotion
    consumes:
      - application/json
    produces:
      - application/json
    definitions:
      Case:
        type: object
        required:
          - case_id
        properties:
          case_id:
            type: string
          promotion_uuid:
            type: string
          case_alternate_description:
            type: string
          case_alternate_caption:
            type: string
          case_alternate_title:
            type: string
          case_notes:
            type: string
    parameters:
      - in: body
        name: postPromotion
        schema:
          id: promotion
          example:
            channel_uuid: <fasdf>
            promotion_name: promotion_1
            cases: []
            promotion_publish_date: 2020-02-03
            promotion_tags: []
          required:
            - channel_uuid
          properties:
            channel_uuid:
              type: string
            promotion_name:
              type: string
            promotion_notes:
              type: string
            promotion_publish_date:
              type: string
              format: date
            promotion_tags:
              type: array
            channel_uuid:
              type: string
            cases:
              type: array
              items:
                $ref: '#/definitions/Case'
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: Promotion Created
        schema:
          properties:
            channel_uuid:
              type: string
            promotion_uuid:
              type: string
            promotion_name:
              type: string
            promotion_notes:
              type: string
            promotion_publish_date:
              type: string
              format: date
            promotion_tags:
              type: array
              items: []
            channel_uuid:
              type: string
            cases:
              type: array
              items:
                $ref: '#/definitions/Case'
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    if request.method == 'POST':
        if not request.json:
            abort(400, 'No valid body attached')
        req = request.json
        if 'channel_uuid' not in req or not req['channel_uuid']:
            abort(400, 'Channel UUID is required')
        return jsonify(add_or_update(req=req))


@managed_session
def add_or_update(req, session):
    p = PromotionMethods()
    promo = p.create_or_update_promotion(channel_uuid=req.get('channel_uuid'),
                                         promotion_name=req.get('promotion_name'),
                                         promotion_uuid=req.get('promotion_uuid'),
                                         promotion_notes=req.get('promotion_notes'),
                                         promotion_publish_date=req.get('promotion_publish_date'),
                                         promotion_tags=req.get('promotion_tags'))
    if not promo:
        return {}
    promo['cases'] = []
    case_list = req.get('cases')
    if not case_list or not isinstance(case_list, list):
        return promo
    for case in case_list:
        case_uuid = case.get('case_id')
        promo_case = p.add_or_update_case(case_id=case_uuid,
                                          promotion_uuid=promo.get('promotion_uuid'),
                                          case_alternate_caption=case.get('case_alternate_caption'),
                                          case_alternate_title=case.get('case_alternate_title'),
                                          case_alternate_description=case.get('case_alternate_description'),
                                          case_notes=case.get('case_notes'))
        update_moderation_case_detail(case_uuid=case_uuid, session=session)
        promo['cases'].append(promo_case)
    update_promotions.delay()
    return promo
