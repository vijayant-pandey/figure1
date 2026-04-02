import uuid

from sqlalchemy import Column, String
from sqlalchemy.dialects.postgresql import UUID

from figure1.core import Base, HasCreateUpdateDeleteTime, managed_session


class LegacySpecialtyProfession(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "r_legacy_specialty_profession"

    profession_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    name = Column(String(1024), default="", nullable=False)

    @staticmethod
    @managed_session
    def create_if_missing(name, session=None):
        existing_item = session.query(LegacySpecialtyProfession).filter(
            LegacySpecialtyProfession.name == name).one_or_none()
        if existing_item:
            return existing_item

        p = LegacySpecialtyProfession()
        p.profession_uuid = uuid.uuid4()
        p.name = name

        session.add(p)
        return p

    def as_dict(self):
        return {
            'professionUuid': str(self.profession_uuid),
            'name': self.name,
        }
