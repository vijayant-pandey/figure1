import uuid
from flask import Blueprint, jsonify, request, abort, make_response
from flask_jwt_extended import jwt_required
from figure1.exceptions import CampaignException
from figure1.admin.campaign.domain import update_campaign, activate_campaign, archive_campaign, unarchive_campaign
from figure1.core import es
from figure1.common.types import CampaignState
from figure1.configuration import es_settings

search_index = es_settings.campaign_alias

bp = Blueprint('pro_admin_campaign_endpoint', __name__)


@bp.app_errorhandler(CampaignException)
def handle_campaign_exception(e):
    return jsonify(e.as_dict()), e.rc


@bp.route('/campaign', methods=['POST'])
@jwt_required()
def create_campaign_endpoint():
    """
    Create a new campaign
    Creates a new campaign in the draft state. Most fields are optional except for the moderator_uid
    ---
    tags:
     - campaigns
    produces:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        schema:
          properties:
            moderator_uid:
              type: string
              required: true
              description: The uid of the moderator
            name:
              type: string
              required: false
              description: The name of the campaign
            client_name:
              type: string
              required: false
              description: The campaign client's name
            campaign_priority:
              type: int
              required: false
              description: A value between 1 and 3 which influences the ordering of the campaign within user feeds.
            target_country_uuids:
              type: array
              items: string
              required: false
            target_specialty_uuids:
              type: array
              items: string
              required: false
            target_languages:
              type: array
              items: string
              required: false
            target_verification:
              type: boolean
              required: false
              description: The verification status of users to target.  Null if targeting both verified and unverified.
            is_sponsored:
              type: boolean
              required: false
              description: mark a tactic as sponsored or not sponsored
            preview_user_uids:
              type: array
              items:
                type: string
              description: A list of user_uids who are able to preview the campaign before it is in an SC_APPROVED state
          example:
            moderator_uid: tJMPKzrR4ig3Yejc7cRQGSl8URr1
            name: New campaign
            client_name: Client A
            campaign_priority: 1
            target_country_uuids: []
            target_specialty_uuids: []
            target_languages: []
            target_verification: True
            is_sponsored: True
            preview_user_uids: []
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

    if 'moderator_uid' not in request.json:
        return abort(400, 'missing moderator_uid')

    moderator_uid = request.json.get('moderator_uid')

    res = update_campaign(moderator_uid=moderator_uid,
                          data=request.json)

    if 'error' in res:
        code = res.get('code', 500)
        return jsonify({'error': res['error']}), code
    else:
        return jsonify(res), 200


@bp.route('/campaign/<campaign_uuid>', methods=['PUT'])
@jwt_required()
def update_campaign_endpoint(campaign_uuid):
    """
    Update an existing campaign. The moderator uid is mandatory, all other fields are optional.
    ---
    tags:
     - campaigns
    produces:
      - application/json
    parameters:
      - name: campaign_uuid
        in: path
        type: string
        required: true
        description: The uuid of the campaign to update
      - name: body
        in: body
        required: true
        schema:
          properties:
            moderator_uid:
              type: string
              required: true
              description: The uid of the moderator
            name:
              type: string
              required: false
              description: The name of the campaign
            client_name:
              type: string
              required: false
              description: The campaign client's name
            campaign_priority:
              type: int
              required: false
              description: A value between 1 and 3 which influences the ordering of the campaign within user feeds.
            target_country_uuids:
              type: array
              items: string
              required: false
            target_specialty_uuids:
              type: array
              items: string
              required: false
            target_languages:
              type: array
              items: string
              required: false
            target_verification:
              type: boolean
              required: false
              description: The verification status of users to target.  Null if targeting both verified and unverified.
            preview_user_uids:
              type: array
              items:
                type: string
              description: A list of user_uids who are able to preview the campaign before it is in an SC_APPROVED state
            is_sponsored:
              type: boolean
              required: false
              description: update a campaign as sponsored or not sponsored
          example:
            moderator_uid: tJMPKzrR4ig3Yejc7cRQGSl8URr1
            name: New campaign
            client_name: Client A
            campaign_priority: 1
            target_country_uuids: []
            target_specialty_uuids: []
            target_languages: []
            target_verification: True
            preview_user_uids: []
            is_sponsored: True
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

    if 'moderator_uid' not in request.json:
        return abort(400, 'missing moderator_uid')

    moderator_uid = request.json.get('moderator_uid')

    res = update_campaign(campaign_uuid=campaign_uuid,
                          moderator_uid=moderator_uid,
                          data=request.json)

    return jsonify(res), 200


