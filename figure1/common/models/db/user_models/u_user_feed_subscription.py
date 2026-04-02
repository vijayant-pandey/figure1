import uuid

from sqlalchemy import Column, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

from figure1.core import Base, HasCreateUpdateDeleteTime, managed_session
from figure1.common.models.db.f_feed_type_model import FeedType
from .u_user_model import User


class UserFeedSubscription(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "u_user_feed_subscription"
    user_feed_subscription_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    user_uuid = Column(UUID(as_uuid=True), ForeignKey(User.user_uuid), index=True)
    feed_type_uuid = Column(UUID(as_uuid=True), ForeignKey(FeedType.feed_type_uuid), index=True)

    @staticmethod
    def create(user_uuid, feed_type_uuid, session=None):
        ut = session.query(UserFeedSubscription) \
            .filter(UserFeedSubscription.user_uuid == user_uuid,
                    UserFeedSubscription.feed_type_uuid == feed_type_uuid) \
            .one_or_none()
        if ut:
            ut.deleted_at = None
            return ut

        ut = UserFeedSubscription()
        ut.user_feed_subscription_uuid = uuid.uuid4()
        ut.user_uuid = user_uuid
        ut.feed_type_uuid = feed_type_uuid
        session.add(ut)
        return ut

    def as_dict(self):
        return {
            'userFeedSubscriptionUuid': str(self.user_feed_subscription_uuid),
            'userUuid': str(self.user_uuid),
            'feedTypeUuid': str(self.feed_type_uuid),
        }

    @staticmethod
    def get_subscription(user_uuid, feed_type_uuid, session=None):
        return session.query(UserFeedSubscription) \
            .filter(UserFeedSubscription.user_uuid == user_uuid,
                    UserFeedSubscription.feed_type_uuid == feed_type_uuid,
                    UserFeedSubscription.deleted_at.is_(None)) \
            .one_or_none()

    @staticmethod
    def get_subscribed_feeds(user_uuid, session=None):
        mfy_uuid = FeedType.get_made_for_you_uuid(session=session)
        for feed in session.query(UserFeedSubscription) \
                .filter(UserFeedSubscription.user_uuid == user_uuid,
                        UserFeedSubscription.deleted_at.is_(None),
                        UserFeedSubscription.feed_type_uuid != mfy_uuid) \
                .all():
            yield feed.as_dict()
