import uuid

from sqlalchemy import Column, Text, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID

from figure1.core import Base, HasCreateUpdateDeleteTime
from .user_models import User
from figure1.common.types import SupportedDeviceTypes


class UserDeviceNotificationToken(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "n_user_device_notification_token"

    user_uuid = Column(UUID(as_uuid=True), ForeignKey(User.user_uuid), primary_key=True, index=True)
    device_id = Column(Text, primary_key=True, index=True)
    device_type = Column(Enum(SupportedDeviceTypes), nullable=False, index=True)
    fcm_token = Column(Text, nullable=False)

    @staticmethod
    def create_or_update(user_uuid,
                         device_id,
                         device_type,
                         fcm_token,
                         session):
        existing_token = session.query(UserDeviceNotificationToken) \
            .filter(UserDeviceNotificationToken.fcm_token == fcm_token,
                    UserDeviceNotificationToken.user_uuid == user_uuid,
                    UserDeviceNotificationToken.deleted_at.is_(None)) \
            .one_or_none()

        if existing_token:
            if existing_token.device_id != device_id:
                existing_token.device_id = device_id
            if existing_token.device_type != device_type.upper():
                existing_token.device_type = device_type.upper()

            return existing_token

        dnt = UserDeviceNotificationToken()
        dnt.user_uuid = user_uuid
        dnt.device_id = device_id
        dnt.fcm_token = fcm_token
        dnt.device_type = device_type.upper()
        return session.merge(dnt)

    @staticmethod
    def list_all(user_uuid, session):
        return session.query(UserDeviceNotificationToken) \
            .filter(UserDeviceNotificationToken.user_uuid == user_uuid,
                    UserDeviceNotificationToken.deleted_at.is_(None)) \
            .all()

    def as_dict(self):
        return {
            'deviceId': self.device_id,
            'deviceType': self.device_type.name.lower(),
            'fcmToken': self.fcm_token
        }
