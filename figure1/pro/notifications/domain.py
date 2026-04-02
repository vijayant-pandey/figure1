import logging

from figure1.common.firebase import do_firebase_sync
from figure1.common.iterable.iterable_tasks import sync_user_device_notification_to_iterable_task
from figure1.common.mixpanel.tasks import sync_user_device_tokens_to_mixpanel_task
from figure1.common.models.firebase import FirebaseCollectionManager
from figure1.common.models.firebase import sync_user_notifications_task
from figure1.common.iterable import sync_device_tokens_task
from figure1.common.types.notification import UserNotificationState
from figure1.core import managed_session, translate_client
from figure1.common.models.db import UserCommunicationPreferences
from figure1.common.models.db import User
from figure1.common.models.db import UserNotification
from figure1.events import UserEvents
from figure1.exceptions import NotificationException
from figure1.exceptions.notification import InvalidDeviceLanguage

fb = FirebaseCollectionManager()

logger = logging.getLogger(__name__)


def _update_firestore_document(user_uid, preferences, preference_type, reset=False):
    """
    Updates preferences in firestore on update.
    :param user_uid:
    :param preferences: User preferences object
    :param reset: boolean - Set this to force overwrite the target preferences document
    :return: None
    """

    fb.set_fs_client(documents=[user_uid, preference_type], collections=['usersDB', 'userPreferences'])

    if reset:
        fb.set({preference_type: preferences}, merge=False)
    else:
        fb.set({preference_type: preferences}, merge=True)


def _validate_devices_language(devices):
    translate = translate_client()

    if not translate:
        logger.error("Translate api is disabled")
        return

    google_supported_languages = [each.get('language') for each in translate.get_languages()]
    for each in devices:
        if each.get('device_language'):
            if not each.get('device_language') in google_supported_languages:
                raise InvalidDeviceLanguage()


@managed_session
def handle_update_tokens_and_sync(device_user_tokens, user_uid, session=None):
    _validate_devices_language(device_user_tokens)
    user = User.get_user_by_uid(user_uid, session, raise_exception=True)

    task = sync_device_tokens_task.si(user_uid=user_uid, device_user_tokens=device_user_tokens)
    task.link(sync_user_device_tokens_to_mixpanel_task.si(user_uuid=user.user_uuid,
                                                          device_user_tokens=device_user_tokens))
    task.link(do_firebase_sync.si(firebasemodel='FirebaseUserDeviceNotificationTokensDB', uuid=str(user.user_uuid)))
    task.apply_async()

    return {'success': f"Updated Tokens for User by id={user_uid}"}


@managed_session
def handle_update_user_device_notification_and_sync(device, notification_enabled, user_uuid, session=None):
    user = User.get_user_by_uuid(user_uuid, session, raise_exception=True)
    task = sync_user_device_notification_to_iterable_task.si(user.email, device, notification_enabled)
    task.apply_async()

    return {'success': f"Updated Device notification for User by uuid={user_uuid}"}


@managed_session
def get_default_preferences(session):
    return UserCommunicationPreferences.get_default_preferences_v2(session=session)


@managed_session
def sync_user_communication_preferences(user_uid, session):
    user_uuid = User.get_user_uuid_by_uid(user_uid, session=session, raise_exception=False)
    if not user_uuid:
        return {'error': 'User not found, probably anonymous'}
    UserEvents.USER_COMM_PREFS_UPDATED(user_uuid=user_uuid, session=session)
    return {'success': f"started communications preferences sync"}


@managed_session
def update_user_communication_preferences(user_uid, preference_list, session):
    user = User.get_user_by_uid(user_uid=user_uid, session=session, raise_exception=True)
    for p in preference_list:
        UserCommunicationPreferences.set_user_preference(user_uuid=user.user_uuid,
                                                         communication_uuid=p.get("communication_uuid"),
                                                         communication_setting=p.get("setting"),
                                                         session=session)
    session.flush()
    UserEvents.USER_COMM_PREFS_UPDATED(user_uuid=user.user_uuid, session=session)
    return {'success': f"set communications preferences"}


@managed_session
def reset_user_preferences(user_uid, session):
    user_uuid = User.get_user_uuid_by_uid(user_uid, session=session, raise_exception=True)
    UserCommunicationPreferences.reset_user_preferences(user_uuid=user_uuid, session=session)
    UserEvents.USER_COMM_PREFS_UPDATED(user_uuid=user_uuid, session=session)
    return {'success': f"reset communications preferences"}


@managed_session
def sync_user_notifications(user_uid, session):
    user_uuid = User.get_user_uuid_by_uid(user_uid=user_uid, session=session, raise_exception=True)
    sync_user_notifications_task.delay(user_uuid=user_uuid)
    return {'success': "Started task to sync user notifications"}


@managed_session
def mark_user_notifications_acknowledged(user_uid, session):
    user_uuid = User.get_user_uuid_by_uid(user_uid=user_uid, session=session, raise_exception=True)
    UserNotification.acknowledge_all_new(user_uuid=user_uuid, session=session)
    return {'success': "Marked as acknowledged, started task to sync user notifications"}


@managed_session
def mark_single_user_notification_acknowledged(user_uid, notification_uuid, session):
    user_uuid = User.get_user_uuid_by_uid(user_uid=user_uid, session=session, raise_exception=True)
    un = UserNotification.get_notification_by_uuid(notification_uuid=notification_uuid, session=session)
    if un.user_uuid != user_uuid:
        raise NotificationException(return_code=403,
                                    msg="Only the owner of a notification can mark it as acknowledged.")
    un.state = UserNotificationState.ACKNOWLEDGED
    session.merge(un)
    return {'success': "Marked as acknowledged"}


@managed_session
def mark_user_notifications_read(user_uid, session):
    user_uuid = User.get_user_uuid_by_uid(user_uid=user_uid, session=session, raise_exception=True)
    UserNotification.read_all(user_uuid=user_uuid, session=session)
    return {'success': "Marked as read, started task to sync user notifications"}


@managed_session
def mark_single_user_notification_read(user_uid, notification_uuid, session):
    user_uuid = User.get_user_uuid_by_uid(user_uid=user_uid, session=session, raise_exception=True)
    un = UserNotification.get_notification_by_uuid(notification_uuid=notification_uuid, session=session)
    if un.user_uuid != user_uuid:
        raise NotificationException(return_code=403, msg="Only the owner of a notification can mark it as read.")
    UserNotification.read_notification(notification_uuid=notification_uuid, session=session)
    return {'success': "Marked as read"}
