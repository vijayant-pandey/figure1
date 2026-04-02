import logging
import datetime
from elasticsearch.exceptions import RequestError
from elasticsearch.exceptions import ConflictError
from elasticsearch.exceptions import ElasticsearchException
from elasticsearch.exceptions import NotFoundError
from figure1.core import es
from figure1.configuration import es_settings
from figure1.common.helpers import CaseDetail
from figure1.common.helpers import CampaignDetail
from figure1.common.types import CaseState
from figure1.store import SponsoredContentCache

public_feed_states = es_settings.public_feed_states
case_index_alias = es_settings.cases_alias
comments_index_alias = es_settings.comments_alias
users_index_alias = es_settings.users_alias
campaigns_index_alias = es_settings.campaign_alias

logger = logging.getLogger(__name__)


def get_cases(case_uuids):
    if not isinstance(case_uuids, list):
        return []
    get_body = {
        "ids": case_uuids
    }
    return es.mget(index=case_index_alias, doc_type="_doc", body=get_body)


def get_case(case_uuid):
    case = es.get(index=case_index_alias, id=case_uuid)
    if case.get('found'):
        state = case['_source'].get("caseState")
        if state == CaseState.APPROVED.name or state == CaseState.SC_APPROVED.name:
            return case
    return None


def get_related_cases(case_uuid):
    return es.search(index=case_index_alias, query={
        "bool": {
            "filter": [
                {
                    "terms": {
                        "caseState": public_feed_states
                    }
                }
            ],
            "should": [
                {
                    "more_like_this": {
                        "fields": [
                            "meshTerms.text",
                            "caption",
                            "title"
                        ],
                        "like": [
                            {
                                "_index": case_index_alias,
                                "_id": case_uuid
                            }
                        ]
                    }
                },
                {
                    "terms": {
                        "specialtyUuids": {
                            "index": case_index_alias,
                            "id": case_uuid,
                            "path": "specialtyUuids"
                        }
                    }
                },
                {
                    "terms": {
                        "meshTerms": {
                            "index": case_index_alias,
                            "id": case_uuid,
                            "path": "meshTerms"
                        }
                    }
                }
            ]
        }
    })


def get_topic_top_cases(specialty_uuid_filters):
    try:
        r = es.search(index=case_index_alias,
                      size=5,
                      timeout="30s",
                      sort=[{"trendScore": "desc"}, {"publishedAt": "desc"}],
                      query={
                          "bool": {
                              "should": [],
                              "filter": [
                                  {
                                      "term": {
                                          "caseState": "APPROVED"
                                      }
                                  },
                                  {
                                      "terms": {
                                          "specialtyUuids": specialty_uuid_filters
                                      }
                                  },
                                  {
                                      "nested": {
                                          "path": "media",
                                          "query": {
                                              "term": {
                                                  "media.type": "image"
                                              }
                                          }
                                      }
                                  }
                              ]
                          }
                      })
        return r['hits']['hits']
    except ElasticsearchException as e:
        logger.error(f"Error caught in search - {e}")
        return []


def trigger_update_case(case_uuid, case_detail=None, session=None):
    return add_or_update_case(case_uuid=case_uuid, session=session)


def add_campaign_data_to_case(case_uuid, session):
    campaign_detail = CampaignDetail.tactic_details(case_uuid=case_uuid, session=session)
    try:
        es.update(index=case_index_alias,
                  id=case_uuid,
                  retry_on_conflict=5,
                  doc=dict(campaignSettings=campaign_detail.dict()))
    except NotFoundError:
        logger.error("Tactic %s not found", case_uuid)
    except RequestError as re:
        logger.error("Failed to add or update campaign data on case %s, caught error %s", case_uuid, re)
    except ConflictError as ce:
        logger.error("Caught conflict trying to add or update campaign data on case %s, error %s", case_uuid, ce)


