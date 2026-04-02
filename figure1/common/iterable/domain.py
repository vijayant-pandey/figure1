import json
import logging
import time
from typing import List

from pydantic import ValidationError
from sqlalchemy.orm import Session

from figure1.common.helpers import UserDocument
from figure1.common.models.db import CommunicationChannel
from figure1.common.models.db import CommunicationSettings
from figure1.common.models.db import FeedType
from figure1.common.models.db import User
from figure1.common.models.db import UserChannelPreferences
from figure1.common.models.db import UserCommunicationPreferences
from figure1.common.models.db import UserDeviceNotificationToken
from figure1.common.models.db import UserFeedSubscription
from figure1.common.models.db import UserState
from figure1.common.types import SupportedDeviceTypes
from figure1.common.utils.date_utils import utc_now
from figure1.core import managed_session
from figure1.exceptions import IterableAPIException
from figure1.exceptions import IterableOverloadedException
from figure1.exceptions import IterableUnsupportedDeviceType
from figure1.exceptions import IterableUserNotFound
from figure1.notifications.iterable import ItblBulkUserObject
from figure1.notifications.iterable import ItblUserBulkUpdate
from figure1.notifications.iterable import ItblUserProfile
from figure1.notifications.iterable import ItblUserProfileTarget
from figure1.store import IterableSyncQueue
from .api import IterableAPI

logger = logging.getLogger('figure1.iterable')


@managed_session
def generate_iterable_user_object(user_uuid, session, phone_number=None) -> ItblUserProfile:
    """
    Given user uuid, generate an up to date user object described by ItblUserProfile. This object is intended only for
    use with iterable.
    This function generates the fields negotiated with marketing that should be updated in iterable.

    :param user_uuid:
    :param session:
    :return:
    """
    user_detail = UserDocument.user_detail(user_uuid=user_uuid, session=session)

    if user_detail.get('interests'):
        interests = [x.get("interestName") for x in user_detail['interests']]
        user_detail.update({'interests': interests})

    st = user_detail.get("specialtyName")
    user_detail.update({'primarySpecialty': st})

    user_detail.update({'specialtyList': set()})
    for ss in user_detail.get("secondarySpecialties", []):
        specialty = None
        if ss.get("tree", {}):
            if ss.get("tree").get("specialty", None):
                specialty = ss.get("tree").get("specialty", None).get("specialtyName", "")
        if specialty:
            user_detail['specialtyList'].add(specialty)
        if user_detail.get("primarySpecialty"):
            user_detail['specialtyList'].add(user_detail.get("primarySpecialty"))

    user_detail.update({'subscribedChannels': set()})
    for subscribed_feed in UserFeedSubscription.get_subscribed_feeds(user_uuid=user_uuid, session=session):
        feed_detail = FeedType.get_feed_from_type_uuid(feed_type_uuid=subscribed_feed.get("feedTypeUuid"),
                                                       session=session)
        if feed_detail.name:
            user_detail['subscribedChannels'].add(feed_detail.name)

    if user_detail.get("country"):
        uc = user_detail.get("country", {}).get("countryName")
        user_detail.update({"country": uc})

    if not user_detail.get("legacyAccount"):
        user_detail.update({'legacyAccount': False})

    if user_detail.get("userBio"):
        user_detail.update({"isBio": True})
    else:
        user_detail.update({"isBio": False})

    if user_detail.get("avatar"):
        user_detail.update({"isAvatar": True})
    else:
        user_detail.update({"isAvatar": False})

    if user_detail.get("practiceHospital"):
        user_detail.update({"isPracticeHospital": True})
    else:
        user_detail.update({"isPracticeHospital": False})

    if user_detail.get("practiceLocation"):
        user_detail.update({"isPracticeLocation": True})
    else:
        user_detail.update({"isPracticeLocation": False})

    if user_detail.get("education"):
        user_detail.update({"isEducation": True})
    else:
        user_detail.update({"isEducation": False})

    if user_detail.get("experience"):
        user_detail.update({"isExperience": True})
    else:
        user_detail.update({"isExperience": False})

    if user_detail.get("affiliations"):
        user_detail.update({"isAffiliations": True})
    else:
        user_detail.update({"isAffiliations": False})

    if phone_number:
        user_detail.update({'phoneNumber': phone_number})

    targetable = ItblUserProfileTarget.parse_obj(user_detail)
    user = ItblUserProfile.parse_obj(user_detail)
    user.targetV1 = targetable
    return user


