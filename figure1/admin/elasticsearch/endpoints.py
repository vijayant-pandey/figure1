from figure1.common.elasticsearch import create_legacy_case_index, \
    populate_new_case_index, \
    create_new_comment_index, \
    create_new_user_index, \
    create_new_search_term_index, \
    create_new_specialty_index, \
    create_new_campaign_index, \
    create_new_public_school_index, \
    create_new_public_country_index, \
    refresh_users_index, \
    switch_user_index_alias, \
    switch_cases_index_task, \
    create_new_case_index, \
    comment_update_mapping, \
    reindex_search_terms_task, \
    generate_groups_index

from figure1.common.helpers.groups import GroupManagement
from flask import Blueprint, request, make_response, abort
from flask.json import jsonify
from flask_jwt_extended import jwt_required

bp = Blueprint('elasticsearch_admin', __name__)


@bp.route("/update_alias")
@jwt_required()
def do_update_index_alias_endpoint():
    """
    Given an alias name and an index name, set the alias to point to this index.
    This is currently only supported by the users index
    ---
    tags:
      - elasticsearch
    parameters:
      - name: index_name
        in: query
        type: string
        required: false
      - name: index_alias
        in: query
        type: string
        enum: ['users', 'cases']
        required: false
    responses:
      '202':
        description: Index update task submitted
        schema:
          properties:
            task_id:
              type: string

    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    index_name = request.args.get('index_name')
    index_alias = request.args.get('index_alias')
    if not index_name:
        abort(400, "Expected index name")
    if not index_alias:
        abort(400, "Expected target alias")
    if index_alias == 'users':
        switch_user_index_alias.apply(kwargs=dict(index_name=index_name))
    if index_alias == 'cases':
        switch_cases_index_task.apply_async(kwargs=dict(index_name=index_name))

    return jsonify({}), 200


@bp.route("/create")
@jwt_required()
def create_index_endpoint():
    """
    Create Index
    This endpoint simply creates a new index and returns the name.
    ---
    tags:
      - elasticsearch
    parameters:
      - name: index
        in: query
        type: string
        enum: [
        'cases']
        required: true
    responses:
      '202':
        description: Reindex Task Submitted
        schema:
          properties:
            task_id:
              type: string

    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    index_name = request.args.get('index')
    if index_name == 'cases':
        idx = create_new_case_index()
        return jsonify(created_index=idx), 200
    else:
        abort(400)


@bp.route("/refresh")
@jwt_required()
def refresh_index_endpoint():
    """
    Refresh index
    In the event of a mapping change, the index needs to be re-indexed, but doesn't necessarily need to be pulled from
    the database again. Executing reindex creates a new index withthe new mapping, then copies the data over. This is
    much faster and is sufficient in the majority of cases.
    This is currently only supported on the users index.
    ---
    tags:
      - elasticsearch
    parameters:
      - name: index
        in: query
        type: string
        enum: [
        'users',
        'comments']
        required: true
      - name: workers
        in: query
        type: number
    responses:
      '202':
        description: Reindex Task Submitted
        schema:
          properties:
            task_id:
              type: string

    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """
    i = request.args.get('index')
    w = request.args.get('workers', 1)

    if i == 'users':
        task = refresh_users_index.apply_async()
        return make_response(jsonify({'index': i, 'task_id': task.id}), 202)
    if i == 'comments':
        task = comment_update_mapping.apply_async()
        return make_response(jsonify({'index': i, 'task_id': task.id}), 202)
    return jsonify({}), 200


@bp.route("/rebuild")
@jwt_required()
def rebuild_index():
    """
    Rebuild Elasticsearch Index
    Passing in the index name generates a task to rebuild that index.
    Passing in a number of workers is how many simultaneous workers will build that index. This is not supported by
     all indexes, but is ignored if not supported.

    ---
    tags:
      - elasticsearch
    parameters:
      - name: index
        in: query
        type: string
        enum: [
        'legacycases',
        'cases',
        'comments',
        'users',
        'public_search_terms',
        'public_search_terms_v2',
        'public_specialty',
        'campaigns',
        'public_schools',
        'public_countries',
        'groups']
        required: true
      - name: workers
        in: query
        type: number
      - name: index_name
        in: query
        type: string
        required: false
        description: If passed, populate this index. Do not use an active index for this.
    responses:
      '202':
        description: Rebuild Task Submitted
        schema:
          properties:
            task_id:
              type: string

    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """

    i = request.args.get('index')
    w = request.args.get('workers', 1)
    idx = request.args.get('index_name', None)
    if i == 'legacycases':
        task = create_legacy_case_index.apply_async()
    if i == 'cases':
        if not idx:
            idx = create_new_case_index()
        sig = populate_new_case_index(workers=w, index_name=idx)
        sig.link(switch_cases_index_task.si(index_name=idx))
        task = sig.apply_async()
    if i == 'comments':
        task = create_new_comment_index.apply_async()
    if i == 'users':
        task = create_new_user_index.apply_async(kwargs={'workers': w})
    if i == 'public_search_terms':
        task = create_new_search_term_index.apply_async()
    if i == 'public_search_terms_v2':
        task = reindex_search_terms_task.apply_async()
    if i == 'public_specialty':
        task = create_new_specialty_index.apply_async()
    if i == 'campaigns':
        task = create_new_campaign_index.apply_async()
    if i == 'public_schools':
        task = create_new_public_school_index.apply_async()
    if i == 'public_countries':
        task = create_new_public_country_index.apply_async()
    if i == 'groups':
        generate_groups_index()
        return jsonify({}), 200

    return make_response(jsonify({'index': i, 'task_id': task.id, 'index_name': idx}), 202)
