import logging

from google.cloud.firestore_v1 import DocumentReference
from pydantic import Field, validator

from figure1.notifications import NotificationDetail
from figure1.common.models.db import UserNotification, User
from figure1.core import FirestoreSyncBase
from figure1.common.types.notification import UserNotificationState
from figure1.core import TaskBase, celery_app

logger = logging.getLogger('figure1.firebase.user_notification')


@celery_app.task(bind=True,
                 base=TaskBase,
                 name='figure1.frontend.sync_firestore_user_notifications')
def sync_user_notifications_task(self, user_uuid):
    sync_user_notifications(user_uuid=user_uuid, session=self.session)


def sync_user_notifications(user_uuid, session):
    u = User.get_user_by_uuid(user_uuid=user_uuid, session=session, raise_exception=True)
    if not u.user_uid:
        logger.debug("Skipping user notification sync for user without uid: %s", user_uuid)
        return
    FirestoreUserNotificationMetadata(user_uid=u.user_uid, user_uuid=u.user_uuid) \
        .firestore_write(session=session)
    FirestoreUserNotificationMetadataOld(user_uid=u.user_uid, user_uuid=u.user_uuid) \
        .firestore_write(session=session)
    for n in session.query(UserNotification).filter(UserNotification.user_uuid == user_uuid).all():
        FirestoreUserNotification(user_uid=u.user_uid, notification_uuid=n.notification_uuid) \
            .firestore_write(session=session)
        FirestoreUserNotificationOld(user_uid=u.user_uid, notification_uuid=n.notification_uuid) \
            .firestore_write(session=session)


@celery_app.task(bind=True,
                 base=TaskBase,
                 name='figure1.frontend.sync_single_user_notification')
def sync_single_user_notification_task(self, notification_uuid):
    sync_single_user_notification(notification_uuid=notification_uuid, session=self.session)


def sync_single_user_notification(notification_uuid, session):
    n = session.query(UserNotification).get(notification_uuid)
    if not n.user.user_uid:
        logger.debug("Skipping user notification sync for user without uid: %s", n.user.user_uuid)
        return
    FirestoreUserNotificationMetadata(user_uid=n.user.user_uid, user_uuid=n.user.user_uuid) \
        .firestore_write(session=session)
    FirestoreUserNotificationMetadataOld(user_uid=n.user.user_uid, user_uuid=n.user.user_uuid) \
        .firestore_write(session=session)
    FirestoreUserNotification(user_uid=n.user.user_uid, notification_uuid=n.notification_uuid) \
        .firestore_write(session=session)
    FirestoreUserNotificationOld(user_uid=n.user.user_uid, notification_uuid=n.notification_uuid) \
        .firestore_write(session=session)


class FirestoreUserNotification(FirestoreSyncBase):
    """
    Handles syncing a user notification to firestore
    """
    notificationUuid: str = Field(alias='notification_uuid')
    userUid: str = Field(alias='user_uid')

    @validator('notificationUuid', pre=True)
    def stringify_uuid(cls, value):
        return str(value)

    @property
    def firestore_doc_reference(self):
        return self.fs_client \
            .collection('userNotificationDB') \
            .document(self.userUid) \
            .collection('notifications') \
            .document(self.notificationUuid)

    def generate_firestore_document(self, session=None) -> dict:
        return NotificationDetail.get_notification_detail(notification_uuid=self.notificationUuid,
                                                          firebase_db=self.fs_client,
                                                          session=session)

    def firestore_reset(self):
        self.firestore_doc_reference.delete()


class FirestoreUserNotificationOld(FirestoreUserNotification):
    """
    Handles syncing a user notification to the old location in firestore.
    Can be removed when clients have been updated.
    """

    @property
    def firestore_doc_reference(self):
        return self.fs_client \
            .collection('userActivityRecordDB') \
            .document(self.userUid) \
            .collection('all') \
            .document(self.notificationUuid)


class FirestoreUserNotificationMetadata(FirestoreSyncBase):
    """
    Handles syncing user notification metadata to firestore
    """
    userUid: str = Field(alias='user_uid')
    userUuid: str = Field(alias='user_uuid')

    @validator('userUuid', pre=True)
    def stringify_uuid(cls, value):
        return str(value)

    def generate_firestore_document(self, session=None) -> dict:
        counts = UserNotification.get_counts(user_uuid=self.userUuid, session=session)
        fs_doc = self.dict()
        fs_doc.update({
            'allCount': counts.get('all'),
            'newCount': counts.get(UserNotificationState.NEW) or 0,
            # deprecated
            'newActivityCount': counts.get(UserNotificationState.NEW) or 0
        })
        return fs_doc

    @property
    def firestore_doc_reference(self) -> DocumentReference:
        return self.fs_client \
            .collection('userNotificationDB') \
            .document(self.userUid)

    def firestore_reset(self, **kwargs):
        self.firestore_doc_reference.delete()


class FirestoreUserNotificationMetadataOld(FirestoreUserNotificationMetadata):
    """
    Handles syncing user notification metadata to the old location in firestore.
    Can be removed when clients have been updated.
    """

    def generate_firestore_document(self, session=None) -> dict:
        counts = UserNotification.get_counts(user_uuid=self.userUuid, session=session)
        data = self.dict()
        data.update({
            'allCount': counts.get('all'),
            'newNotificationCount': counts.get(UserNotificationState.NEW) or 0,
            # deprecated
            'newActivityCount': counts.get(UserNotificationState.NEW) or 0
        })
        return data

    @property
    def firestore_doc_reference(self) -> DocumentReference:
        return self.fs_client \
            .collection('userActivityRecordDB') \
            .document(self.userUid)
