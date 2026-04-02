import logging

from sqlalchemy import Column, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

from figure1.core import Base, HasCreateUpdateDeleteTime
from .c_comment_model import Comment
from .user_models import User


class CommentFlag(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "m_comment_flag"
    moderator_uuid = Column(UUID(as_uuid=True), ForeignKey(User.user_uuid), primary_key=True)
    comment_uuid = Column(UUID(as_uuid=True), ForeignKey(Comment.comment_uuid), primary_key=True)

    @staticmethod
    def create(moderator_uuid, comment_uuid, session, skip_commit=False):
        f = session.query(CommentFlag) \
            .filter(CommentFlag.moderator_uuid == moderator_uuid,
                    CommentFlag.comment_uuid == comment_uuid) \
            .one_or_none()
        if f:
            f.deleted_at = None
            return

        f = CommentFlag()
        f.comment_uuid = comment_uuid
        f.moderator_uuid = moderator_uuid
        session.add(f)

        if skip_commit:
            return f
        try:
            session.commit()
        except Exception as e:
            session.rollback()
            logging.error(f"Error saving comment flag {e}")
        return f
