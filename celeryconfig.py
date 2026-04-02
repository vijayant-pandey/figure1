from kombu import Queue
from figure1.configuration import app_settings
import logging

# Simple debug logging for Redis connection troubleshooting
logger = logging.getLogger(__name__)
logger.info(f"=== REDIS CONNECTION DEBUG ===")
logger.info(f"Redis URL: {app_settings.redis_url}")
logger.info(f"Sentinel enabled: {app_settings.sentinel_enabled}")
logger.info(f"=== END REDIS CONNECTION DEBUG ===")

# Enhanced logging configuration for debugging Redis connection issues
imports = (
    'figure1.admin.campaign.case.tasks',
    'figure1.admin.migrate.cases.tasks',
    'figure1.admin.migrate.users.tasks',
    'figure1.admin.moderation.cases',
    'figure1.admin.moderation.tagging',
    'figure1.admin.reference_data',
    'figure1.common.models.firebase',
    'figure1.notifications.tasks',
    'figure1.common.token_rotator',
    'figure1.pro.cme',
    'figure1.pro.verification.tasks',
    'figure1.feeds',
    'figure1.common.models.firebase',
    'figure1.common.firebase',
    'figure1.common.elasticsearch',
    'figure1.common.comms',
    'figure1.tools',
    'figure1.events',
)

# Broker settings.
broker_url = app_settings.redis_url
if app_settings.sentinel_enabled:
    broker_url = ";".join(app_settings.redis_url)
    broker_transport_options = {'master_name': "redismaster"}
    result_backend_transport_options = {'master_name': "redismaster", 'visibility_timeout': 3600}
else:
    broker_transport_options = {}  # Initialize as empty dict when sentinel is disabled
    result_backend_transport_options = {'visibility_timeout': 3600}

# Log the final broker configuration
logger.info(f"Final broker_url: {broker_url}")
logger.info(f"Broker transport options: {broker_transport_options if app_settings.sentinel_enabled else 'None'}")

accept_content = ['pickle', 'json']


# Worker settings
worker_prefetch_multiplier = 1
worker_max_tasks_per_child = 10
worker_max_memory_per_child = 200000
worker_send_task_events = True


task_serializer = 'pickle'
task_send_sent_event = True
task_reject_on_worker_lost = True
task_queues = (
    Queue('celery'),
    Queue('service'),
    Queue('frontend'),
    Queue('backend'),
)
task_routes = {
    'figure1.service.*': {'queue': 'service'},
    'figure1.frontend.*': {'queue': 'frontend'},
    'figure1.backend.*': {'queue': 'backend'},
    '*': {'queue': 'celery'},
}
task_annotations = {
    'figure1.backend.get_mesh_data': {'rate_limit': '30/h', 'max_retries': 4},
    'figure1.service.get_npi_info': {'max_retries': 5}
}

result_backend = broker_url
result_serializer = 'pickle'
result_extended = True
result_expires = 3600

beat_max_loop_interval = 120.0

# Enhanced logging configuration for debugging Redis connection issues
worker_log_level = 'DEBUG'
worker_log_format = '[%(asctime)s: %(levelname)s/%(processName)s] %(message)s'
worker_task_log_format = '[%(asctime)s: %(levelname)s/%(processName)s][%(task_name)s(%(task_id)s)] %(message)s'

# Enable detailed logging for Redis/Kombu connections
worker_hijack_root_logger = False
worker_log_color = True

