import logging
import datetime
from elasticsearch.exceptions import RequestError, ConflictError
from figure1.core import es
from figure1.configuration import es_settings
from figure1.common.types import CampaignState
from figure1.common.helpers import CampaignDetail

campaigns_index_alias = es_settings.campaign_alias

logger = logging.getLogger(__name__)


def add_or_update_campaign(campaign_uuid, campaign_detail=None, session=None):
    if not campaign_detail:
        campaign_detail = CampaignDetail.elasticsearch_campaign(campaign_uuid=campaign_uuid, session=session)

    try:
        es.update(index=campaigns_index_alias,
                  id=campaign_uuid,
                  retry_on_conflict=5,
                  doc=campaign_detail,
                  doc_as_upsert=True)
    except RequestError as re:
        logger.error("Failed to add or update campaing %s, caught error %s", campaign_uuid, re)
    except ConflictError as ce:
        logger.error("Caught conflict trying to update campaign %s, error %s", campaign_uuid, ce)


def update_campaign_state(campaign_uuid, state: CampaignState):
    updated_at = str(datetime.datetime.now(tz=datetime.timezone.utc))
    try:
        es.update(index=campaigns_index_alias,
                  id=campaign_uuid,
                  retry_on_conflict=5,
                  doc=dict(state=state.name, updatedAt=updated_at))
    except RequestError as re:
        logger.error("Failed to add or update campaign state for campaign %s, caught error %s", campaign_uuid, re)
    except ConflictError as ce:
        logger.error("Caught conflict trying to update campaign state for campaign %s, error %s", campaign_uuid, ce)


def update_campaign_fields(campaign_uuid, campaign_field_name, campaign_field_value):
    updated_at = str(datetime.datetime.now(tz=datetime.timezone.utc))
    try:
        es.update(index=campaigns_index_alias,
                  id=campaign_uuid,
                  retry_on_conflict=5,
                  doc=dict(campaign_field_name=campaign_field_value, updatedAt=updated_at))
    except RequestError as re:
        logger.error("Failed to update campaign field %s with value %s for campaign %s caught error %s",
                     campaign_field_name, campaign_field_value, campaign_uuid, re)
    except ConflictError as ce:
        logger.error("Failed to update campaign field %s with value %s for campaign %s caught error %s",
                     campaign_field_name, campaign_field_value, campaign_uuid, ce)
