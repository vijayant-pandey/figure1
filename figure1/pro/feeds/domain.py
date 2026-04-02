import logging
import json
from dogpile.cache.api import NO_VALUE
from figure1.cache_config import cache_region
from figure1.feeds import SponsoredContentTargets, \
    GroupFeed, \
    TopicFeed, \
    EverythingFeed, \
    MadeForYouFeed
from figure1.core import managed_session
from figure1.common.models.db import FeedType, FeedKind
from figure1.core import es
from figure1.exceptions import FeedNotFound, TooManyRequests
from figure1.common.types import Locale
from figure1.common.tracking import set_last_seen
from figure1.configuration import app_settings

logger = logging.getLogger('figure1.userfeed')


def _is_throttled(user_uid, feed_type_uuid):
    cache_key = feed_type_uuid + user_uid
    v = cache_region.get(key=cache_key, expiration_time=app_settings.feed_throttle_seconds)
    if v == NO_VALUE:
        cache_region.set(key=cache_key, value=None)
        return False
    return True


@managed_session
def generate_user_feed(user_uid,
                       feed_type_uuid,
                       sort_by=[],
                       filter_by=[],
                       update=False,
                       session=None,
                       feed_language=Locale.EN_US,
                       return_feed=False):
    kind = FeedType.get_kind_for_uuid(feed_type_uuid=feed_type_uuid, session=session)
    if not update and _is_throttled(user_uid=user_uid, feed_type_uuid=feed_type_uuid):
        logger.debug("Not an update and throttled")
        raise TooManyRequests()

    if kind is FeedKind.TOPIC:
        uf = TopicFeed(session=session,
                       es_client=es,
                       user_uid=user_uid,
                       feed_type_uuid=feed_type_uuid,
                       feed_language=feed_language)
    elif kind is FeedKind.GROUP:
        uf = GroupFeed(session=session,
                       es_client=es,
                       user_uid=user_uid,
                       feed_type_uuid=feed_type_uuid,
                       feed_language=feed_language)
    elif kind is FeedKind.MADE_FOR_YOU:
        uf = MadeForYouFeed(session=session,
                            es_client=es,
                            user_uid=user_uid,
                            feed_type_uuid=feed_type_uuid,
                            feed_language=feed_language)
    elif kind is FeedKind.EVERYTHING:
        uf = EverythingFeed(session=session,
                            es_client=es,
                            user_uid=user_uid,
                            feed_type_uuid=feed_type_uuid,
                            feed_language=feed_language)
    else:
        raise FeedNotFound(msg="Feed %s is unknown" % feed_type_uuid)

    if sort_by:
        uf.sort_fields = sort_by
        logger.debug("Setting sort fields to %s", sort_by)
    if filter_by:
        uf.feed_search_filters = filter_by
        logger.debug("Setting filter fields to %s", filter_by)
    if not update:
        logger.debug("Regenerating feed")
        uf.generate_feed(skip_delete=return_feed)
    set_last_seen(user_uuid=str(uf.user_uuid), session=session)
    feed_items = uf.get_feed_items(return_feed_items=return_feed)
    resp = {}
    if hasattr(uf, 'mfy_config'):
        q = uf.mfy_config.get_feed_query()
        try:
            q = json.loads(q)
        except json.JSONDecodeError:
            pass
        else:
            resp.update({"query": q})

    resp.update({'is_eof': uf.feed_config.get_eof(),
                 'cursor': uf.feed_config.get_cursor()})

    if feed_items:
        resp.update({'feed': feed_items})

    return resp


def get_targeted_uids(case_uuid):
    t = SponsoredContentTargets(caseUuid=case_uuid)
    return list(t.get_user_uids())


@managed_session
def get_user_targetted_tactics(user_uid, session):
    """
    Needs to be reworked
    :param user_uid:
    :param session:
    :return:
    """
    pass
    # user = User.get_user_by_uid(user_uid=user_uid, session=session)
    # target_data = UserDocument.get_user_target_data(user=user, session=session)
    # sp = SponsoredContent(user_uuid=user.user_uuid)
    # return {
    #     "userSponsoredData": sp.sponsored_config,
    #     "usertactics": sp.get_tactics()
    # }
