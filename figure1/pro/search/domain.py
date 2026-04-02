from figure1.core import es
from elasticsearch.exceptions import NotFoundError, RequestError
from figure1.configuration import es_settings
from figure1.common.models.db import FeedType, User
from figure1.core import managed_session
import logging

logger = logging.getLogger(__name__)
user_index_alias = es_settings.users_alias
case_index_alias = es_settings.cases_alias


def _execute_search(search_query, search_cursor, search_index):
    logger.debug("Executing search %s, search_cursor %d, index %s", search_query, search_cursor, search_index)
    if not search_index:
        logger.error("Warning - No index passed, this will search everything by default resulting in duplicates")
    try:
        results = es.search(index=search_index, body=search_query, from_=search_cursor, size=20)
    except NotFoundError as ne:
        logger.error("Index not found %s", ne)
        return {'error': f'Search index {search_index} not found'}
    except RequestError as re:
        logger.error("Elasticsearch request error %s", re)
        return {'error': 'Search request failed'}
    total_hits = results.get('hits', {}).get('total', {}).get('value', 0)
    if search_index == user_index_alias:
        return {
            'search_count': {
                'total': total_hits
            },
            'search_results': [x.get("_source") for x in results.get('hits', {}).get('hits', [])]
        }

    resp = []
    for r in results.get('hits', {}).get('hits', []):
        h = r.get("_source")
        if not h:
            continue
        case_type = h.get('caseType')
        if not isinstance(case_type, str):
            continue
        if case_type == 'clinical_moments' or case_type == 'cme':
            feed_card = h.get('feedCardMedia')
            if feed_card:
                h.update({'media': [feed_card]})
            else:
                for content_item in h.get('contentItems'):
                    content_type = content_item.get('contentType')
                    if content_type and content_type == 'cme_hub_card':
                        h.update({'media': content_item.get("media")})

        resp.append(h)
    return {
        'search_count': {
            'total': total_hits
        },
        'search_results': resp
    }


def search_users(search_term, search_cursor=0):
    user_search_query = {
        "query": {
            "bool": {
                "should": [
                    {
                        "term": {
                            "username": {
                                "value": search_term
                            }
                        }
                    },
                    {
                        "term": {
                            "professionName": {
                                "value": search_term
                            }
                        }
                    },
                    {
                        "term": {
                            "specialtyName": {
                                "value": search_term
                            }
                        }
                    },
                    {
                        "term": {
                            "subSpecialtyName": {
                                "value": search_term
                            }
                        }
                    },
                    {
                        "multi_match": {
                            "query": search_term,
                            "type": "phrase_prefix",
                            "operator": "and",
                            "fields": [
                                "username.text^2",
                                "displayName^2",
                                "userBio"
                            ]
                        }
                    }
                ],
                "must_not": [
                    {
                        "term": {
                            "userHiddenFromSearch": True
                        }
                    },
                    {
                        "term": {
                            "isDeleted": {
                                "value": True
                            }
                        }
                    }
                ]
            }
        }
    }
    return _execute_search(search_query=user_search_query, search_cursor=search_cursor, search_index=user_index_alias)


@managed_session
def search_cases(search_term, search_index, user_uid, search_cursor=0, session=None):
    mfy_uuid = FeedType.get_made_for_you_uuid(session=session)
    terms_filter = {}
    if mfy_uuid in search_index:
        u = User.get_user_by_uid(user_uid=user_uid, session=session, raise_exception=True)
        user_uuid = str(u.user_uuid)
        user_doc = es.get(index=user_index_alias, id=user_uuid)
        filter_specialties = user_doc.get('_source', {}).get('madeForYouSpecialties', [])
        if filter_specialties:
            terms_filter = {'terms': {'specialtyUuids': filter_specialties}}
        logger.debug("Appending terms filter %s for user_uid %s", terms_filter, user_uid)
    case_search_query = {
        "query": {
            "bool": {
                "minimum_should_match": 1,
                "filter": [
                    {
                        "terms": {
                            "caseState": ["APPROVED", "SC_APPROVED"]
                        }
                    }
                ],
                "must_not": [
                    {
                        "exists": {
                            "field": "groupUuid"
                        }
                    },
                    {
                        "term": {
                            "caseType": "promo_card"
                        }
                    },
                    {
                        "term": {
                            "isAnonymous": "true"
                        }
                    }
                ],
                "should": [
                    {
                        "match": {
                            "contentSearch": search_term
                        }
                    },
                    {
                        "match": {
                            "commentSearch": search_term
                        }
                    },
                    {
                        "match": {
                            "meshTerms.text": search_term
                        }
                    },
                    {
                        "nested": {
                            "path": "authors",
                            "query": {
                                "multi_match": {
                                    "query": search_term,
                                    "fields": ["authors.displayName^2", "authors.username^2"]
                                }
                            }
                        }
                    }
                ]
            }
        }
    }
    if terms_filter:
        case_search_query['query']['bool']['filter'].append(terms_filter)
        logger.debug("Added terms for RFY filter: %s", terms_filter)
    logger.debug("Executing case search %s", case_search_query)
    return _execute_search(search_query=case_search_query, search_cursor=search_cursor, search_index=case_index_alias)