def add_or_update_case(case_uuid, session):
    case_detail = CaseDetail.elasticsearch_case_detail(case_uuid=case_uuid, session=session)

    logger.info(f"Updating case uuid {case_uuid}")
    try:
        es.update(index=case_index_alias,
                  id=case_uuid,
                  retry_on_conflict=5,
                  refresh=True,
                  doc=case_detail,
                  doc_as_upsert=True)
    except RequestError as re:
        logger.error("Failed to add or update case %s, caught error %s", case_uuid, re)
    except ConflictError as ce:
        logger.error("Caught conflict trying to add or update case %s, error %s", case_uuid, ce)

    if case_detail['caseState'] == 'SC_APPROVED':
        SponsoredContentCache().write_sponsored_content(items=[case_uuid])

    if case_detail['caseState'] in ['SC_REVIEW', 'SC_APPROVED', 'SC_DRAFT']:
        add_campaign_data_to_case(case_uuid=case_uuid, session=session)


def delete_case(case_uuid):
    try:
        es.delete_by_query(index="_all", body={
            "query": {
                "term": {
                    "caseUuid": {
                        "value": case_uuid
                    }
                }
            }
        })
    except RequestError as re:
        logger.error("Failed to delete case %s, caught error %s", case_uuid, re)
    except ConflictError as ce:
        logger.error("Caught conflict trying to delete case %s, error %s", case_uuid, ce)


def update_case_state(case_uuid, state: CaseState):
    updated_at = str(datetime.datetime.now(tz=datetime.timezone.utc))
    try:
        es.update(index=case_index_alias,
                  id=case_uuid,
                  retry_on_conflict=5,
                  doc=dict(caseState=state.name, updatedAt=updated_at))
    except NotFoundError:
        logger.error("Failed to find case %s in elasticsearch", case_uuid)
    logger.info("Updated case %s to state %s", case_uuid, state.name)


def update_case_fields(case_uuid, case_field_name, case_field_value):
    updated_at = str(datetime.datetime.now(tz=datetime.timezone.utc))
    try:
        es.update(index=case_index_alias,
                  id=case_uuid,
                  retry_on_conflict=5,
                  doc={
                      case_field_name: case_field_value,
                      'updatedAt': updated_at
                  })
    except RequestError as re:
        logger.error("Failed to update case field %s with value %s for case %s caught error %s",
                     case_field_name, case_field_value, case_uuid, re)
    except ConflictError as ce:
        logger.error("Failed to update case field %s with value %s for case %s caught error %s",
                     case_field_name, case_field_value, case_uuid, ce)


def update_case_reaction(case_uuid, reaction):
    """
    reactions is a dict of reaction names as the key and a list of user_uuid who reacted as values
    :param case_uuid:
    :param reaction:
    :return:
    """
    all_reactions = {}
    for k in reaction.keys():
        all_reactions.update({k: len(reaction.get(k))})
    updated_at = str(datetime.datetime.now(tz=datetime.timezone.utc))

    try:
        es.update(index=case_index_alias,
                  id=case_uuid,
                  retry_on_conflict=5,
                  doc=dict(allReactions=all_reactions, reactions=reaction, updatedAt=updated_at))
    except NotFoundError:
        logger.error("Case %s not found", case_uuid)
    except RequestError as re:
        logger.error("Failed to update case reaction for case %s", case_uuid, re)
    except ConflictError as ce:
        logger.error("Failed to update case reaction for case %s", case_uuid, ce)


def update_moderation_case_detail(session, case_uuid):
    full_case = CaseDetail.elasticsearch_case_detail(session=session, case_uuid=case_uuid)
    update = CaseDetail.elasticsearch_moderation_case_detail(session=session, case_uuid=case_uuid)
    if update:
        fc = {**update[case_uuid], **full_case}
    else:
        fc = full_case
    try:
        es.update(index=case_index_alias, id=case_uuid, retry_on_conflict=5, doc=fc)
        logging.info(f"Added to case uuid {case_uuid}")

    except RequestError as re:
        logger.error("Failed to update moderation case %s caught error %s", case_uuid, re)
    except ConflictError as ce:
        logger.error("Failed to update moderation case %s caught error %s", case_uuid, ce)
