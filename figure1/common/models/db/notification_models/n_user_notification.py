import uuid
from datetime import datetime
from datetime import timezone
from sqlalchemy import Column, Enum, ForeignKey, func, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from figure1.common.models.db import Groups
from figure1.common.types import UserNotificationType, UserNotificationState
from figure1.common.utils.date_utils import utc_now
from figure1.common.models.db.c_case_model import Case
from figure1.common.models.db.c_comment_model import Comment
from figure1.common.models.db.user_models import User
from figure1.exceptions import NotificationNotFound
from figure1.core import Base, HasCreateUpdateTime


class UserNotification(Base, HasCreateUpdateTime):
    """
    UserNotification tracks activity notifications shown to the user in the activity notification center.

     notification_uuid:  the PK identifier for the notification
     user_uuid:  the user uuid who this notification belongs to
     source_uuid:  the user uuid who prompted the notification.  For example for a comment notification, this is the
         uuid of the user who created the comment
     case_uuid:  the case uuid that the notification relates to
     comment_uuid:  the comment uuid that the notification relates to.  None if not applicable for the notification type
     state:  the viewed status of the notification.  Initially 'new', once viewed becomes 'acknowledged'
     notification_type:  the type of action the notification is about
     short_message:  a user displayable message describing the notification
     long_message:  a more verbose user displayable message describing the notification
    """
    __tablename__ = "n_user_notification"

    notification_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    user_uuid = Column(UUID(as_uuid=True), ForeignKey(User.user_uuid), index=True)
    source_uuid = Column(UUID(as_uuid=True), ForeignKey(User.user_uuid), nullable=True)
    case_uuid = Column(UUID(as_uuid=True), ForeignKey(Case.case_uuid), index=True)
    comment_uuid = Column(UUID(as_uuid=True), ForeignKey(Comment.comment_uuid), nullable=True)
    group_uuid = Column(UUID(as_uuid=True), ForeignKey(Groups.group_uuid, ondelete='CASCADE'), nullable=True)
    state = Column(Enum(UserNotificationState), default=UserNotificationState.NEW, nullable=False)
    notification_type = Column(Enum(UserNotificationType), nullable=False)

    user = relationship('User', uselist=False, foreign_keys=user_uuid)

    @staticmethod
    def create(user_uuid,
               notification_type,
               session,
               case_uuid=None,
               comment_uuid=None,
               source_uuid=None,
               group_uuid=None,
               state=UserNotificationState.NEW):
        n = UserNotification()
        n.notification_uuid = uuid.uuid4()
        n.user_uuid = user_uuid
        n.source_uuid = source_uuid
        n.case_uuid = case_uuid
        n.comment_uuid = comment_uuid
        n.group_uuid = group_uuid
        n.state = state
        n.notification_type = notification_type
        session.add(n)

        return n

    @staticmethod
    def acknowledge_all_new(user_uuid, session):
        for record in session.query(UserNotification) \
                .filter(UserNotification.user_uuid == user_uuid,
                        UserNotification.state == UserNotificationState.NEW) \
                .all():
            record.state = UserNotificationState.ACKNOWLEDGED
            session.add(record)
        session.flush()

    @staticmethod
    def read_all(user_uuid, session):
        for record in session.query(UserNotification) \
                .filter(UserNotification.user_uuid == user_uuid,
                        UserNotification.state is not UserNotificationState.READ).all():
            record.state = UserNotificationState.READ
            session.add(record)
        session.flush()

    @staticmethod
    def read_notification(notification_uuid, session):
        notification = UserNotification.get_notification_by_uuid(notification_uuid, session)
        notification.state = UserNotificationState.READ

        session.add(notification)

    @staticmethod
    def get_counts(user_uuid, session):
        counts = {'all': 0}
        for r in session.query(UserNotification.state, func.count(UserNotification.state)) \
                .filter(UserNotification.user_uuid == user_uuid) \
                .group_by(UserNotification.state) \
                .all():
            counts[r[0]] = r[1]
            counts['all'] += r[1]
        return counts

    @staticmethod
    def get_notification_by_uuid(notification_uuid, session):
        un = session.query(UserNotification).get(notification_uuid)
        if not un:
            raise NotificationNotFound(notification_uuid=notification_uuid)
        return un

    @staticmethod
    def get_unread_notifications_count(user_uuid, session):
        return session.query(UserNotification).filter(UserNotification.user_uuid == user_uuid,
                                                      UserNotification.state != UserNotificationState.READ).count()


class ActivityReminder(Base, HasCreateUpdateTime):
    """
    ActivityReminder tracks when notification reminders have been sent to users
     user_uuid:  the PK identifier for the ActivityReminder
     last_sent: last time a user received a reminder
    """
    __tablename__ = "n_user_activity_reminder"
    last_sent = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    user_uuid = Column(UUID(as_uuid=True), ForeignKey(User.user_uuid), primary_key=True)

    @staticmethod
    def update_last_sent(session, user_uuid):
        a = ActivityReminder()
        a.user_uuid = user_uuid
        a.last_sent = utc_now(timezone=timezone.utc)
        session.merge(a)
