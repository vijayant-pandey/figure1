"""
Mention model for tracking @mentions in comments and content.
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from figure1.core.db.sqlalchemy_declarative_base import Base
from figure1.core.db.database_engine import mapper_args


class Mention(Base):
    """
    Represents a user mention (@username) in comments or case descriptions.

    When a user mentions another user with @username, a record is created here.
    This enables notifications and mention tracking.
    """
    __tablename__ = 'c_mention'
    __mapper_args__ = mapper_args

    # Primary key
    mention_uuid = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False
    )

    # User being mentioned
    mentioned_user_uuid = Column(
        UUID(as_uuid=True),
        ForeignKey('u_user.user_uuid', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # User who created the mention
    mentioning_user_uuid = Column(
        UUID(as_uuid=True),
        ForeignKey('u_user.user_uuid', ondelete='CASCADE'),
        nullable=False,
        index=True
    )

    # Where the mention occurred
    comment_uuid = Column(
        UUID(as_uuid=True),
        ForeignKey('c_comment.comment_uuid', ondelete='CASCADE'),
        nullable=True,
        index=True
    )

    content_uuid = Column(
        UUID(as_uuid=True),
        ForeignKey('c_content.content_uuid', ondelete='CASCADE'),
        nullable=True,
        index=True
    )

    case_uuid = Column(
        UUID(as_uuid=True),
        ForeignKey('c_case.case_uuid', ondelete='SET NULL'),
        nullable=True,
        index=True
    )

    # Position of mention in the text
    position = Column(Integer, nullable=False)

    # Read status
    is_read = Column(Boolean, default=False, nullable=False, index=True)
    read_at = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=True, onupdate=datetime.utcnow)

    # Relationships
    mentioned_user = relationship(
        "User",
        foreign_keys=[mentioned_user_uuid],
        backref="mentions_received"
    )

    mentioning_user = relationship(
        "User",
        foreign_keys=[mentioning_user_uuid],
        backref="mentions_created"
    )

    comment = relationship(
        "Comment",
        foreign_keys=[comment_uuid],
        backref="mentions"
    )

    # Composite indexes for common queries
    __table_args__ = (
        Index(
            'ix_c_mention_mentioned_user_unread',
            'mentioned_user_uuid',
            'is_read',
            postgresql_where=(Column('is_read') == False)
        ),
        Index(
            'ix_c_mention_mentioned_user_created',
            'mentioned_user_uuid',
            'created_at'
        ),
    )

    def __repr__(self):
        return f"<Mention {self.mention_uuid}: @{self.mentioned_user_uuid} by {self.mentioning_user_uuid}>"
