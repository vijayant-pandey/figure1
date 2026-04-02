import logging
from typing import List

from celery.exceptions import MaxRetriesExceededError
from requests.exceptions import ReadTimeout

from figure1.common.models.db import CommunicationSettings
from figure1.common.models.db import User
from figure1.common.models.db import UserCommunicationPreferences
from figure1.common.models.db import UserNotification
from figure1.core import TaskBase
from figure1.core import celery_app
from figure1.exceptions import IterableException
from figure1.exceptions import IterableOverloadedException
from figure1.exceptions import IterableUserNotFound
from figure1.exceptions import UserNotFound
from figure1.store import IterableSyncQueue
from . import IterableAPI
from .domain import bulk_update_user
from .domain import get_iterable_subscribed_message_types
from .domain import set_iterable_user_deleted_flag
from .domain import sync_anonymous_user_comm_preferences
from .domain import sync_deleted_users
from .domain import sync_user_device_notification_to_iterable
from .domain import sync_user_device_to_iterable
from .domain import sync_user_to_iterable
from .domain import update_tokens_and_sync
from .domain import update_user_comm_preferences

logger = logging.getLogger("figure1.common.iterable.task")


@celery_app.task(bind=True,
                 base=TaskBase,
                 autoretry_for=(IterableOverloadedException,),
                 retry_backoff=True,
                 rate_limit='1/s',
                 name='figure1.backend.update_iterable_user')
def update_iterable_user(self, user_uid=None, user_uuid=None, phone_number=None):
    """
    Synchronizes user with iterable
    :return:
    """
    if user_uid:
        user = User.get_user_by_uid(user_uid=user_uid, session=self.session, raise_exception=True)
    elif user_uuid:
        user = User.get_user_by_uuid(user_uuid=user_uuid, session=self.session, raise_exception=True)
    else:
        raise UserNotFound(msg="No user identifier found")

    sync_user_to_iterable(user_uuid=str(user.user_uuid), session=self.session, phone_number=phone_number)


@celery_app.task(bind=True,
                 base=TaskBase,
                 autoretry_for=(IterableOverloadedException,),
                 retry_backoff=True,
                 rate_limit='1/s',
                 name='figure1.backend.update_iterable_user_device_language')
def update_iterable_user_device_language(self, email, device, device_language):
    sync_user_device_to_iterable(email, device, device_language)


@celery_app.task(bind=True,
                 base=TaskBase,
                 autoretry_for=(IterableOverloadedException, IterableUserNotFound),
                 retry_backoff=10,
                 rate_limit='1/s',
                 name='figure1.backend.update_iterable_user_communication_prefs')
def update_iterable_user_comm_preferences(self, user_uid=None, user_uuid=None):
    """
    Synchronizes user subscriptions with iterable, if a user is not in iterable, they are created and the task is
    retried
    :return:
    """

    if user_uid:
        user = User.get_user_by_uid(user_uid=user_uid, session=self.session, raise_exception=True)
    elif user_uuid:
        user = User.get_user_by_uuid(user_uuid=user_uuid, session=self.session, raise_exception=True)
    else:
        raise UserNotFound(msg="No user identifier passed")
    # try:
    #     update_user_comm_preferences(user_uuid=str(user.user_uuid), session=self.session, email=user.email)
    # except IterableUserNotFound:
    #     sync_user_to_iterable(user_uuid=str(user.user_uuid), session=self.session)
    #     raise

    sync_user_to_iterable(user_uuid=str(user.user_uuid), session=self.session)


@celery_app.task(bind=True,
                 base=TaskBase,
                 autoretry_for=(IterableOverloadedException, IterableUserNotFound),
                 retry_backoff=True,
                 rate_limit='1/s',
                 name='figure1.backend.sync_iterable_anonymous_user_comm_preferences')
def sync_anonymous_user_comm_preferences_task(self: TaskBase,
                                              email: str,
                                              user_uuid: str,
                                              subscribed_uuids: List[str]):
    """
    Synchronizes user subscriptions with iterable for an anonymous email subscriber
    :return:
    """
    sync_anonymous_user_comm_preferences(email=email,
                                         user_uuid=user_uuid,
                                         subscribed_uuids=subscribed_uuids,
                                         session=self.session)


@celery_app.task(bind=True,
                 base=TaskBase,
                 autoretry_for=(IterableOverloadedException,),
                 retry_backoff=True,
                 name='figure1.backend.update_iterable_sync_device_token_task')
def sync_device_tokens_task(self, user_uid, device_user_tokens):
    """
    Synchronizes user subscriptions with iterable
    :return:
    """

    user = User.get_user_by_uid(user_uid=user_uid, session=self.session, raise_exception=True)
    update_tokens_and_sync(user_uuid=user.user_uuid,
                           device_user_tokens=device_user_tokens,
                           session=self.session,
                           email=user.email)


@celery_app.task(bind=True,
                 base=TaskBase,
                 autoretry_for=(IterableOverloadedException,),
                 retry_backoff=True,
                 name='figure1.backend.sync_user_device_notification_to_iterable_task')
