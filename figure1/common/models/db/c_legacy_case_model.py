"""
Defines the Data Model for Case, CaseComments and CaseRaw
"""
import enum
import uuid

from sqlalchemy import Column, Integer, String, Index, Enum, ForeignKey, ARRAY, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID

from figure1.core import Base, HasCreateUpdateTime
from .c_legacy_comment_model import LegacyComment
from .c_media_model import Media, MediaType
from .user_models import LegacyUser


class TaggingState(enum.Enum):
    EXCLUDED = -3,
    RETRY = -2
    FAILED = -1
    WAITING = 0
    PROCESSING = 1
    PENDING_ASSIGNMENT = 2
    ASSIGNED = 3
    PENDING_APPROVAL = 4
    APPROVED = 5
    MIGRATED = 6

    @staticmethod
    def is_valid(case_state):
        return case_state in [state.name for state in TaggingState]


class LegacyCase(Base, HasCreateUpdateTime):
    __tablename__ = "c_legacy_case"

    case_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    legacy_id = Column(String, default="<EMPTY>", nullable=False)
    caption = Column(String(10000))
    author_id = Column(String(1024))
    user_uuid = Column(UUID(as_uuid=True), ForeignKey(LegacyUser.user_uuid))
    title = Column(String(1024), default="")
    likes = Column(Integer, default=0, nullable=False)
    follows = Column(Integer, default=0, nullable=False)
    specialty = Column(String(1024))
    language = Column(String(8))
    state = Column(Enum(TaggingState), nullable=False)
    tagged_specialty_uuids = Column(ARRAY(UUID(as_uuid=True)))
    external_link = Column(Text)
    external_link_text = Column(Text)
    is_grand_rounds = Column(Boolean)
    is_image_series = Column(Boolean)
    is_cm_cme = Column(Boolean)
    is_quiz = Column(Boolean)
    __table_args__ = (Index('idx_case_legacy_unique', 'author_id', 'legacy_id', unique=True),)

    def as_dict(self):
        return {
            'caseUuid': str(self.case_uuid),
            'uuid': str(self.case_uuid),
            'legacyId': str(self.legacy_id),
            'state': self.state.name.lower(),
            'caption': self.caption,
            'userUuid': str(self.user_uuid),
            'title': self.title,
            'likes': self.likes,
            'follows': self.follows,
            'specialty': self.specialty,
            'taggedSpecialtyUuids':
                list(map(lambda s: str(s), self.tagged_specialty_uuids)) if self.tagged_specialty_uuids else [],
            'createdAt': self.created_at,
        }

    def elasticsearch_dict(self):
        return {
            'caseUuid': str(self.case_uuid),
            'legacyId': str(self.legacy_id),
            'caption': self.caption,
            'userUuid': str(self.user_uuid),
            'title': self.title,
            'likes': self.likes,
            'follows': self.follows,
            'caseState': self.state.name.lower(),
            'taggingState': self.state.name.lower()
        }

    def comment_count(self, session=None):
        return session.query(LegacyComment) \
            .filter(LegacyComment.case_uuid == self.case_uuid) \
            .count()

    def media_dict(self, session=None):
        media = []
        for m in session.query(Media) \
                .filter(Media.type == MediaType.IMAGE) \
                .filter(Media.case_uuid == self.case_uuid) \
                .order_by(Media.display_order.asc()) \
                .all():
            m_dict = m.as_dict()
            media.append({
                'type': m_dict.get('type'),
                'url': m_dict.get('url'),
                'display_order': m_dict.get('displayOrder'),
                'width': m_dict.get('width'),
                'height': m_dict.get('height'),
            })
        return media if media else None
