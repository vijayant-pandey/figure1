from flask import Blueprint, request, abort
from flask.json import jsonify
from flask_jwt_extended import jwt_required
from .domain import follow_topic, \
    unfollow_topic, \
    create_topic, \
    get_topic_list, \
    delete_topic, \
    update_topic, \
    handle_bulk_topics

bp = Blueprint('pro_topics_endpoint', __name__)


@bp.route('/topics/<user_uid>', methods=['POST'])
@jwt_required()
def post_multiple_topics(user_uid):
    """
    Follow or unfollow multiple topics
    This is functionally the same as /topic/<user_uid> except that it takes a list of objects that look like
    {'action': 'follow', 'feed_type_uuid', 'd13dafd0-bf4e-4386-9186-3ef13505b9e8'}
    ---
    tags:
     - topics
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
            actions:
              type: array
              items: dict
              description: List of dicts
          example:
            actions: [{
            'feed_type_uuid': 'd13dafd0-bf4e-4386-9186-3ef13505b9e8',
            'action': 'follow'
            }]

    responses:
      default:
        description: Unexpected Failure
      '404':
        description: Topic or user not found
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
    data = request.json
    actions = data.get('actions', [])
    if not actions:
        return abort(400, 'No actions attached')
    resp = handle_bulk_topics(user_uid=user_uid, data=actions)
    return jsonify(resp), 200


@bp.route('/topic/<user_uid>', methods=["POST"])
@jwt_required()
def post_topic(user_uid):
    """
    Follow or unfollow a topic
    Supported actions:  'follow', 'unfollow'
    ---
    tags:
     - topics
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
            action:
              type: string
              enum: ["follow", "unfollow"]
              description: The topic action to perform
            feed_type_uuid:
              type: string
              description: The topic to update
          example:
            feed_type_uuid: d13dafd0-bf4e-4386-9186-3ef13505b9e8
            action: follow
    responses:
      default:
        description: Unexpected Failure
      '404':
        description: Topic or user not found
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

    if 'feed_type_uuid' not in request.json:
        return abort(400, 'missing feed_type_uuid')
    if 'action' not in request.json:
        return abort(400, 'missing action')

    feed_type_uuid = request.json.get('feed_type_uuid')
    action = request.json.get('action')

    if action.lower() == 'follow':
        res = follow_topic(user_uid, feed_type_uuid)
    elif action.lower() == 'unfollow':
        res = unfollow_topic(user_uid, feed_type_uuid)
    else:
        return abort(400, 'Unsupported action')

    if 'error' in res:
        code = res.get('code', 500)
        return jsonify({'error': res['error']}), code

    return jsonify(res), 200


