from figure1.core import Base, HasCreateUpdateDeleteTime
from sqlalchemy import Column, Text


class LessBlockedUsernames(Base, HasCreateUpdateDeleteTime):
    """
    less_forbidden_usernames
        - only allowed when part of a larger word
    """

    __tablename__ = "r_less_forbidden_usernames"

    less_forbidden_usernames = Column(Text, index=True, primary_key=True)

    @staticmethod
    def usernames(session, less_forbidden_usernames):
        b = LessBlockedUsernames()
        b.less_forbidden_usernames = less_forbidden_usernames
        return session.merge(b)
