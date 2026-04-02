from sqlalchemy import Column, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from figure1.core import Base, HasCreateUpdateDeleteTime
from .u_user_model import User


class UserFollow(Base, HasCreateUpdateDeleteTime):
    """
    One row for each follow event.
    1. User follows user
        - user_uuid is the source event, the user who clicked follow
        - user_follows_user is the uuid of the user who is followed
    2. Find all followers for a user
        - Select all matching uuids matching a user from user_follows_user
    3. Find all users a given user is following
        - Select all matching uuids from user_uuid matching the given user

    """
    __tablename__ = "u_user_follow"
    user_uuid = Column(UUID(as_uuid=True), ForeignKey(User.user_uuid), primary_key=True)
    follower_uuid = Column(UUID(as_uuid=True), ForeignKey(User.user_uuid), primary_key=True)
    __table_args__ = (
        Index('ix_u_user_follow_follower', "user_uuid", "follower_uuid", unique=True),
    )

    @staticmethod
    def get_user_followers(session, user_uuid):
        user_followers = []
        for u in session.query(UserFollow).filter(UserFollow.user_uuid == user_uuid).all():
            if u.is_deleted:
                continue
            user_followers.append(str(u.follower_uuid))
        return user_followers

    @staticmethod
    def get_user_following(session, user_uuid):
        user_following = []
        for u in session.query(UserFollow) \
                .filter(UserFollow.follower_uuid == user_uuid).all():
            if u.is_deleted:
                continue
            user_following.append(str(u.user_uuid))
        return user_following

    @staticmethod
    def follow_user(session, user_uuid, follower_user_uuid):
        u = UserFollow()
        u.user_uuid = user_uuid
        u.follower_uuid = follower_user_uuid
        u.deleted_at = None
        return session.merge(u)

    @staticmethod
    def unfollow_user(session, user_uuid, follower_user_uuid):
        u = UserFollow()
        u.user_uuid = user_uuid
        u.follower_uuid = follower_user_uuid
        u.mark_deleted()
        return session.merge(u)