@bp.route('/campaign/<campaign_uuid>/activate', methods=["POST"])
@jwt_required()
def do_activate_campaign(campaign_uuid):
    """
     Activate a campaign
     ---
     tags:
      - campaigns
     produces:
       - application/json
     parameters:
       - name: campaign_uuid
         in: path
         type: string
         required: true
         description: The uuid of the campaign to update
       - name: body
         in: body
         required: true
         schema:
           properties:
             moderator_uid:
               type: string
               required: true
               description: The uid of the moderator
         example:
           moderator_uid: tJMPKzrR4ig3Yejc7cRQGSl8URr1

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

    if 'moderator_uid' not in request.json:
        return abort(400, 'missing moderator_uid')

    moderator_uid = request.json.get('moderator_uid')
    res = activate_campaign(moderator_uid=moderator_uid, campaign_uuid=campaign_uuid)

    return jsonify(res), 200


@bp.route('/campaign/<campaign_uuid>/archive', methods=["POST"])
@jwt_required()
def do_archive_campaign(campaign_uuid):
    """
     Archive a campaign
     ---
     tags:
      - campaigns
     produces:
       - application/json
     parameters:
       - name: campaign_uuid
         in: path
         type: string
         required: true
         description: The uuid of the campaign to update
       - name: body
         in: body
         required: true
         schema:
           properties:
             moderator_uid:
               type: string
               required: true
               description: The uid of the moderator
         example:
           moderator_uid: tJMPKzrR4ig3Yejc7cRQGSl8URr1

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
    if 'moderator_uid' not in request.json:
        return abort(400, 'missing moderator_uid')

    moderator_uid = request.json.get('moderator_uid')
    res = archive_campaign(moderator_uid=moderator_uid, campaign_uuid=campaign_uuid)

    return jsonify(res), 200


@bp.route('/campaign/<campaign_uuid>/state', methods=["POST"])
@jwt_required()
def update_campaign_state_endpoint(campaign_uuid):
    """
    Update the state of a campaign
    Supported states: ["draft", "active", "archived"]
    ---
    tags:
     - campaigns
    produces:
      - application/json
    parameters:
      - name: campaign_uuid
        in: path
        type: string
        required: true
        description: The uuid of the campaign to update
      - name: body
        in: body
        required: true
        schema:
          properties:
            moderator_uid:
              type: string
              required: true
              description: The uid of the moderator
            state:
              type: string
              required: true
              enum: ["draft", "active", "archived"]
              description: The new state for the campaign
        example:
          moderator_uid: tJMPKzrR4ig3Yejc7cRQGSl8URr1
          state: draft
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

    if 'moderator_uid' not in request.json:
        return abort(400, 'missing moderator_uid')
    if 'state' not in request.json:
        return abort(400, 'missing state')

    moderator_uid = request.json.get('moderator_uid')
    state = request.json.get('state').upper()

    if state not in CampaignState.__members__:
        return abort(400, f'State {state} is not supported')
    if state == 'ARCHIVED':
        res = archive_campaign(moderator_uid=moderator_uid, campaign_uuid=campaign_uuid)
    elif state == 'ACTIVE':
        res = activate_campaign(moderator_uid=moderator_uid, campaign_uuid=campaign_uuid)
    elif state == 'DRAFT':
        res = unarchive_campaign(moderator_uid=moderator_uid, campaign_uuid=campaign_uuid)
    else:
        abort(400, f'State {state} is not supported')

    return jsonify(res), 200


@bp.route("/campaign/search", methods=['POST'])
@jwt_required()
def search_campaigns():
    """
    Search
    ---
    tags:
     - campaigns
    consumes:
      - application/json
    parameters:
      - name: request
        in: body
    responses:
      '200':
        description: Elasticsearch Resultset
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
      """

    search_request = request.json
    results = es.search(body=search_request, index=search_index, doc_type='_doc')
    return jsonify(results)


@bp.route("/campaign/<campaign_uuid>", methods=['GET'])
@jwt_required()
def get_search_campaign(campaign_uuid):
    """
    Get Campaign from Elastic
    ---
    tags:
      - campaigns
    produces:
      - application/json
    parameters:
      - name: campaign_uuid
        in: path
        type: string
        description:
        required: true
    responses:
      '200':
        description: Elasticsearch Resultset
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
      """

    results = es.get(index=search_index, id=campaign_uuid)
    return jsonify(results)
