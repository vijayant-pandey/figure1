import uuid

from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

from figure1.core import Base, HasCreateUpdateDeleteTime, managed_session
from .r_legacy_specialty_profession_model import LegacySpecialtyProfession
from .r_legacy_specialty_type_model import LegacySpecialtyType


class LegacySpecialty(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "r_legacy_specialty"

    specialty_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    type_uuid = Column(UUID(as_uuid=True), ForeignKey(LegacySpecialtyType.type_uuid), nullable=False)
    profession_uuid = Column(UUID(as_uuid=True), ForeignKey(LegacySpecialtyProfession.profession_uuid), nullable=False)
    label = Column(String(1024), default="", nullable=False)
    singular_label = Column(String(1024), nullable=True)
    plural_label = Column(String(1024), nullable=True)
    indefinite_article = Column(String(32), nullable=True)
    pro_tree_uuid = Column(UUID(as_uuid=True))

    @staticmethod
    @managed_session
    def create_if_missing(type_uuid, profession_uuid, label, singular_label, plural_label, indefinite_article,
                          skip_commit=False, session=None):
        existing_item = session.query(LegacySpecialty) \
            .filter(LegacySpecialty.type_uuid == type_uuid,
                    LegacySpecialty.profession_uuid == profession_uuid) \
            .one_or_none()
        if existing_item:
            return existing_item

        s = LegacySpecialty()
        s.specialty_uuid = uuid.uuid4()
        s.type_uuid = type_uuid
        s.profession_uuid = profession_uuid
        s.label = label
        s.singular_label = singular_label
        s.plural_label = plural_label
        s.indefinite_article = indefinite_article

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
            'typeUuid': str(self.type_uuid),
            'professionUuid': str(self.profession_uuid),
            'label': self.label,
            'singularLabel': self.singular_label,
            'pluralLabel': self.plural_label,
            'indefiniteArticle': self.indefinite_article,
        }

    def elasticsearch_dict(self):
        return {
            'typeUuid': str(self.type_uuid),
            'label': self.label
        }
