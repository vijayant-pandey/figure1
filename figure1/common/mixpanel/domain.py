import logging

from mixpanel import MixpanelException

from figure1.common.helpers import UserDocument
from figure1.common.mixpanel.api import MixpanelAPI
from figure1.common.models.db import UserFeedSubscription, FeedType
from figure1.common.types.user_tracking import MixpanelUserData, MixpanelLegacyUserData, MixpanelUserDeviceData

logger = logging.getLogger('figure1.mixpanel')


def _get_subscribed_feeds(user_uuid, session):
    """
    Returns a list of the feed names that a user is subscribed to
    """
    for subscribed_feed in UserFeedSubscription.get_subscribed_feeds(user_uuid=user_uuid, session=session):
        feed_detail = FeedType.get_feed_from_type_uuid(feed_type_uuid=subscribed_feed.get("feedTypeUuid"),
                                                       session=session)
        if feed_detail.name:
            yield feed_detail.name


def sync_user_to_mixpanel(user_uuid, session):
    api = MixpanelAPI()
    if api.mixpanel_api_disabled:
        logger.info("Mixpanel api is disabled, nothing to do")
        return

    user_detail = UserDocument.user_detail(user_uuid=user_uuid, session=session)
    user_detail.update({
        "subscribedChannels": list(_get_subscribed_feeds(user_uuid=user_uuid, session=session))
    })
    user_data = MixpanelUserData.parse_obj(user_detail).dict(by_alias=True)

    try:
        api.client.people_set(distinct_id=str(user_uuid),
                              properties=user_data)
    except MixpanelException as e:
        logging.error(f"Failed to send mixpanel update for user {user_uuid}: {e}")
        raise


def sync_user_device_to_mixpanel(user_uuid, device):
    api = MixpanelAPI()
    if api.mixpanel_api_disabled:
        logger.info("Mixpanel api is disabled, nothing to do")
        return

    user_device = MixpanelUserDeviceData.parse_obj(device).dict(by_alias=True)
    user_device_data = {"Devices": [user_device]}
    try:
        api.client.people_union(distinct_id=str(user_uuid),
                                properties=user_device_data)
    except MixpanelException as e:
        logging.error(f"Failed to send mixpanel update for user device {user_uuid}: {e}")
        raise


def sync_user_devices_to_mixpanel(user_uuid, devices):
    for each in devices:
        mixpanel_user_device = {
            "deviceId": each.get("device_id"),
            "deviceType": each.get("device_type"),
            "deviceLanguage": each.get("device_language")
        }

        sync_user_device_to_mixpanel(user_uuid, mixpanel_user_device)


def sync_user_legacy_data_to_mixpanel(user_uuid, session):
    api = MixpanelAPI()
    if api.mixpanel_api_disabled:
        logger.info("Mixpanel api is disabled, nothing to do")
        return

    user_detail = UserDocument.user_detail(user_uuid=user_uuid, session=session)
    profession_label = user_detail.get('primarySpecialty', {}) \
        .get('tree', {}) \
        .get('profession', {}) \
        .get('professionLabel')
    if profession_label:
        hcp = profession_label not in ['non-healthcareprofessional', 'othernon-hcpstudent']
        mapped_profession = profession_label not in ['nursingprofessional', 'otherhealthcareprofessional']
        user_detail.update({
            'hcp': hcp,
            'mappedProfession': mapped_profession
        })
    specialty = user_detail.get('primarySpecialty', {}).get('tree', {}).get('specialty')
    user_detail['mappedSpecialty'] = specialty is not None

    mixpanel_data = MixpanelLegacyUserData.parse_obj(user_detail).dict(by_alias=True)

    try:
        api.client.people_set(distinct_id=str(user_uuid),
                              properties=mixpanel_data)
    except MixpanelException as e:
        logging.error(f"Failed to send mixpanel update for user {user_uuid}: {e}")
        raise


def send_event_to_mixpanel(user_uuid, event_name, properties):
    api = MixpanelAPI()
    if api.mixpanel_api_disabled:
        logger.info("Mixpanel api is disabled, nothing to do")
        return

    try:
        api.client.track(distinct_id=str(user_uuid), event_name=event_name, properties=properties)
    except MixpanelException as e:
        logging.error(f"Failed to send mixpanel event {event_name} for user {user_uuid}: {e}")
        raise
