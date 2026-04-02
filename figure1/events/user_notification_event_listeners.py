import logging

from sqlalchemy import event
from sqlalchemy.orm import object_session

from figure1.common.iterable.iterable_tasks import sync_iterable_user_unread_notifications_count_task
from figure1.common.models.db import UserNotification
from figure1.common.models.firebase import sync_single_user_notification_task

logger = logging.getLogger(__name__)


def _add_sync_task(session, notification_uuid, if_update_notifications_count=False):
    task = sync_single_user_notification_task.si(notification_uuid=str(notification_uuid))
    if if_update_notifications_count:
        task.link(sync_iterable_user_unread_notifications_count_task.si(notification_uuid=str(notification_uuid)))

    if isinstance(session.info.get('tasks'), list):
        if task not in session.info['tasks']:
            session.info['tasks'].append(task)
    else:
        session.info['tasks'] = [task]


@event.listens_for(UserNotification.state, 'set', active_history=True, raw=True)
def handle_user_notification_state_change(target, value, old, initiator):
    if target.transient or not target.session:
        logger.debug("Target is transient, will be handled by after_insert")
        return

    if value == old:
        logger.debug("State was not modified, do nothing")
        return

    logger.debug("UserNotification %s state changed to %s, adding sync task", target.object.notification_uuid, value)
    _add_sync_task(target.session, target.object.notification_uuid, if_update_notifications_count=True)


@event.listens_for(UserNotification, 'after_insert')
def handle_user_notification_insert(mapper, connection, target):
    session = object_session(target)
    logger.debug("UserNotification %s inserted, adding sync task", target.notification_uuid)
    _add_sync_task(session, target.notification_uuid)
