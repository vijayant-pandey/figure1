import uuid

from sqlalchemy import Column, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID

from figure1.core import Base, HasCreateUpdateDeleteTime
from .user_models import User


class VerificationNote(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "m_verification_note"

    note_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    user_uuid = Column(UUID(as_uuid=True), ForeignKey(User.user_uuid), index=True)
    moderator_uuid = Column(UUID(as_uuid=True), ForeignKey(User.user_uuid))
    text = Column(Text, nullable=True)

    @staticmethod
    def create(user_uuid, moderator_uuid, text, session, skip_commit=False):
        n = VerificationNote()
        n.note_uuid = uuid.uuid4()
        n.user_uuid = user_uuid
        n.moderator_uuid = moderator_uuid
        n.text = text

        session.add(n)

        if skip_commit:
            return n

        try:
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        return n

    def as_dict(self):
        return {
            'noteUuid': str(self.note_uuid),
            'userUuid': str(self.user_uuid),
            'moderatorUuid': str(self.moderator_uuid),
            'text': self.text,
        }

    def as_firestore_dict(self, session):
        moderator = session.query(User).filter(User.user_uuid == self.moderator_uuid).one_or_none()
        if not moderator:
            return None

        return {
            'createdAt': self.created_at,
            'noteUuid': str(self.note_uuid),
            'moderatorUuid': str(self.moderator_uuid),
            'moderatorUid': moderator.user_uid,
            'moderatorUsername': moderator.username,
            'moderatorName': moderator.first_name,
            'text': self.text
        }
