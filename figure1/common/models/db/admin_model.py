"""
Defines the data model for admin tasks not directly linked to end-user functionality
"""

import uuid
import logging

from sqlalchemy import Column, Integer, String
from sqlalchemy.dialects.postgresql import UUID

from figure1.core import Base, HasCreateTime, managed_session

logger = logging.getLogger('figure1.models.admin')

class BackendToken(Base, HasCreateTime):
    __tablename__ = 'a_firebase_token'

    # columns
    uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    expires_secs = Column(Integer, default=600, server_default='300', nullable=False)
    token = Column(String, nullable=False)

    @staticmethod
    @managed_session
    def get_token(session=None):
        """
        Get's the most recently created token
        """
        return session.query(BackendToken).order_by(BackendToken.created_at.desc()).first()

    @staticmethod
    @managed_session
    def get_text_token(session=None):
        t = BackendToken.get_token(session=session)
        return str(t.token)

    @staticmethod
    @managed_session
    def create_token(token, session=None):
        logger.debug("Creating new BackendToken record")
        try:
            t = BackendToken()
            t.uuid = uuid.uuid4()
            t.token = token
            logger.debug(f"BackendToken object created with UUID: {t.uuid}")
            
            session.add(t)
            logger.debug("BackendToken added to session")
            
            return t
        except Exception as e:
            logger.error(f"Error creating BackendToken: {e}", exc_info=True)
            raise


class ElasticsearchToken(Base, HasCreateTime):
    __tablename__ = 'a_elasticsearch_token'
    refresh_token = Column(String, primary_key=True)

    @staticmethod
    def set_refresh_token(session, old_refresh_token, new_refresh_token):

        t = session.query(ElasticsearchToken).get(old_refresh_token)
        if not t:
            t = ElasticsearchToken()
            session.query(ElasticsearchToken).delete()
        t.refresh_token = new_refresh_token
        session.add(t)
        try:
            session.commit()
        except Exception as e:
            session.rollback()
            raise

    @staticmethod
    def get_refresh_token(session):
        rt = session.query(ElasticsearchToken).one_or_none()
        if rt:
            return rt.as_dict()
        return None

    def as_dict(self):
        return {
            'refresh_token': self.refresh_token,
        }
