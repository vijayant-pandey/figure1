from sqlalchemy import Column, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from figure1.core import Base, HasCreateUpdateDeleteTime, managed_session
from .user_models import User
from .r_verification_tag import VerificationTag


class UserVerificationTag(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "m_user_verification_tag"

    user_uuid = Column(UUID(as_uuid=True), ForeignKey(User.user_uuid), primary_key=True)
    tag_uuid = Column(UUID(as_uuid=True), ForeignKey(VerificationTag.tag_uuid), primary_key=True)
    moderator_uuid = Column(UUID(as_uuid=True), ForeignKey(User.user_uuid))

    tag = relationship("VerificationTag", uselist=False)

    @staticmethod
    def _generate_user_verification_instance(user_uuid, tag_uuid, moderator_uuid=None) -> 'UserVerificationTag':
        uvt = UserVerificationTag()
        uvt.user_uuid = user_uuid
        uvt.tag_uuid = tag_uuid
        uvt.deleted_at = None
        if moderator_uuid is not None:
            uvt.moderator_uuid = moderator_uuid
        return uvt

    @staticmethod
    def create(user_uuid, tag_uuid, moderator_uuid) -> 'UserVerificationTag':
        return UserVerificationTag._generate_user_verification_instance(user_uuid, tag_uuid, moderator_uuid)

    @staticmethod
    def delete(user_uuid, tag_uuid) -> 'UserVerificationTag':
        uvt = UserVerificationTag._generate_user_verification_instance(user_uuid, tag_uuid)
        uvt.mark_deleted()
        return uvt

    def as_dict(self):
        return {
            'userUuid': str(self.user_uuid),
            'tagUuid': str(self.tag_uuid),
            'moderatorUuid': str(self.moderator_uuid),
        }

    def as_firestore_dict(self):
        return {
            'userUuid': str(self.user_uuid),
            'tagUuid': str(self.tag_uuid),
            'moderatorUuid': str(self.moderator_uuid),
            'tagName': self.tag.name,
        }