def sync_user_device_notification_to_iterable_task(self, email, device, notification_enabled):
    sync_user_device_notification_to_iterable(email, device, notification_enabled)


@celery_app.task(bind=True,
                 base=TaskBase,
                 autoretry_for=(IterableOverloadedException,),
                 retry_backoff=True,
                 name='figure1.backend.delete_iterable_user')
def delete_iterable_user_task(self, email):
    """
    Deletes a single user from iterable.
    """
    u = User.get_user_by_email(email=email, session=self.session, include_deleted=True)
    update_user_comm_preferences(user_uuid=str(u.user_uuid), session=self.session, email=email)
    try:
        r = set_iterable_user_deleted_flag(email=email, session=self.session)
    except IterableUserNotFound:
        logger.error("User %s not found in iterable", email)
        return
    if r == 'updated':
        self.retry(countdown=30)
    if r is True:
        sync_deleted_users(email=email)


@celery_app.task(bind=True,
                 base=TaskBase,
                 autoretry_for=(IterableOverloadedException,),
                 retry_backoff=True,
                 name='figure1.backend.iterable.sync_deleted_users')
def sync_deleted_users_to_iterable_task(self, chunksize=100, offset=0):
    if self.task_locked is True:
        if self.task_lock_identifier == self.request.id:
            logger.info("Task is locked for this task id")
        else:
            logger.error("Task is locked elsewhere")
            return
    else:
        logger.error("Task is not locked")

    r = sync_deleted_users(limit=chunksize, offset=offset, session=self.session)
    logger.error("Returned %s", r)
    offset = offset + chunksize
    logger.info("Updated offset to %s", offset)

    if offset == r['result_count']:
        logger.info("All users updated")
        return

    if offset + chunksize > r['result_count']:
        logger.info("Modifed chunksize to %s", r['result_count'] - offset)
        self.apply_async(countdown=5, kwargs={'offset': offset, 'chunksize': r['result_count'] - offset})
        return

    logger.info("Deleted %s users out of %s", offset, r['result_count'])
    self.apply_async(countdown=5, kwargs=dict(offset=offset, chunksize=chunksize))


@celery_app.task(bind=True,
                 base=TaskBase,
                 autoretry_for=(IterableOverloadedException, ReadTimeout),
                 retry_backoff=True,
                 name='figure1.backend.bulk_update_iterable_users')
def bulk_update_users(self, chunk_size=1000):
    t: IterableSyncQueue = IterableSyncQueue.get_queue_task(task_id=self.request.id)
    if t is True:
        try:
            bulk_update_user(session=self.session, chunk_size=chunk_size)
        finally:
            IterableSyncQueue.remove_queue_task(task_id=self.request.id)
    else:
        logger.error("Iterable update queue is locked by task %s", t)


@celery_app.task(bind=True,
                 base=TaskBase,
                 autoretry_for=(IterableOverloadedException,),
                 retry_backoff=True,
                 name='figure1.frontend.import_anonymous_email_subscriber_preferences')
def import_anonymous_email_subscriber_preferences_task(self, user_uuid, email):
    for message_type_id in get_iterable_subscribed_message_types(email=email):
        for cs in self.session.query(CommunicationSettings) \
                .filter(CommunicationSettings.communication_iterable_message_type == message_type_id) \
                .all():
            UserCommunicationPreferences.set_user_preference(user_uuid=user_uuid,
                                                             communication_uuid=cs.communication_uuid,
                                                             communication_setting=True,
                                                             session=self.session)


@celery_app.task(bind=True,
                 base=TaskBase,
                 max_retries=5,
                 name='figure1.backend.delete_iterable_users')
def delete_iterable_users(self, emails):
    iterable_client = IterableAPI()
    if iterable_client.iterable_api_disabled:
        logger.error("Iterable api is disabled, nothing to do")
        return None
    undeleted_emails = []
    for email in emails:
        try:
            iterable_client.get_iterable_user_by_email(email=email)
            iterable_client.delete_user(email=email)
        except IterableException:
            undeleted_emails.append(email)
            continue
    if undeleted_emails:
        try:
            self.retry(countdown=5, kwargs=dict(emails=undeleted_emails))
        except MaxRetriesExceededError:
            logger.exception("Max retries exceeded, couldn't delete %s", undeleted_emails)


@celery_app.task(bind=True,
                 base=TaskBase,
                 max_retries=5,
                 name='figure1.backend.sync_iterable_user_unread_notifications_count')
def sync_iterable_user_unread_notifications_count_task(self, notification_uuid: str):
    n = self.session.query(UserNotification).get(notification_uuid)
    if not n.user.user_uid:
        logger.debug("Skipping user notification sync for user without uid: %s", n.user.user_uuid)
        return

    unread_notifications_count = UserNotification \
        .get_unread_notifications_count(user_uuid=n.user.user_uuid, session=self.session)

    IterableAPI().update_user(email=n.user.email, data_fields={"badgeCount": unread_notifications_count})
