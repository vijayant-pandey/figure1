import logging

from elasticsearch_dsl import Document
from figure1.core import es
from figure1.configuration import es_settings
from figure1.common.helpers import FeedCard
from figure1.store import Recommended
from elasticsearch.exceptions import NotFoundError

logger = logging.getLogger('figure1.api')


def get_feed_card(case_uuid):
    try:
        doc = Document.get(id=case_uuid, using=es, index=es_settings.cases_alias)
    except NotFoundError:
        logger.error("Case %s not found", case_uuid)
        return None

    return FeedCard.feed_card(feed_item=doc.to_dict())


def get_recommended(user_uuid):
    case_uuid = Recommended.get_user_recommended_case(user_uuid=user_uuid)
    if case_uuid:
        logger.debug("Recommended case %s for user %s", case_uuid, user_uuid)
        feed_card = get_feed_card(case_uuid)
        if not feed_card:
            logger.error("Unable to populate feed card for case %s and user %s", case_uuid, user_uuid)
        Recommended.set_sent_user_recommendation(user_uuid=user_uuid, case_uuid=case_uuid)
        return feed_card

    else:
        logger.error("No case found for user %s", user_uuid)
        Recommended.regenerate_user(user_uuid=user_uuid)
