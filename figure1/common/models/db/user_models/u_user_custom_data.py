from sqlalchemy import Column, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from figure1.core import HasCreateUpdateDeleteTime, Base
from .u_user_model import User


class UserCustomData(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "u_user_custom_data"
    user_uuid = Column(UUID(as_uuid=True), ForeignKey(User.user_uuid), primary_key=True)
    custom_school = Column(Text)
    custom_specialty = Column(Text)

    @staticmethod
    def create(session, user_uuid, custom_school=None, custom_specialty=None):
        u = session.query(UserCustomData).get(user_uuid)
        if not u:
            u = UserCustomData()
            u.user_uuid = user_uuid

        if custom_school:
            u.custom_school = custom_school
        if custom_specialty:
            u.custom_specialty = custom_specialty
        session.add(u)
        session.flush()
        return u

    @staticmethod
    def get(session, user_uuid):
        return session.query(UserCustomData).get(user_uuid)
