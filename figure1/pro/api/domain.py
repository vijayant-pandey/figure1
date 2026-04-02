import logging

from figure1.common.comms import sync_user_communication_preferences
from figure1.common.comms import sync_user_communication_preferences_v2
from figure1.common.elasticsearch import get_case
from figure1.common.helpers import FeedCard
from figure1.common.iterable import IterableSupportedWebHooks
from figure1.common.iterable import IterableWebHookBase
from figure1.common.iterable import bulk_update_users
from figure1.common.iterable.api import IterableAPI
from figure1.common.iterable.domain import get_subscription_preferences
from figure1.common.models.db import CommunicationSettings
from figure1.common.models.db import User
from figure1.common.models.db import UserCommunicationPreferences
from figure1.common.models.db.api_models import ApiUser
from figure1.core import managed_session
from figure1.feeds.feed_base import GenerateDataFeed
from figure1.store import IterableSyncQueue
from figure1.store import NewCaseHandler

logger = logging.getLogger('figure1.api')


def _update_user_preference(message_type_ids, user_uuid, subscribe, session):
    for m in message_type_ids:
        comms = session.query(CommunicationSettings) \
            .filter(CommunicationSettings.communication_iterable_message_type == m) \
            .one_or_none()
        if not comms:
            continue
        UserCommunicationPreferences.set_user_preference(user_uuid,
                                                         communication_uuid=comms.communication_uuid,
                                                         communication_setting=subscribe,
                                                         session=session)


def _unsubscribe_from_all_channels(email):
    iterable_api = IterableAPI()
    if iterable_api.iterable_api_disabled:
        logger.error("Iterable api is disabled")
        return
    return iterable_api.unsubscribe_user_from_all_channels(email=email)


@managed_session
def get_valid_token(token, session):
    """
    Compare the token to the tokens known and ensure it is valid. The Authorization object is an immutable dict
    representing the authorization headers.
    :param token:
    :return:
    """
    return ApiUser.validate_api_token(api_user_token=token, session=session)


@managed_session
def create_api_user(session):
    u = ApiUser.create_api_user(session=session)
    if u:
        return u.dict()


def push_to_user_update_queue(iterable_data):
    """
    On blast send, gather the users who have been sent to and ensure the profile is up to date. This just pushes data
    into a queue in redis, processing happens later.
    :param iterable_data:
    :return:
    """
    IterableSyncQueue.write(iterable_data.email)
    if IterableSyncQueue.get_queue_task() is None:
        bulk_update_users.delay()


@managed_session
def update_user_subscriptions(iterable_data: IterableWebHookBase, session):
    """
    :param session:
    :param iterable_data: Parsed webhook model
    :return:
    """
    user = User.get_user_by_email(email=iterable_data.email,
                                  session=session,
                                  raise_exception=True,
                                  include_deleted=True)

    if user.deleted_at is not None:
        logger.error("User has been deleted - forcing unsubscribe from all channels")
        resp = _unsubscribe_from_all_channels(email=iterable_data.email)
        if resp is None:
            return
        else:
            logger.info("Unsubscribe completed with response: %s", resp.dict())
            return

    pref = get_subscription_preferences(user_uuid=user.user_uuid, session=session)
    subscribed = set(pref.get("subscribed_message_types", []))
    unsubscribed = set(pref.get("unsubscribed_message_types", []))

    if iterable_data.dataFields.messageTypeIds:
        message_type_ids = set(iterable_data.dataFields.messageTypeIds)
    elif iterable_data.dataFields.messageTypeId:
        message_type_ids = {iterable_data.dataFields.messageTypeId}
    else:
        return

    if iterable_data.eventName == IterableSupportedWebHooks.emailSubscribe.value:
        logger.info("Handling subscribe request from user %s", iterable_data.email)
        _update_user_preference(message_type_ids=message_type_ids - subscribed,
                                user_uuid=user.user_uuid,
                                session=session,
                                subscribe=True)
        logger.debug("Iterable subscribe data received %s", iterable_data.json())
    elif iterable_data.eventName == IterableSupportedWebHooks.emailUnsubscribe.value:
        logger.info("Handling email un-subscribe request from user %s", iterable_data.email)
        _update_user_preference(message_type_ids=message_type_ids - unsubscribed,
                                user_uuid=user.user_uuid,
                                session=session,
                                subscribe=False)
        logger.debug("Iterable unsubscribe data received %s", iterable_data.json())
    elif iterable_data.eventName == IterableSupportedWebHooks.hostedUnsubscribeClick.value:
        logger.info("Handling hosted un-subscribe request from user %s", iterable_data.email)
        _update_user_preference(message_type_ids=message_type_ids - unsubscribed,
                                user_uuid=user.user_uuid,
                                session=session,
                                subscribe=False)
        logger.debug("Iterable hosted un-subscribe data received %s", iterable_data.json())
    else:
        raise Exception("Unsupported event passed %s", iterable_data.eventName)

    session.flush()
    sync_user_communication_preferences(user_uuid=str(user.user_uuid), session=session)
    sync_user_communication_preferences_v2(user_uuid=str(user.user_uuid), session=session)
    return {'success': "set communications preferences"}


def get_rfy_data_feed(user_uuid):
    df = GenerateDataFeed()
    return dict(feed_items=list(df.get_onboarding_cases(user_uuid=user_uuid)))


def get_case_by_uuid(case_uuid):
    c = get_case(case_uuid=case_uuid)
    if c:
        fc = FeedCard.feed_card(feed_item=c)
        if fc:
            return fc
    return None


def get_new_case_by_user(user_uuid):
    nc = NewCaseHandler()
    case = nc.get_new_case_by_user(user_uuid=user_uuid)
    if case:
        return get_case(case_uuid=case)
