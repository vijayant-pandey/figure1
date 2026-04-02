import logging

from sqlalchemy import func

from figure1.core import managed_session
from figure1.common.models.db import User


@managed_session
def get_user_by_username_case_insensitive(username, session=None):
    u = session.query(User) \
        .filter(func.lower(User.username) == func.lower(username)) \
        .one_or_none()
    return u.as_dict() if u else None


@managed_session
def get_user_by_email_case_insensitive(email, session=None):
    u = session.query(User) \
        .filter(func.lower(User.email) == func.lower(email)) \
        .one_or_none()
    return u.as_dict() if u else None
