import uuid

from sqlalchemy import Column, Text
from sqlalchemy.dialects.postgresql import UUID

from figure1.core import Base, HasCreateUpdateDeleteTime


class VerificationTag(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "r_verification_tag"
    tag_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    name = Column(Text, nullable=False, unique=True)

    @staticmethod
    def create(name, session, skip_commit=False):
        t = session.query(VerificationTag) \
            .filter(VerificationTag.name == name) \
            .one_or_none()
        if t:
            t.deleted_at = None
        else:
            t = VerificationTag()
            t.tag_uuid = uuid.uuid4()
            t.name = name
            session.add(t)

        if skip_commit:
            return t
        try:
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        return t

    @staticmethod
    def update(tag_uuid, name, session, skip_commit=False):
        t = session.query(VerificationTag) \
            .filter(VerificationTag.tag_uuid == tag_uuid) \
            .one_or_none()
        if not t:
            return

        t.name = name

        if skip_commit:
            return t
        try:
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        return t

    @staticmethod
    def delete(tag_uuid, session, skip_commit=False):
        t = session.query(VerificationTag) \
            .filter(VerificationTag.tag_uuid == tag_uuid) \
            .one_or_none()
        if not t:
            return None

        t.mark_deleted()

        if skip_commit:
            return t
        try:
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        return t

    def as_dict(self):
        return {
            'tagUuid': str(self.tag_uuid),
            'name': self.name,
        }
