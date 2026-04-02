from figure1.common.models.db import UserNotification, User
from figure1.common.models.firebase import sync_user_notifications_task
from figure1.core import managed_session


@managed_session
def sync_user_notifications(user_uuid=None, session=None):
    if not user_uuid:
        q = session.query(UserNotification.user_uuid) \
                .join(User, User.user_uuid == UserNotification.user_uuid) \
                .filter(User.deleted_at.is_(None), User.user_uid.isnot(None)) \
                .distinct()
        users = list([str(x[0]) for x in q.all()])
        sync_user_notifications_task.map(users).apply_async()
    else:
        sync_user_notifications_task.delay(user_uuid=user_uuid)
