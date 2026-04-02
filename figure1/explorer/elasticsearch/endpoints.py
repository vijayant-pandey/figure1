import json
import os
from figure1.configuration import es_settings
from elasticsearch import NotFoundError, Elasticsearch
from flask import Blueprint, request, abort, make_response
from flask.json import jsonify
from flask_jwt_extended import jwt_required

elasticsearch_hosts = os.environ.get('ELASTICSEARCH_HOSTS', default='http://elasticsearch:9200')
es = Elasticsearch([elasticsearch_hosts])

search_index = es_settings.legacy_cases_alias

bp = Blueprint('explorer_search', __name__)


@bp.route("/search", methods=['POST'])
@jwt_required()
def post_search():
    """
    Search
    ---
    tags:
      - elasticsearch
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
    if request.method == 'POST':
        search_request = request.json
        try:
            results = es.search(body=search_request, index=search_index, doc_type='_doc')
        except Exception as e:
            return make_response(jsonify({'error': str(e)}), 400)
        return jsonify(results)


@bp.route("/search", methods=['GET'])
@jwt_required()
def search():
    """
    Search
    ---
    tags:
      - elasticsearch
    parameters:
      - name: query
        in: query
        type: string
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

    if request.args.get('query'):
        search_results = es.search(index=search_index, doc_type="_doc", q=request.args.get('query'))
        return jsonify(search_results)
    else:
        return jsonify({})


@bp.route("/relatedcases/<caseid>", methods=['GET'])
@jwt_required()
def related_cases(caseid):
    """
    Search
    ---
    tags:
      - elasticsearch
    parameters:
      - name: caseid
        in: path
        type: string
        required: true
    definitions:
      relatedCases:
        type: object
        required:
          - id
        properties:
          id:
            type: string
          caption:
            type: string
          image_url:
            type: string

    responses:
      '200':
        description: Related Cases
        schema:
          properties:
            relatedCases:
              type: array
              items:
                $ref: '#/definitions/relatedCases'

    securityDefinitions:
      JWT:
        type: apiKey
        name: Authorization
        in: header
    security:
      - JWT: []
    """

    keyword_query = {
        "query": {
            "bool": {
                "must_not": {
                    "ids": {
                        "values": caseid
                    }
                },
                "should": []
            }
        }
    }

    speciality_query = {
        "terms": {
            "boost": 1.2,
            "speciality.keyword": {
                "index": search_index,
                "id": "",
                "path": "speciality"
            }
        }
    }

    search_terms = []
    try:
        sd = es.get(index=search_index, id=caseid)
    except NotFoundError:
        abort(404)
    for term in sd['_source']['mesh_terms']:
        search_terms.append(term)
    if not search_terms:
        vec = es.termvectors(index=search_index, id=caseid, fields='caption')
        search_terms.append([x for x in vec])
    for search_term in search_terms:
        m = {
            "match_phrase": {
                "mesh_terms": search_term
            }
        }
        keyword_query['query']['bool']['should'].append(m)

    speciality_query['terms']['speciality.keyword']['id'] = caseid
    keyword_query['query']['bool']['should'].append(speciality_query)
    return_results = {'relatedCases': []}
    try:
        results = es.search(body=json.dumps(keyword_query), index=search_index)
    except NotFoundError:
        return jsonify(return_results)
    for hit in results['hits']['hits']:
        return_results['relatedCases'].append({'id': hit['_id'],
                                               'caption': hit['_source']['caption'],
                                               'image_url': hit['_source']['image_url']
                                               })
    return jsonify(return_results)
