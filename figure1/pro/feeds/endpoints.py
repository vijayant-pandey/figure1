import logging
from flask import Blueprint, request
from flask.json import jsonify
from flask_jwt_extended import jwt_required
from figure1.exceptions import FeedException
from .domain import generate_user_feed, get_user_targetted_tactics, get_targeted_uids
from figure1.aggregation import NewCasesDatafeed
from figure1.aggregation import regenerate_new_cases_task
from figure1.store import NewCaseHandler
from figure1.core import managed_session

logger = logging.getLogger(__name__)
bp = Blueprint('pro_feeds_endpoint', __name__)


def parse_filter(j):
    sort_by = []
    filter_by = []
    for opt in j.keys():
        logger.debug("Handling option %s with value %s", opt, j.get(opt))
        if opt.startswith('filter') and j.get(opt):
            if opt == 'filter_resolved':
                filter_by.append('resolved')
            elif opt == 'filter_unresolved':
                filter_by.append('unresolved')
            elif opt == 'filter_verified_literature':
                filter_by.append('verified_literature')
            elif opt == 'filter_trending':
                filter_by.append('trending')
                sort_by.append("trendScore:desc")
            elif opt == 'filter_teaching_case':
                filter_by.append('teaching_case')
            elif opt == 'filter_common_presentation':
                filter_by.append('common_presentation')
            elif opt == 'filter_rare_condition':
                filter_by.append('rare_condition')
            else:
                filter_by.append(opt.split('_', 1)[1])
        elif opt.startswith('sort'):
            if opt == 'sort_created':
                sort_by.append(f"createdAt:{j[opt]}")
            else:
                sort_by.append(f"{opt.split('_', 1)[1]}:{j[opt]}")
    logger.debug("Returning filter list %s and sort list %s", filter_by, sort_by)
    return sort_by, filter_by


@bp.errorhandler(FeedException)
def handle_general_feed_exception(e):
    logger.exception("%s", e.msg)
    return jsonify(e.as_dict()), e.rc


@bp.route('/feeds/<user_uid>', methods=['POST'])
@bp.route('/feeds/<user_uid>/<path:update>', methods=['POST'])
@jwt_required()
def do_update_user_feed(user_uid, update=None):
    """Update User's made-for-you feed
    Passing through filters and sort parameters are optional, setting a filter to False is the same as not setting it.

    For both sort and filter parameters, the general syntax for the key is <sort|filter>_<fieldname>, so the parameter
     for sorting by the created_at fieldname has a key sort_created_at.
     The value is either true or false for the filters, and sort parameters can be either asc or desc.

    There are some preset filter and sort names that are pre-mapped, they take precedence over freeform parameters.

    - sort_created
    - filter_resolved
    - filter_unresolved
    - filter_verified_literature
    - filter_trending
    - filter_common_presentation
    - filter_rare_condition
    - filter_teaching_case

     Passing in a fieldname that doesn't exist will be ignored.

    ---
    tags:
     - feed
    produces:
      - application/json
    parameters:
      - name: user_uid
        in: path
        required: true
      - name: update
        in: path
        required: false
        enum: ['update', '']
      - name: body
        in: body
        required: true
        schema:
          required:
          properties:
            feed_type_uuid:
              type: string
              description: Update this feed type for this user
            return_feed:
              type: boolean
              description: If 'true', the feed data is returned in the response body.  If false it is written to
                firestore.
            filter_resolved:
              type: bool
              description: Only show resolved ( True/False )
            filter_unresolved:
              type: bool
              description: Only show unresolved ( True/False )
            filter_verified_literature:
              type: bool
              description: Filter on verified literature ( True/False )
            filter_trending:
              type: bool
              description: Filter on trending ( True/False )
            filter_teaching_case:
              type: bool
              description: Filter on teaching_case
            filter_rare_condition:
              type: bool
              description: Filter on rare condition
            filter_common_presentation:
              type: bool
              description: Filter on common presentation

            sort_created:
              type: string
              enum: ['asc', 'desc']
              description: Sort by created date

          example:
            feed_type_uuid: <>
            filter_resolved: false
            filter_unresolved: false
            filter_verified_literature: false
            filter_trending: false
            filter_rare_condition: false
            filter_common_presentation: false
            filter_teaching_case: false
            return_feed: true
            sort_created: desc

    responses:
      default:
        description: Unexpected Failure
      '202':
        description: Users feed task submitted
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    j = request.json
    if j:
        feed_type_uuid = j.get('feed_type_uuid')
        return_feed = j.get('return_feed') is True
        if not feed_type_uuid:
            return jsonify({'error': 'feed type uuid is required'}), 400
        sort_by, filter_by = parse_filter(j)

        if update:
            res = generate_user_feed(feed_type_uuid=feed_type_uuid,
                                     user_uid=user_uid,
                                     sort_by=sort_by,
                                     filter_by=filter_by,
                                     update=True,
                                     return_feed=return_feed)
        else:
            res = generate_user_feed(feed_type_uuid=feed_type_uuid,
                                     user_uid=user_uid,
                                     sort_by=sort_by,
                                     filter_by=filter_by,
                                     return_feed=return_feed)
        return jsonify(res), 200
    else:
        return jsonify({'error': 'No json body found'})


@bp.route('/user/target/<user_uid>/', methods=['GET'])
@jwt_required()
def get_user_targeted_tactics(user_uid):
    """User Tactic Targets
    Given a user_uid, return a list of sponsored content in order they will be shown

    ---
    tags:
     - SponsoredContent
    produces:
      - application/json
    parameters:
      - name: user_uid
        in: path
        required: true

    responses:
      default:
        description: Unexpected Failure
      '200':
        description: Target list returned
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    res = get_user_targetted_tactics(user_uid=user_uid)
    return jsonify(res), 200


