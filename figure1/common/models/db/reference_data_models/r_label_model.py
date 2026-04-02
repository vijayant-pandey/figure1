import uuid

from sqlalchemy import Column, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID

from figure1.core import Base, HasCreateUpdateDeleteTime


class Label(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "r_label"
    label_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    name = Column(Text, nullable=False)
    kind = Column(Text, nullable=False, index=True, unique=True)
    is_public = Column(Boolean, nullable=False, index=True)

    @staticmethod
    def create_or_update(name, kind, is_public, session, skip_commit=False):
        label = session.query(Label) \
            .filter(Label.kind == kind) \
            .one_or_none()
        if not label:
            label = Label()
            label.label_uuid = uuid.uuid4()
            label.kind = kind
        label.name = name
        label.is_public = is_public

        session.add(label)

        if skip_commit:
            return label
        try:
            session.commit()
        except Exception as e:
            session.rollback()
            raise e

        return label

    def as_dict(self):
        return {
            'labelUuid': str(self.label_uuid),
            'name': self.name,
            'kind': self.kind,
            'isPublic': self.is_public,
        }

    @staticmethod
    def get_resolved(session):
        return session.query(Label) \
            .filter(Label.kind == 'resolved') \
            .one_or_none()

    @staticmethod
    def get_unresolved(session):
        return session.query(Label) \
            .filter(Label.kind == 'unresolved') \
            .one_or_none()
