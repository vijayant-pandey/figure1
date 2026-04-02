#!/usr/bin/env python3
"""
Test script for token rotation with enhanced logging and error handling.
This script will help debug issues with the token rotation process.
"""

import os
import sys
import logging
from datetime import datetime

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Configure logging before importing figure1 modules
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('token_rotation_debug.log')
    ]
)

# Set specific loggers to DEBUG
logging.getLogger('token_rotator').setLevel(logging.DEBUG)
logging.getLogger('figure1.models.admin').setLevel(logging.DEBUG)
logging.getLogger('figure1.core').setLevel(logging.DEBUG)
logging.getLogger('figure1.configuration').setLevel(logging.DEBUG)

def test_token_rotation():
    """Test the token rotation process with detailed logging."""
    
    logger = logging.getLogger('test_token_rotation')
    logger.info("=== STARTING TOKEN ROTATION TEST ===")
    logger.info(f"Test started at: {datetime.now()}")
    
    try:
        # Import after logging configuration
        from figure1.common.token_rotator import run_token_rotator
        from figure1.common.models.db import BackendToken
        from figure1.core import managed_session
        
        logger.info("Successfully imported token rotation modules")
        
        # Test 1: Check environment
        logger.info("=== TEST 1: Environment Check ===")
        jwt_secret = os.environ.get('JWT_SECRET_KEY')
        logger.info(f"JWT_SECRET_KEY environment variable: {'SET' if jwt_secret else 'NOT SET'}")
        
        # Test 2: Check database connection
        logger.info("=== TEST 2: Database Connection Check ===")
        try:
            with managed_session() as session:
                # Try to query the BackendToken table
                token_count = session.query(BackendToken).count()
                logger.info(f"Database connection successful. Found {token_count} existing tokens")
                
                # Get the most recent token
                latest_token = session.query(BackendToken).order_by(BackendToken.created_at.desc()).first()
                if latest_token:
                    logger.info(f"Latest token created at: {latest_token.created_at}")
                    logger.info(f"Latest token UUID: {latest_token.uuid}")
                else:
                    logger.warning("No existing tokens found in database")
                    
        except Exception as e:
            logger.error(f"Database connection failed: {e}", exc_info=True)
            return False
        
        # Test 3: Run token rotation
        logger.info("=== TEST 3: Token Rotation ===")
        try:
            run_token_rotator()
            logger.info("Token rotation completed successfully")
        except Exception as e:
            logger.error(f"Token rotation failed: {e}", exc_info=True)
            return False
        
        # Test 4: Verify results
        logger.info("=== TEST 4: Verification ===")
        try:
            with managed_session() as session:
                # Check if a new token was created
                new_token = session.query(BackendToken).order_by(BackendToken.created_at.desc()).first()
                if new_token:
                    logger.info(f"New token created successfully")
                    logger.info(f"New token UUID: {new_token.uuid}")
                    logger.info(f"New token created at: {new_token.created_at}")
                    logger.info(f"New token expires in: {new_token.expires_secs} seconds")
                    
                    # Check if this is different from the previous token
                    if latest_token and new_token.uuid != latest_token.uuid:
                        logger.info("✓ Token rotation successful - new token is different from previous")
                    else:
                        logger.warning("⚠ Token rotation may have failed - new token is same as previous")
                else:
                    logger.error("No token found after rotation")
                    return False
                    
        except Exception as e:
            logger.error(f"Verification failed: {e}", exc_info=True)
            return False
        
        logger.info("=== TOKEN ROTATION TEST COMPLETED SUCCESSFULLY ===")
        return True
        
    except ImportError as e:
        logger.error(f"Failed to import required modules: {e}", exc_info=True)
        return False
    except Exception as e:
        logger.error(f"Unexpected error during test: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    success = test_token_rotation()
    sys.exit(0 if success else 1) 