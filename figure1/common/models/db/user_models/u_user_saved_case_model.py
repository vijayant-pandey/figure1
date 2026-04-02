from sqlalchemy import Column
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from figure1.common.models.db.c_case_model import CaseAuthor
from figure1.core import Base
from figure1.core import HasCreateUpdateDeleteTime
from .u_user_follow_model import UserFollow


class UserSavedCase(Base, HasCreateUpdateDeleteTime):
    """
    The users relationship links to the Case table and returns a list of users who have saved this case
    The cases relationship links to the User table and returns a list of cases for a given user
    """

    __tablename__ = "u_user_saved_case"
    user_uuid = Column(UUID(as_uuid=True), ForeignKey('u_user.user_uuid'), primary_key=True)
    case_uuid = Column(UUID(as_uuid=True), ForeignKey('c_case.case_uuid'), primary_key=True)
    users = relationship("Case",
                         uselist=True,
                         primaryjoin=("and_(UserSavedCase.case_uuid == Case.case_uuid,"
                                      " UserSavedCase.deleted_at == None)"),
                         backref="user_saved_case")

    cases = relationship("User",
                         uselist=True,
                         primaryjoin=("and_(UserSavedCase.user_uuid == User.user_uuid,"
                                      " UserSavedCase.deleted_at == None)"),
                         backref="cases_saved")

    __table_args__ = (
        Index('idx_u_user_saved_case_uuid_deleted_at', 'case_uuid', 'deleted_at'),
    )

    @staticmethod
    def create(case_uuid, user_uuid, skip_commit=False, session=None):
        c = UserSavedCase()
        c.case_uuid = case_uuid
        c.user_uuid = user_uuid
        c.deleted_at = None
        return session.merge(c)

    @staticmethod
    def delete(case_uuid, user_uuid, skip_commit=False, session=None):
        s = session.query(UserSavedCase) \
            .filter(UserSavedCase.case_uuid == case_uuid,
                    UserSavedCase.user_uuid == user_uuid) \
            .one_or_none()
        if not s:
            return None

        s.mark_deleted()
        session.add(s)

        return s

    @staticmethod
    def get_is_saved(case_uuid, user_uuid, session=None):
        s = session.query(UserSavedCase) \
            .filter(UserSavedCase.case_uuid == case_uuid,
                    UserSavedCase.user_uuid == user_uuid,
                    UserSavedCase.deleted_at.is_(None)) \
            .one_or_none()
        return True if s else False

    def as_dict(self):
        return {
            'userUuid': str(self.user_uuid),
            'caseUuid': str(self.case_uuid)
        }

    @staticmethod
    def users_saved_cases_for_author(session, author_uuid):
        """
        returns a list of users who have saved any case authored by this author
        :param session:
        :param author_uuid:
        :return:
        """
        list_of_users = []
        for user_saved in session.query(UserSavedCase.user_uuid) \
                .join(CaseAuthor, UserSavedCase.case_uuid == CaseAuthor.case_uuid) \
                .filter(CaseAuthor.author_uuid == author_uuid,
                        UserSavedCase.deleted_at.is_(None)).group_by(UserSavedCase.user_uuid).all():
            list_of_users.append(str(user_saved.user_uuid))
        return list_of_users

    @staticmethod
    def users_saved_case_non_followers(session, author_uuid):
        """
        returns a list of users who saved this case but are non followers
        :param session:
        :param author_uuid:
        :return:
        """
        users_saved = list(UserSavedCase.users_saved_cases_for_author(session=session, author_uuid=author_uuid))
        users_followed = list(UserFollow.get_user_followers(session=session, user_uuid=author_uuid))
        for user in users_saved:
            if user in users_followed:
                continue
            yield str(user)

    @staticmethod
    def users_saved_case(session, case_uuid):
        """
        returns a list of users who saved this case
        :param session:
        :param case_uuid:
        :return:
        """
        list_of_users = []
        for user_saved in session.query(UserSavedCase.user_uuid).filter(UserSavedCase.case_uuid == case_uuid,
                                                                        UserSavedCase.deleted_at.is_(None)).all():
            list_of_users.append(str(user_saved.user_uuid))
        return list_of_users


class UserRecommendedCase(Base, HasCreateUpdateDeleteTime):
    """
    This table tracks cases that have been recommended to users through datafeeds so we can avoid repetition.
    """

    __tablename__ = 'u_user_recommended_case'
    user_uuid = Column(UUID(as_uuid=True), ForeignKey('u_user.user_uuid'), primary_key=True)
    case_uuid = Column(UUID(as_uuid=True), ForeignKey('c_case.case_uuid'), primary_key=True)

    @staticmethod
    def get_recommended(user_uuid, session):
        """
        Return a generator containing a list of case_uuids recommended to the user. Excludes records marked as deleted.
        :param user_uuid:
        :param session:
        :return:
        """
        for c in session.query(UserRecommendedCase.case_uuid)\
                .filter(UserRecommendedCase.user_uuid == user_uuid, UserRecommendedCase.deleted_at.is_(None))\
                .all():
            yield str(c[0])
