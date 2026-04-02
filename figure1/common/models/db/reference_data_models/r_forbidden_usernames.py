from figure1.core import Base, HasCreateUpdateDeleteTime
from sqlalchemy import Column, Text


class BlockedUsernames(Base, HasCreateUpdateDeleteTime):
    """
    1. forbidden_usernames
        - usernames that should be completely banned even when used in a larger word
    """

    __tablename__ = "r_forbidden_usernames"

    forbidden_usernames = Column(Text, index=True, primary_key=True)

    @staticmethod
    def usernames(session, forbidden_usernames):
        b = BlockedUsernames()
        b.forbidden_usernames = forbidden_usernames
        return session.merge(b)