def get_subscription_preferences(user_uuid, session):
    """
    If a user has been marked as deleted - skip straight to unsubscribing from all channels. Note that this
    does not record the user preferences.
    """
    subscribed_message_types = []
    unsubscribed_message_types = []
    unsubscribed_channel_types = []

    u = User.q.get(user_uuid)
    if u.deleted_at is not None:
        logger.error("User is marked deleted - unsubscribe from all channels")
        for pref in CommunicationChannel.q.all():
            unsubscribed_channel_types.append(pref.communication_channel_id)
        return dict(subscribed_message_types=subscribed_message_types,
                    unsubscribed_message_types=unsubscribed_message_types,
                    unsubscribed_channel_types=unsubscribed_channel_types, )

    for pref in UserCommunicationPreferences.get_preference_uuid_settings(user_uuid=user_uuid, session=session):
        comm_uuid, message_type, preference_setting = pref
        if preference_setting is False:
            unsubscribed_message_types.append(message_type)
        elif preference_setting is True:
            subscribed_message_types.append(message_type)

    for pref in UserChannelPreferences.get_preference_uuid_settings(user_uuid=user_uuid, session=session):
        comm_uuid, message_type, preference_setting = pref
        if preference_setting is False:
            unsubscribed_channel_types.append(message_type)

    return dict(subscribed_message_types=subscribed_message_types,
                unsubscribed_message_types=unsubscribed_message_types,
                unsubscribed_channel_types=unsubscribed_channel_types, )


def update_user_comm_preferences(user_uuid, session, email):
    """
    This is a receiver that is called when a user's preferences are updated. Calling this triggers a task to synchronize
    a users preferences to iterable.
    :param user_uuid:
    :param session:
    :param email: User's email - required for iterable
    :return:
    """
    return None
    # DISABLING BELOW SINCE THE MESSAGE TYPES DON'T EVEN EXIST IN ITERABLE (Oct 2, 2025 - Felman)
    # iterable_client = IterableAPI()
    # if iterable_client.iterable_api_disabled:
    #     logger.error("Iterable api is disabled, nothing to do")
    #     return None

    # pref = get_subscription_preferences(user_uuid=user_uuid, session=session)
    # unsubscribed_channel_types = pref.get("unsubscribed_channel_types", [])

    # iterable_client.subscribe_user(email=email, message_type_ids=pref.get("subscribed_message_types", []))
    # iterable_client.unsubscribe_user(email=email,
    #                                  message_type_ids=pref.get("unsubscribed_message_types", []),
    #                                  channel_type_ids=unsubscribed_channel_types)