# Logging configuration for debugging Redis connections
logging_config = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'detailed': {
            'format': worker_log_format,
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
        'task_detailed': {
            'format': worker_task_log_format,
            'datefmt': '%Y-%m-%d %H:%M:%S',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'level': 'DEBUG',
            'formatter': 'detailed',
            'stream': 'ext://sys.stdout',
        },
    },
    'loggers': {
        'celery': {
            'level': 'DEBUG',
            'handlers': ['console'],
            'propagate': False,
        },
        'celery.worker': {
            'level': 'DEBUG',
            'handlers': ['console'],
            'propagate': False,
        },
        'celery.worker.consumer': {
            'level': 'DEBUG',
            'handlers': ['console'],
            'propagate': False,
        },
        'celery.worker.consumer.connection': {
            'level': 'DEBUG',
            'handlers': ['console'],
            'propagate': False,
        },
        'celery.worker.consumer.agent': {
            'level': 'DEBUG',
            'handlers': ['console'],
            'propagate': False,
        },
        'celery.worker.consumer.mingle': {
            'level': 'DEBUG',
            'handlers': ['console'],
            'propagate': False,
        },
        'celery.worker.consumer.gossip': {
            'level': 'DEBUG',
            'handlers': ['console'],
            'propagate': False,
        },
        'celery.worker.consumer.heartbeat': {
            'level': 'DEBUG',
            'handlers': ['console'],
            'propagate': False,
        },
        'celery.worker.consumer.control': {
            'level': 'DEBUG',
            'handlers': ['console'],
            'propagate': False,
        },
        'celery.worker.consumer.tasks': {
            'level': 'DEBUG',
            'handlers': ['console'],
            'propagate': False,
        },
        'celery.worker.consumer.connection': {
            'level': 'DEBUG',
            'handlers': ['console'],
            'propagate': False,
        },
        'celery.worker.consumer.connection.redis': {
            'level': 'DEBUG',
            'handlers': ['console'],
            'propagate': False,
        },
        'celery.worker.consumer.connection.sentinel': {
            'level': 'DEBUG',
            'handlers': ['console'],
            'propagate': False,
        },
        'kombu': {
            'level': 'DEBUG',
            'handlers': ['console'],
            'propagate': False,
        },
        'kombu.connection': {
            'level': 'DEBUG',
            'handlers': ['console'],
            'propagate': False,
        },
        'kombu.transport.redis': {
            'level': 'DEBUG',
            'handlers': ['console'],
            'propagate': False,
        },
        'kombu.transport.sentinel': {
            'level': 'DEBUG',
            'handlers': ['console'],
            'propagate': False,
        },
        'redis': {
            'level': 'DEBUG',
            'handlers': ['console'],
            'propagate': False,
        },
        'redis.connection': {
            'level': 'DEBUG',
            'handlers': ['console'],
            'propagate': False,
        },
        'redis.sentinel': {
            'level': 'DEBUG',
            'handlers': ['console'],
            'propagate': False,
        },
        'figure1': {
            'level': 'DEBUG',
            'handlers': ['console'],
            'propagate': False,
        },
        'figure1.core.tasks': {
            'level': 'DEBUG',
            'handlers': ['console'],
            'propagate': False,
        },
        'figure1.configuration': {
            'level': 'DEBUG',
            'handlers': ['console'],
            'propagate': False,
        },
    },
    'root': {
        'level': 'INFO',
        'handlers': ['console'],
    },
}

# Enable detailed connection logging
broker_connection_retry = True
broker_connection_retry_on_startup = True
broker_connection_max_retries = 10
broker_connection_retry_delay = 1.0

# Enable heartbeat for connection monitoring
broker_heartbeat = 10
broker_heartbeat_checkrate = 2.0

# Enable detailed task logging
task_always_eager = False
task_eager_propagates = True

# Enable detailed result backend logging

try:
    result_backend_transport_options = result_backend_transport_options or {}
except NameError:
    result_backend_transport_options = {}

result_backend_transport_options.update({
    'retry_policy': {
        'timeout': 5.0,
        'interval_start': 0,
        'interval_step': 0.2,
        'interval_max': 0.2,
        'max_retries': 3,
    }
})

# Enable detailed broker transport options logging
try:
    broker_transport_options = broker_transport_options or {}
except NameError:
    broker_transport_options = {}

broker_transport_options.update({
    'retry_policy': {
        'timeout': 5.0,
        'interval_start': 0,
        'interval_step': 0.2,
        'interval_max': 0.2,
        'max_retries': 3,
    },
    'socket_connect_timeout': 5.0,
    'socket_timeout': 5.0,
    'socket_keepalive': True,
    'socket_keepalive_options': {},
})

# Enable detailed worker logging
worker_disable_rate_limits = False
worker_enable_remote_control = True
worker_send_task_events = True
worker_recv_task_events = True

# Enable detailed task logging
task_ignore_result = False
task_store_errors_even_if_ignored = True
task_remote_tracebacks = True
