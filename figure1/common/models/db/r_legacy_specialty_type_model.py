import uuid

from sqlalchemy import Column, String
from sqlalchemy.dialects.postgresql import UUID

from figure1.core import Base, HasCreateUpdateDeleteTime, managed_session


class LegacySpecialtyType(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "r_legacy_specialty_type"

    type_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    name = Column(String(1024), default="", nullable=False)

    @staticmethod
    @managed_session
    def create_if_missing(name, session=None):
        existing_item = session.query(LegacySpecialtyType).filter(LegacySpecialtyType.name == name).one_or_none()
        if existing_item:
            return existing_item

        t = LegacySpecialtyType()
        t.type_uuid = uuid.uuid4()
        t.name = name

        session.add(t)
        return t

    def as_dict(self):
        return {
            'typeUuid': str(self.type_uuid),
            'name': self.name,
        }
