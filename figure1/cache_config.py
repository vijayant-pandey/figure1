import logging
from dogpile.cache import make_region
from figure1.configuration import app_settings

logger = logging.getLogger(__name__)


def generate_cache_key(namespace, fn, **kw):
    fname = fn.__name__

    def generate_key(*arg, **kw):
        if 'user_uuid' in kw:
            return f"{fname}_{kw.get('user_uuid')}"
        if 'user_uid' in kw:
            return f"{fname}_{kw.get('user_uid')}"
        if arg[0]:
            return f"{fname}_{arg[0]}"
        elif arg[1]:
            return f"{fname}_{arg[1]}"
        return f"{namespace}_{fname}"

    return generate_key


if app_settings.sentinel_enabled:
    sentinels = [[x.host, x.port] for x in app_settings.redis_url]
    cache_region = make_region(function_key_generator=generate_cache_key).configure(
        'dogpile.cache.redis_sentinel',
        arguments={
            'sentinels': sentinels,
            'service_name': 'redismaster',
            'redis_expiration_time': 60 * 60 * 1,
            'distributed_lock': True,
            'lock_sleep': 2,
            'thread_local_lock': False
        })
else:
    cache_region = make_region(function_key_generator=generate_cache_key).configure(
        'dogpile.cache.redis',
        arguments={
            'url': app_settings.redis_url,
            'redis_expiration_time': 60 * 60 * 1,
            'distributed_lock': True,
            'lock_sleep': 2,
            'thread_local_lock': False,
        }
    )
