import uuid

from sqlalchemy import Column, String, Integer, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

from figure1.core import managed_session, Base, HasCreateTime
from .user_models import LegacyUser


class LegacyComment(Base, HasCreateTime):
    __tablename__ = "c_legacy_comment"

    comment_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    legacy_id = Column(String, default="", nullable=True, index=True)
    user_id = Column(String, nullable=True)
    user_uuid = Column(UUID(as_uuid=True), ForeignKey(LegacyUser.user_uuid))
    case_uuid = Column(UUID(as_uuid=True), index=True)
    case_legacy_id = Column(String, default="", nullable=True)
    text = Column(String(10000))
    language = Column(String(8))
    likes = Column(Integer, default=0)
    parent_id = Column(String, default="", nullable=True)
    deleted = Column(Boolean, default=False, nullable=False)
    edited = Column(Boolean, default=False, nullable=False)
    accepted_answer = Column(Boolean, default=False, nullable=False)

    @staticmethod
    @managed_session
    def create(legacy_id, user_legacy_id, case_uuid, case_legacy_id, text, language, likes, parent_id, deleted, edited,
               accepted_answer, session):
        user = session.query(LegacyUser).filter(LegacyUser.legacy_id == user_legacy_id).one()
        c = LegacyComment()
        c.comment_uuid = uuid.uuid4()
        c.legacy_id = legacy_id
        c.user_id = user.legacy_id
        c.user_uuid = user.user_uuid
        c.case_uuid = case_uuid
        c.case_legacy_id = case_legacy_id
        c.text = text
        c.language = language
        c.likes = likes
        c.parent_id = parent_id
        c.deleted = deleted
        c.edited = edited
        c.accepted_answer = accepted_answer

        session.add(c)
        return c

    def as_dict(self):
        return {
            'commentUuid': str(self.comment_uuid),
            'uuid': str(self.comment_uuid),
            'legacyId': self.legacy_id,
            'authorUuid': str(self.user_uuid),
            'caseUuid': str(self.case_uuid),
            'caseLegacyId': self.case_legacy_id,
            'text': self.text,
            'language': self.language,
            'likes': self.likes,
            'parentId': self.parent_id,
            'deleted': self.deleted,
            'edited': self.edited,
            'acceptedAnswer': self.accepted_answer,
        }

    def elasticsearch_dict(self):
        return {
            'commentUuid': str(self.comment_uuid),
            'userUuid': str(self.user_uuid),
            'caseUuid': str(self.case_uuid),
            'text': self.text,
            'language': self.language,
            'likes': self.likes,
            'parentId': self.parent_id,
            'acceptedAnswer': self.accepted_answer,
        }
