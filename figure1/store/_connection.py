from redis import Redis, ConnectionPool
from redis.sentinel import Sentinel
from figure1.configuration import app_settings
import logging

logger = logging.getLogger(__name__)

redis_conn = None
try:
    if app_settings.sentinel_enabled:
        logger.info("Initializing Redis Sentinel connection")
        sentinel = Sentinel([(x.host, x.port) for x in app_settings.redis_url])
        m = sentinel.discover_master('redismaster')
        redis_conn = Redis(host=m[0], port=m[1], decode_responses=True)
        logger.info(f"Redis Sentinel connection established to {m[0]}:{m[1]}")
    else:
        logger.info(f"Initializing direct Redis connection to {app_settings.redis_url}")
        redis_conn = Redis.from_url(url=app_settings.redis_url, decode_responses=True)
        logger.info("Direct Redis connection established")
    
    # Test the connection
    redis_conn.ping()
    logger.info("Redis connection test successful")
    
except Exception as e:
    logger.error(f"Failed to establish Redis connection: {e}")
    logger.error(f"Redis URL: {app_settings.redis_url}")
    logger.error(f"Sentinel enabled: {app_settings.sentinel_enabled}")
    raise Exception(f"Redis connection failed: {e}")

if not redis_conn:
    raise Exception("Redis connection failed")
