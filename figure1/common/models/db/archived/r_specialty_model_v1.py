import uuid

from sqlalchemy import Column, String, Boolean, Integer

from sqlalchemy.dialects.postgresql import UUID
from figure1.core import Base, managed_session, HasCreateUpdateDeleteTime


class Specialty(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "r_specialty"

    specialty_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    name = Column(String(1024), default="", nullable=False, index=True)
    label = Column(String(1024), default="", nullable=False)
    depth = Column(Integer, default=0, nullable=False)
    master = Column(Boolean, default=False, nullable=False)

    @staticmethod
    @managed_session
    def create_or_update(name, label, depth, skip_commit=False, session=None):
        existing_item = session.query(Specialty) \
            .filter(Specialty.label == label,
                    Specialty.depth == depth) \
            .one_or_none()
        if existing_item:
            if existing_item.name != name:
                existing_item.name = name
            return existing_item

        s = Specialty()
        s.specialty_uuid = uuid.uuid4()
        s.name = name
        s.label = label
        s.depth = depth

        session.add(s)

        if skip_commit:
            return s

        try:
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        return s

    def as_dict(self):
        return {
            'specialtyUuid': str(self.specialty_uuid),
            'name': self.name,
            'label': self.label,
            'depth': self.depth,
        }