def sync_anonymous_user_comm_preferences(email: str,
                                         user_uuid: str,
                                         subscribed_uuids: List[str],
                                         session: Session):
    """
    Updates the email preferences for an anonymous user.  This subscribes an email address to the message types
    associated with the communication uuids given.

    The first time an email is synced all other message types will be unsubscribed.
    :param email:
    :param user_uuid:
    :param subscribed_uuids:
    :param session:
    :return:
    """
    iterable_client = IterableAPI()
    if iterable_client.iterable_api_disabled:
        logger.error("Iterable api is disabled, nothing to do")
        return None

    try:
        iterable_client.get_iterable_user_by_email(email=email)
        requires_unsubscribe = False
    except IterableUserNotFound:
        logging.info(f"User %s not found in iterable, creating in iterable", email)
        profile = ItblUserProfile(email=email, userUuid=user_uuid)
        iterable_client.update_user(
            email=email,
            data_fields=profile.dict()
        )
        requires_unsubscribe = True

    # DISABLING BELOW SINCE THE MESSAGE TYPES DON'T EVEN EXIST IN ITERABLE (Oct 2, 2025 - Felman)
    # subscribed_message_types = []
    # unsubscribed_message_types = []

    # for cs in session.query(CommunicationSettings) \
    #         .filter(CommunicationSettings.communication_iterable_message_type != 0) \
    #         .all():
    #     if str(cs.communication_uuid) in subscribed_uuids:
    #         subscribed_message_types.append(cs.communication_iterable_message_type)
    #     else:
    #         unsubscribed_message_types.append(cs.communication_iterable_message_type)

    # logging.info(f"Subscribing user %s to: %s", email, subscribed_message_types)
    # iterable_client.subscribe_user(email=email, message_type_ids=subscribed_message_types)

    # if requires_unsubscribe:
    #     logging.info(f"Unsubscribing user %s from: %s", email, unsubscribed_message_types)
    #     iterable_client.unsubscribe_user(email=email, message_type_ids=unsubscribed_message_types)


@managed_session
def sync_user_to_iterable(user_uuid, session, phone_number=None): # works with sign up service
    """
    Call to sync a single user to iterable.
    :param user_uuid:
    :param session:
    :param phone_number: Optional - only used on verification
    :return:
    """
    iterable_client = IterableAPI()
    if iterable_client.iterable_api_disabled:
        logger.error("Iterable api is disabled, nothing to do")
        return None
    iterable_user_object = generate_iterable_user_object(user_uuid=user_uuid,
                                                         session=session,
                                                         phone_number=phone_number)

    iterable_client.update_user(
        email=iterable_user_object.email,
        data_fields=iterable_user_object.dict()
    )
    u = UserState()
    u.user_uuid = user_uuid
    u.last_iterable_sync = utc_now(timezone=True)

    # DISABLING BELOW SINCE THE MESSAGE TYPES DON'T EVEN EXIST IN ITERABLE (Oct 2, 2025 - Felman)
    # if iterable_user_object.isDeleted is True:
    #     iterable_client.unsubscribe_user_from_all_channels(email=iterable_user_object.email)
    return session.merge(u)


def sync_user_group_filter_to_iterable(email, group_filter_uuid):
    user_details = {"email": email, "groupFilterUuid": group_filter_uuid}

    iterable_client = IterableAPI()
    if iterable_client.iterable_api_disabled:
        logger.error("Iterable api is disabled, nothing to do")
        return None

    iterable_client.update_user(
        email=email,
        data_fields=user_details
    )


def sync_user_device_to_iterable(email, device_user_token, device_language=None):
    iterable_client = IterableAPI()
    if iterable_client.iterable_api_disabled:
        logger.error("Iterable api is disabled, nothing to do")
        return None

    device_type = device_user_token.get('device_type')
    device_token = device_user_token.get('fcm_token')

    if device_type.upper() not in SupportedDeviceTypes.__members__:
        raise IterableUnsupportedDeviceType("Device type is unsupported")

    iterable_client.register_device_token(
        email=email,
        device_type=device_type,
        device_token=device_token,
        device_language=device_language
    )


