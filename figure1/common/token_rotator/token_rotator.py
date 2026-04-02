"""
The administrator does 'administrative' stuff like handle frontend synchronization resets etc. Admin functionality is
not directly linked to end-user requirements/features. It is there to help us administer the system.
"""
import datetime
import logging
import os
from typing import Optional

from firebase_admin import db
from firebase_admin.exceptions import FirebaseError
from flask import Flask
from flask_jwt_extended import JWTManager
from flask_jwt_extended import create_access_token, decode_token
from jwt import ExpiredSignatureError, InvalidSignatureError
from sqlalchemy.exc import SQLAlchemyError

from figure1.common.models.db import BackendToken
from figure1.core import firebase_app, configure_environment, celery_app
from figure1.core import managed_session

logger = logging.getLogger('token_rotator')

secs_between_token_rotations = 300
token_expiry = 12 * secs_between_token_rotations * 24


@celery_app.task(serializer='pickle', name='figure1.service.token_rotator')
def run_token_rotator_task(jwt_secret_key=None):
    logger.debug("Starting token rotator task")
    try:
        run_token_rotator(jwt_secret_key=jwt_secret_key)
        logger.debug(f"jwt_secret_key: {jwt_secret_key}")
        logger.debug("Token rotator task completed successfully")
    except Exception as e:
        logger.error(f"Token rotator task failed: {e}", exc_info=True)
        raise


def run_token_rotator(jwt_secret_key=None):
    logger.debug("Initializing token rotator")
    if not jwt_secret_key:
        jwt_secret_key = os.environ.get('JWT_SECRET_KEY')
        logger.debug(f"JWT_SECRET_KEY: {jwt_secret_key}")
        logger.debug(f"Using JWT secret key from environment: {'SET' if jwt_secret_key else 'NOT SET'}")
    
    tr = TokenRotator(jwt_secret_key=jwt_secret_key)
    tr.run_service()


def validate_token(_token):
    """
    Throws an invalid signature error if the secrets do not match, otherwise will throw and expired signature error.
    :param _token:
    :return:
    """
    try:
        tok = decode_token(encoded_token=_token, allow_expired=False)
        logger.debug("Token validation successful")
        return tok
    except (ExpiredSignatureError, InvalidSignatureError) as e:
        logger.error(f"Saved token is invalid: {e}")
        return None


class TokenRotator:
    def __init__(self, jwt_secret_key):
        logger.debug("Initializing TokenRotator class")
        configure_environment()
        self._flask_app = Flask(__name__)
        self._flask_app.config['JWT_SECRET_KEY'] = jwt_secret_key
        self._jwt_manager = JWTManager(self._flask_app)
        logger.debug("TokenRotator class initialized successfully")

    def __create_access_token(self, expires_in):
        logger.debug(f"Creating access token with expiry: {expires_in} seconds")
        with self._flask_app.app_context():
            token = create_access_token(identity="figure1-firebase",
                                       expires_delta=datetime.timedelta(seconds=expires_in))
            logger.debug("Access token created successfully")
            return token

    @managed_session
    def _rotate_tokens(self, session=None):
        logger.debug("Starting token rotation process")
        
        # Step 1: Create new token
        logger.debug("Creating new JWT token")
        new_token = self.__create_access_token(expires_in=token_expiry)
        logger.debug(f"New token created with expiry: {token_expiry} seconds")
        
        # Step 2: Save to database
        logger.debug("Saving token to database")
        try:
            token = BackendToken.create_token(new_token, session=session)
            token.expires_secs = token_expiry
            session.commit()
            logger.info(f"Token saved to database successfully. Token UUID: {token.uuid}")
        except SQLAlchemyError as e:
            logger.error(f"Database error while saving token: {e}", exc_info=True)
            session.rollback()
            raise
        except Exception as e:
            logger.error(f"Unexpected error while saving token to database: {e}", exc_info=True)
            session.rollback()
            raise

        # Step 3: Update Firebase
        logger.debug("Updating Firebase Realtime Database")
        try:
            fb_app = firebase_app()
            logger.debug("Firebase app initialized successfully")
            
            shared_secret = db.reference(f'system/configuration/shared_secret', fb_app)
            logger.debug("Firebase reference created successfully")
            
            shared_secret.set(new_token)
            logger.info("Firebase shared_secret updated successfully")
            
        except FirebaseError as e:
            logger.error(f"Firebase error during token rotation: {e}", exc_info=True)
            # Don't raise here - database update succeeded, Firebase update failed
            # This allows the task to complete with partial success
        except Exception as e:
            logger.error(f"Unexpected error updating Firebase: {e}", exc_info=True)
            # Don't raise here - database update succeeded, Firebase update failed
            # This allows the task to complete with partial success
        
        logger.info('Token rotation process completed')

    def run_service(self):
        logger.info('Rotating Tokens...')

        try:
            self._rotate_tokens()
        except Exception as x:
            logger.exception('Fatal error rotating tokens...')
            raise x
