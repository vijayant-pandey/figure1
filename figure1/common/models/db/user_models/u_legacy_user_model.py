import uuid

from sqlalchemy import Column, String, Boolean, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID

from figure1.core import managed_session, Base, HasCreateUpdateDeleteTime
from figure1.common.models.db.reference_data_models import Country
from figure1.common.models.db.r_legacy_specialty_model import LegacySpecialty
from figure1.common.models.db.r_legacy_specialty_profession_model import LegacySpecialtyProfession


class LegacyUser(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "u_legacy_user"

    user_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    legacy_id = Column(String, nullable=True, unique=True, index=True)
    username = Column(String(1024), nullable=False, index=True)
    email = Column(String(1024), nullable=False)
    decrypted_email = Column(Text)
    verified = Column(Boolean, default=False, nullable=False)
    specialty_uuid = Column(UUID(as_uuid=True), ForeignKey(LegacySpecialty.specialty_uuid))
    fe_synchronized = Column(Boolean, default=False)

    @staticmethod
    @managed_session
    def create(legacy_id,
               username,
               email,
               verified,
               specialty_uuid,
               skip_commit=False,
               created_at=None,
               updated_at=None,
               deleted_at=None,
               session=None):
        u = LegacyUser()
        u.user_uuid = uuid.uuid4()
        u.legacy_id = legacy_id
        u.username = username
        u.email = email
        u.verified = verified
        u.specialty_uuid = specialty_uuid
        if created_at:
            u.created_at = created_at
        if updated_at:
            u.updated_at = updated_at
        if deleted_at:
            u.deleted_at = deleted_at

        session.add(u)

        if skip_commit:
            return u

        try:
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        return u

    def as_dict(self):
        return {
            'userUuid': str(self.user_uuid),
            'legacyId': str(self.legacy_id),
            'createdAt': str(self.created_at),
            'username': self.username,
            'email': self.email,
            'decryptedEmail': self.decrypted_email,
            'verified': self.verified,
            'specialtyUuid': str(self.specialty_uuid),
        }

    def elasticsearch_dict(self):
        return {
            'userUuid': str(self.user_uuid),
            'username': self.username,
            'email': self.email,
            'verified': self.verified
        }

    @managed_session
    def profession_dict(self, session=None):
        p = session.query(LegacySpecialtyProfession) \
            .join(LegacySpecialty, LegacySpecialty.profession_uuid == LegacySpecialtyProfession.profession_uuid) \
            .filter(LegacySpecialty.specialty_uuid == self.specialty_uuid) \
            .one_or_none()
        if not p:
            return None

        return {
            'uuid': str(p.profession_uuid),
            'name': p.name,
        }