def sync_user_device_notification_to_iterable(email, device_user_token, notification_enabled):
    iterable_client = IterableAPI()
    if iterable_client.iterable_api_disabled:
        logger.error("Iterable api is disabled, nothing to do")
        return None

    device_type = device_user_token.get('device_type')
    device_token = device_user_token.get('fcm_token')

    if device_type.upper() not in SupportedDeviceTypes.__members__:
        raise IterableUnsupportedDeviceType("Device type is unsupported")

    iterable_user_devices = iterable_client.get_iterable_user_by_email(email=email)['user']['dataFields'] \
        .get('devices', [])

    device = {}
    for each_device in iterable_user_devices:
        if each_device['token'] == device_token:
            device = each_device
            break

    device_language = device.get('deviceLanguage')
    iterable_client.register_device_token(
        email=email,
        device_type=device_type,
        device_token=device_token,
        notification_enabled=notification_enabled,
        device_language=device_language,
    )


@managed_session
def update_tokens_and_sync(device_user_tokens, user_uuid, email, session):
    iterable_client = IterableAPI()
    if iterable_client.iterable_api_disabled:
        logger.error("Iterable api is disabled, nothing to do")
        return None
    for udt in device_user_tokens:
        device_id = udt.get("device_id")
        device_type = udt.get("device_type")
        device_token = udt.get("fcm_token")
        device_language = udt.get("device_language")

        if device_type.upper() not in SupportedDeviceTypes.__members__:
            raise IterableUnsupportedDeviceType("Device type is unsupported")

        UserDeviceNotificationToken.create_or_update(
            user_uuid=user_uuid,
            device_id=device_id,
            device_type=device_type,
            fcm_token=device_token,
            session=session)

        iterable_client.register_device_token(
            email=email,
            device_type=device_type,
            device_token=device_token,
            device_language=device_language
        )
        session.flush()


@managed_session
def set_iterable_user_deleted_flag(email, session):
    """
    Sets the isDeleted flag for a user to True. If the user has this flag set already, True is returned, if the user
    is updated, 'updated' is returned.
    IterableUserNotFound is raised if the user isn't in iterable.

    """

    iterable_client = IterableAPI()
    if iterable_client.iterable_api_disabled:
        logger.error("Iterable api is disabled, nothing to do")
        return None
    else:
        iterable_user = iterable_client.get_iterable_user_by_email(email, wait_for_user=True)
        try:
            is_user_deleted = iterable_user['user']['dataFields'].get("isDeleted", False)
        except KeyError:
            logger.error("Incorrect data structure found - %s", iterable_user)
            return False
        else:
            if is_user_deleted is True:
                return is_user_deleted
            else:
                iterable_client.update_user(email=email, data_fields={'isDeleted': True})
                return 'updated'


