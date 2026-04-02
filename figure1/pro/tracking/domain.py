import logging
from figure1.common.helpers import user_uuid_from_uid
from figure1.store import UserFeedConfig, UserRFYFeedConfig, SponsoredContentCache
from figure1.feeds import get_all_sponsored_content

logger = logging.getLogger(__name__)


def handle_views(user_uid, feed_data, detail_views=False):
    """
    Write feed views to redis
    :param user_uid:
    :param feed_data:
    :param detail_views:
    :return: Tries to always return None unless there is an exception
    """
    logger.info("Handling views for user_uid %s, feed_data is %s", user_uid, feed_data)

    if not user_uid:
        return

    user_uuid = user_uuid_from_uid(user_uid)

    if SponsoredContentCache.get_sponsored_content_size() < 10:
        logger.debug("Writing sponsored content list")
        SponsoredContentCache.write_sponsored_content(list(get_all_sponsored_content()))

    if not user_uuid:
        logger.error("Failed to find user_uuid while writing feed views")
        return None

    if detail_views:
        logger.debug("Detail views being updated")
        case_uuid_list = feed_data.get('caseUuids', [])
        user_feed = UserRFYFeedConfig(user_uuid=user_uuid, feed_type_uuid=None)
        user_feed.set_detail_views(detail_views=case_uuid_list)

    feed_views = feed_data.get('views', [])
    logger.debug("Processing feed views %s", feed_views)
    for i in feed_views:
        case_uuid_list = i.get('caseUuids', [])
        feed_type_uuid = i.get('feedTypeUuid', None)

        if not feed_type_uuid and detail_views is False:
            return
        if not case_uuid_list:
            return
        case_uuid_list = [x for x in case_uuid_list if isinstance(x, str)]
        logger.debug("Writing feed views %s", case_uuid_list)
        user_feed = UserRFYFeedConfig(user_uuid=user_uuid, feed_type_uuid=feed_type_uuid)
        user_feed.set_feed_views(case_uuid_list)

    return None