@bp.route('/sponsoredcontent/target/<case_uuid>/', methods=['GET'])
@jwt_required()
def get_tactic_targets(case_uuid):
    """User Tactic Targets
    Given a user_uid, return a list of sponsored content in order they will be shown

    ---
    tags:
     - SponsoredContent
    produces:
      - application/json
    parameters:
      - name: case_uuid
        in: path
        required: true

    responses:
      default:
        description: Unexpected Failure
      '200':
        description: Target list returned
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    res = get_targeted_uids(case_uuid)
    return jsonify(res), 200


@bp.route('/datafeeds/new/<user_uuid>', methods=['GET'])
@jwt_required()
@managed_session
def get_new_cases_by_user(user_uuid, session=None):
    """
    Given a user_uid, return a list of sponsored content in order they will be shown

    ---
    tags:
     - DataFeeds
    produces:
      - application/json
    parameters:
      - name: user_uuid
        in: path
        required: true
      - name: count
        in: query
        required: false
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: List of new cases to be recommended to user
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    count = request.args.get('count', default=10, type=int)
    res = list(NewCasesDatafeed.get_new_case(cases_per_user=count, user_uuid=user_uuid, session=session))
    return jsonify(res), 200


@bp.route('/datafeeds/new/all', methods=['GET'])
@jwt_required()
def get_new_cases():
    """
    Returns a list of case_uuids that can be promoted as a new case
    ---
    tags:
     - DataFeeds
    produces:
      - application/json
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: List of new cases that can be promoted
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    res = NewCasesDatafeed.get_all_new_cases()
    return jsonify(res), 200


@bp.route('/datafeeds/new/generate', methods=['GET'])
@jwt_required()
def regenerate_new_cases():
    """
    Triggers a task to regenerate new cases. This may remove some cases from the list of promotable cases.
    ---
    tags:
     - DataFeeds
    produces:
      - application/json
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: Task started
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    t = regenerate_new_cases_task.apply_async()
    return jsonify(dict(task=t.task_id)), 200


@bp.route('/datafeeds/new/clear_sent', methods=['DELETE'])
@jwt_required()
def clear_sent_queue():
    """
    Removes all keys from the sent queue. This should only be used for testing.
    ---
    tags:
     - DataFeeds
    produces:
      - application/json
    responses:
      default:
        description: Unexpected Failure
      '200':
        description: Sent queue removed
    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    new_case = NewCaseHandler()
    new_case.clean_sent_queue()
    return jsonify(), 200