@managed_session
def sync_deleted_users(session, email=None, offset=0, limit=10):
    """
    If an email is passed, then make sure that profile is moved in iterable, otherwise, go through deleted users and
    ensure they are correctly set in iterable.
    If the email passed has the isDeleted flag set to True, then the profile is moved to <user_uuid>@figure1.com

    """
    deleted_users = []
    failed_users = []
    not_found_users = []
    retry_users = []
    iterable_client = IterableAPI()
    if iterable_client.iterable_api_disabled:
        logger.error("Iterable api disabled, nothing to do")
        return dict(retry_users=retry_users,
                    not_found_users=not_found_users,
                    failed_users=failed_users,
                    deleted_users=deleted_users,
                    result_count=0)

    def _handle_iterable_delete(email):
        try:
            iterable_user = iterable_client.get_iterable_user_by_email(email, wait_for_user=False)
            logger.info("Attempting to delete iterable user %s", iterable_user)
        except IterableUserNotFound:
            logger.error("Unable to find iterable user by original email(%s)", email)
            not_found_users.append(email)
        except IterableAPIException as ie:
            if ie.status == 'InvalidEmailAddressError':
                logger.error("Invalid email")
                failed_users.append(email)
                return
            else:
                raise
        else:
            try:
                is_user_deleted = iterable_user['user']['dataFields'].get("isDeleted", False)
            except KeyError:
                logger.error("User does not have expected structure - %s", iterable_user)
                is_user_deleted = False
            if is_user_deleted is True:
                iterable_client.unsubscribe_user_from_all_channels(email=email)

            else:
                logger.error("Iterable user should be deleted but isn't marked correctly")
                set_iterable_user_deleted_flag(email)
                iterable_client.unsubscribe_user_from_all_channels(email=email)

    q = session.query(User.user_uuid, User.email) \
        .filter(User.deleted_at.isnot(None)) \
        .order_by(User.deleted_at.desc())

    result_count = 0
    if email:
        q = q.filter(User.email == email)
    else:
        result_count = q.count()
        logger.info("Updating %s deleted users in iterable", result_count)
        if offset >= result_count:
            return dict(retry_users=retry_users,
                        not_found_users=not_found_users,
                        failed_users=failed_users,
                        deleted_users=deleted_users,
                        result_count=result_count)
    if offset:
        q = q.offset(offset)
    q = q.limit(limit)

    for u in q.all():
        try:
            _handle_iterable_delete(email=u[1])
        except IterableOverloadedException:
            logger.error("Iterable overloaded, waiting 5 seconds to try again")
            retry_users.append((u[1],))
            time.sleep(5)
        except json.JSONDecodeError:
            retry_users.append((u[1],))
            time.sleep(5)

    while retry_users:
        for r in retry_users:

            try:
                _handle_iterable_delete(email=r[0])
            except IterableOverloadedException:
                logger.error("Iterable overloaded, waiting for 5 seconds to continue")
                time.sleep(5)
            except json.JSONDecodeError:
                time.sleep(5)
            else:
                retry_users.remove(r)

    return dict(retry_users=retry_users,
                not_found_users=not_found_users,
                failed_users=failed_users,
                deleted_users=deleted_users,
                result_count=result_count)


def get_user_for_bulk_update(user_uuid, session):
    u = generate_iterable_user_object(user_uuid=user_uuid, session=session)
    return ItblBulkUserObject(email=u.email, userId=u.userUuid, dataFields=u)


def get_user_comm_preference_for_bulk_update(user_uuid, session):
    return get_subscription_preferences(user_uuid=user_uuid, session=session)


def reset_user_communication_preferences(user_uuid, session):
    UserCommunicationPreferences.reset_user_preferences(user_uuid=user_uuid, session=session)
    session.flush()
    UserCommunicationPreferences.initialize_user_communication_preferences(user_uuid=user_uuid, session=session)


def bulk_update_user(chunk_size=1000, session=None):
    iterable_client = IterableAPI()
    if iterable_client.iterable_api_disabled:
        logger.error("Iterable api is disabled")
        return None

    user_update = []
    count = 0

    logger.info("Current queue length is %s", IterableSyncQueue.get_queue_len())
    for email in IterableSyncQueue():
        user = User.get_user_by_email(email=email, session=session, raise_exception=False)
        if not user:
            logger.error("Failed to find user %s", email)
            continue
        try:
            it_prof = get_user_for_bulk_update(user_uuid=user.user_uuid, session=session)
        except ValidationError:
            logger.error("User uuid %s failed to validate", user.user_uuid)
            continue
        if it_prof.dataFields.isDeleted is True:
            iterable_client.unsubscribe_user_from_all_channels(email=it_prof.email)

        user_update.append(it_prof)
        count += 1

        if not len(user_update) % chunk_size or IterableSyncQueue.get_queue_len() == 0:
            update_object = ItblUserBulkUpdate(users=user_update)
            logger.info("Running bulk user update for %s users", len(user_update))
            ret = iterable_client.bulk_update_user(update_object=update_object)
            logger.info("Bulk user update request returned %s", ret)
            user_update = []


def get_iterable_subscribed_message_types(email: str):
    iterable_client = IterableAPI()
    if iterable_client.iterable_api_disabled:
        logger.error("Iterable api is disabled")
        return []

    user = iterable_client.get_iterable_user_by_email(email=email)
    return user.get('user', {}).get('dataFields', {}).get('subscribedMessageTypeIds', [])