@bp.route('/topic/create', methods=["POST"])
@jwt_required()
def do_create_topic():
    """
    Create a new topic

    A topic is essentially an arbitrarily complex saved search. The standard topics consist of a list of specialty uuids
    which are assigned by the tagging workflow, and campaign preview feeds are just filters on the campaign uuid that
    are pushed to a specific user or users.
    The filter_query is the json that comprises the core of the query, this query is any json structure that fits inside
    of the {query: {}} construct. The specialty list and language filter just modify this.
    The expire_query is intended for feeds that have a cycle to them, this could be used for something like a New Feed
    where items expire out after a certain amount of time. While this can technically be any query, likely a range
    query makes the most sense.
    The sort fields are for sorting the feed, this is just passed through to elasticsearch.
    The name is what is shown in the app.
    The label must be unique, it is what is used to identify the topic.

    ---
    tags:
     - topics
    produces:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        schema:
          properties:
            label:
              type: string
              description: The label given to identify the feed, no spaces in this one
            name:
              type: string
              description: This is the name visible in the app, spaces are acceptable here
            filter_query:
              type: object
              description: This is the query used to create this topic
            expire_query:
              type: object
              description: This should be the negative of the filter query, this is used to remove items from the topic
            sort_fields:
              type: array
              items: object
              description: List of tuples describing sort fields
            topic_language:
              type: enum
              items: ['EN_US', 'ES_ES', 'PT_PT']
              required: false
              description: Language filter for this topic
            specialtyUuids:
              type: array
              items: string
              description: A list of specialtyUuids, these are used as search indexes. This is optional.

          example:
            label: "new"
            name: "all new topics"
            topic_language: "EN_US"
            filter_query: {"range": {"publishedAt": {"gte": "now-7d","lte": "now"}}}
            expire_query: {"range": {"publishedAt": {"lte": "now-7d"}}}
            sort_fields: [{"publishedAt": {"order": "desc"}}]
    responses:
      default:
        description: Unexpected Failure
      '500':
        description: Error fetching topics
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
    data = request.json
    label = data.get('label')
    name = data.get('name')
    specialty_uuids = data.get('specialtyUuids')
    filter_query = data.get('filter_query')
    expire_query = data.get('expire_query')
    sort_fields = data.get('sort_fields')
    topic_language = data.get('topic_language')
    ret = create_topic(label=label,
                       name=name,
                       specialtyUuids=specialty_uuids,
                       filter_query=filter_query,
                       expire_query=expire_query,
                       sort_fields=sort_fields,
                       topic_language=topic_language)
    return jsonify(ret), 200


@bp.route('/topic/<label>/update', methods=["POST"])
@jwt_required()
def do_topic_update(label):
    """
    Update an existing topic
    Note the hidden is set to be true by default when topic is created, it is necessary to set hidden=false to expose
    the feed in the app.

    All fields in the body are optional, do NOT include fields you are not changing, this will erase data in most cases.
    The filter_query is an arbitrarily complex elasticsearch query that can reference any field in the case index. This
    forms the core of the search that creates the topic. Specialty terms end up being a part of this query.
    This does not create a new topic if one does not exist.

    ---
    tags:
     - topics
    produces:
      - application/json
    parameters:
      - name: label
        in: path
        required: true
        type: string
      - name: body
        in: body
        required: true
        schema:
          properties:
            display_order:
              type: integer
              description: Where in the list in the app should this topic appear? Fails if the display number is taken
            hidden:
              type: boolean
              description: Expose the feed to all users, defaults to hidden=true for all new feeds which hides the feed
            name:
              type: string
              description: This is the name visible in the app, spaces are acceptable here
            filter_query:
              type: object
              description: This is the query used to create this topic
            expire_query:
              type: object
              description: This should be the negative of the filter query, this is used to remove items from the topic
            sort_fields:
              type: array
              items: object
              description: List of tuples describing sort fields
            topic_language:
              type: enum
              items: ['EN_US', 'ES_ES', 'PT_PT']
              required: false
              description: Language filter for this topic
            specialtyUuids:
              type: array
              items: string
              description: A list of specialtyUuids, these are used as search indexes. This is optional.

          example:
            hidden: true
            name: "all new topics"
            filter_query: {"range": {"publishedAt": {"gte": "now-7d","lte": "now"}}}
            expire_query: {"range": {"publishedAt": {"lte": "now-7d"}}}
            sort_fields: [{"publishedAt": {"order": "desc"}}]
            topic_language: "EN_US"
            display_order: 4
    responses:
      default:
        description: Unexpected Failure
      '500':
        description: Error fetching topics
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
    data = request.json
    hidden = data.get('hidden', True)
    name = data.get('name')
    specialty_uuids = data.get('specialtyUuids')
    filter_query = data.get('filter_query')
    expire_query = data.get('expire_query')
    sort_fields = data.get('sort_fields')
    display_order = data.get('display_order', 1000)
    topic_language = data.get('topic_language')

    ret = update_topic(label=label,
                       name=name,
                       hidden=hidden,
                       display_order=display_order,
                       specialtyUuids=specialty_uuids,
                       filter_query=filter_query,
                       expire_query=expire_query,
                       sort_fields=sort_fields,
                       topic_language=topic_language)
    return jsonify(ret), 200


@bp.route('/topic/<label>/delete', methods=["DELETE"])
@jwt_required()
def do_delete_topic(label):
    """
    Delete this topic
    ---
    tags:
     - topics
    produces:
      - application/json
    parameters:
      - name: label
        in: path
        required: true
        type: string
    responses:
      default:
        description: Unexpected Failure
      '500':
        description: Error fetching topics
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

    ret = delete_topic(label=label)
    return jsonify(ret), 200


@bp.route('/topic/list', methods=["POST"])
@jwt_required()
def list_all_topics():
    """
    List of topics ordered by displayOrder
    ---
    tags:
     - topics
    produces:
      - application/json
    parameters:
      - name: show_hidden
        in: query
        required: false
        type: boolean
    responses:
      default:
        description: Unexpected Failure
      '500':
        description: Error fetching topics
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
    show_hidden = request.args.get('show_hidden')
    if show_hidden:
        if show_hidden.lower() == 'false':
            show_hidden = False
        else:
            show_hidden = True
    else:
        show_hidden = False
    ret = get_topic_list(show_hidden=show_hidden)
    return jsonify(ret), 200
