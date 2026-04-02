import uuid
import string
from random import choice

from typing import Optional, Dict
from sqlalchemy import Column, Text, Boolean, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from datetime import timezone, datetime

from figure1.core import Base, HasCreateUpdateDeleteTime
from figure1.common.types import ApiUserModel


def _generate_token(token_length=32):
    return ''.join(choice(
        string.ascii_lowercase +
        string.ascii_uppercase +
        string.digits)
                   for _ in range(token_length))


class ApiUser(Base, HasCreateUpdateDeleteTime):
    __tablename__ = 'api_user'
    api_user_uuid = Column(UUID(as_uuid=True), primary_key=True)
    api_user_enabled = Column(Boolean, default=True)
    api_user_token = Column(Text, nullable=False, unique=True)
    api_last_access = Column(DateTime(timezone=True), default=func.now(), index=True)

    @staticmethod
    def create_api_user(session) -> ApiUserModel:
        """
        Create an api user, returns the api key on success.
        :param session:
        :return:
        """

        api_user = ApiUser()
        api_user.api_user_enabled = True
        api_user.api_user_token = _generate_token()
        api_user.api_user_uuid = uuid.uuid4()
        session.add(api_user)
        session.flush()
        return ApiUserModel.from_orm(api_user)

    @staticmethod
    def delete_api_user(api_user_token):
        """
        Takes a token and disables, then marks the user as deleted.
        :return:
        """
        pass

    @staticmethod
    def disable_api_user(api_user_token):
        """
        Given an token, disables the user.
        :return:
        """
        pass

    @staticmethod
    def validate_api_token(api_user_token, session) -> Optional[Dict]:
        """
        Given a token, returns the user if the token is valid, else returns None. Returning None or
        False here denies the api key access.
        :return:
        """

        user = session.query(ApiUser) \
            .filter(ApiUser.api_user_token == api_user_token, ApiUser.api_user_enabled.is_(True)) \
            .one_or_none()
        if user:
            user.api_last_access = datetime.now(tz=timezone.utc)
            session.add(user)
            return ApiUserModel.from_orm(user).dict()
        return None
