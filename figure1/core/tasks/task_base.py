import logging
from figure1.exceptions import UserError
from pydantic import ValidationError
from google.api_core.exceptions import Aborted, ClientError
from figure1.store import TaskLock
from celery import Celery
from celery.signals import task_prerun, task_postrun, celeryd_init, worker_init, worker_ready, worker_shutdown
from sqlalchemy.exc import DatabaseError

from figure1.configuration import app_settings
from figure1.core.db import global_session
from figure1.core.firebase import FirebaseClient

# Set up debug logging for Celery app initialization
logger = logging.getLogger(__name__)

celery_app: Celery = Celery('figure1')
celery_app.config_from_object('celeryconfig')

# Add debug logging for Celery app initialization
@celeryd_init.connect
def celeryd_init_handler(sender=None, conf=None, **kwargs):
    """Log Celery worker initialization details."""
    logger.info("=== CELERY APP INITIALIZED ===")
    logger.info(f"App name: {celery_app.main}")
    logger.info(f"Broker URL: {celery_app.conf.broker_url}")
    logger.info(f"Result backend: {celery_app.conf.result_backend}")
    
    logger.debug("=== CELERY WORKER INITIALIZATION START ===")
    logger.debug(f"Worker instance: {sender}")
    logger.debug(f"Configuration: {conf}")
    logger.debug(f"Broker URL: {conf.get('broker_url', 'NOT_SET')}")
    logger.debug(f"Result Backend: {conf.get('result_backend', 'NOT_SET')}")
    logger.debug(f"Task Queues: {conf.get('task_queues', 'NOT_SET')}")
    logger.debug(f"Imports: {conf.get('imports', 'NOT_SET')}")
    logger.debug("=== CELERY WORKER INITIALIZATION END ===")
    
    # Test connection attempt
    try:
        logger.info("=== ATTEMPTING BROKER CONNECTION ===")
        with celery_app.connection() as conn:
            logger.info(f"✓ SUCCESS: Connected to broker at {conn.as_uri()}")
            logger.info(f"  Transport: {conn.transport}")
            logger.info(f"  Hostname: {conn.hostname}")
            logger.info(f"  Port: {conn.port}")
    except Exception as e:
        logger.error(f"✗ FAILED: Broker connection error: {e}")
        logger.error(f"  Error type: {type(e).__name__}")
        if "Connection refused" in str(e):
            logger.error("  → Redis server is not running or not accessible")
        elif "timeout" in str(e).lower():
            logger.error("  → Connection timeout - check network/firewall")
        elif "authentication" in str(e).lower():
            logger.error("  → Authentication failed - check Redis password")
        elif "sentinel" in str(e).lower():
            logger.error("  → Sentinel connection failed - check sentinel config")

@worker_init.connect
def worker_init_handler(sender=None, **kwargs):
    """Log worker initialization details."""
    logger.debug("=== WORKER INITIALIZATION START ===")
    logger.debug(f"Worker: {sender}")
    logger.debug(f"Worker hostname: {getattr(sender, 'hostname', 'UNKNOWN')}")
    logger.debug(f"Worker app: {getattr(sender, 'app', 'UNKNOWN')}")
    logger.debug("=== WORKER INITIALIZATION END ===")

@worker_ready.connect
def worker_ready_handler(sender=None, **kwargs):
    """Log when worker is ready to process tasks."""
    logger.debug("=== WORKER READY ===")
    logger.debug(f"Worker {getattr(sender, 'hostname', 'UNKNOWN')} is ready to process tasks")
    logger.debug("=== WORKER READY END ===")

@worker_shutdown.connect
def worker_shutdown_handler(sender=None, **kwargs):
    """Log worker shutdown."""
    logger.debug("=== WORKER SHUTDOWN ===")
    logger.debug(f"Worker {getattr(sender, 'hostname', 'UNKNOWN')} is shutting down")
    logger.debug("=== WORKER SHUTDOWN END ===")

@task_prerun.connect()
def lock_task(signal, task, task_id, *args, **kwargs):
    """
    Runs before the task is sent to the worker. Properties set on the task are passed through, however returns are
    ignored.
    If there is another task id running the same task, this will set the task_locked property to true. It is up to
    the task to check this property before running.

    If a task is locked successfully, the task_lock_identifier is set to the task_id. This can be compared in the task
     to the task_id to determine if the current task has an authoritative lock.

     There is a specific catch for case sync currently that uses the case_uuid instead of the task id.
    """
    logger.debug(f"=== TASK PRERUN: {task.name} ({task_id}) ===")
    logger.debug(f"Task args: {args}")
    logger.debug(f"Task kwargs: {kwargs}")

    task.task_lock_identifier = None
    task.task_locked = False
    task_identifier = None
    case_uuid = None
    if task.name == 'figure1.frontend.firebase_sync':
        task_args = task.request.kwargs
        if task_args.get('firebasemodel') == 'CaseDetailV2':
            case_uuid = task_args.get('uuid')
            task_identifier = f'CaseDetailV2_{case_uuid}'
    else:
        task_identifier = task.name

    logger.debug(f"Task identifier: {task_identifier}")
    logger.debug(f"Case UUID: {case_uuid}")

    tl = TaskLock(task_identifier=task_identifier)

    status = tl.create_lock(task_id=task_id)
    logger.debug(f"Task lock status: {status}")
    
    if status is True:
        task.task_lock_identifier = task_id
    task.task_locked = True

    if case_uuid:
        tl.set_ttl(task_id=task_id, expire_time=app_settings.case_sync_throttle)
        logger.debug(f"Set TTL for case sync task: {app_settings.case_sync_throttle}")

    logger.debug(f"Task locked: {task.task_locked}")
    logger.debug(f"Task lock identifier: {task.task_lock_identifier}")
    logger.debug(f"=== TASK PRERUN END: {task.name} ({task_id}) ===")


@task_postrun.connect()
def unlock_task(signal, task, task_id, *args, **kwargs):
    logger.debug(f"=== TASK POSTRUN: {task.name} ({task_id}) ===")
    logger.debug(f"Task lock identifier: {getattr(task, 'task_lock_identifier', 'NOT_SET')}")
    
    if task_id == task.task_lock_identifier:
        tl = TaskLock(task_identifier=task.name)
        tl.unlock(task_id)
        logger.debug(f"Task unlocked: {task_id}")
    else:
        logger.debug(f"Task not unlocked - lock identifier mismatch")
    
    logger.debug(f"=== TASK POSTRUN END: {task.name} ({task_id}) ===")


class TaskBase(celery_app.Task):
    _session = None
    task_lock_identifier = None
    task_locked = False
    throws = (UserError, ValidationError,)

    def __init__(self):
        super().__init__()
        logger.debug(f"=== TASKBASE INIT: {self.__class__.__name__} ===")

    @property
    def session(self):
        if self._session is None:
            logger.debug("Creating new database session")
            self._session = global_session()
        if not self._session.is_active:
            logger.error("Session in bad state, rolling back session transaction")
            self._session.rollback()
        return self._session

    def before_start(self, task_id, args, kwargs):
        logger.debug(f"=== TASK BEFORE_START: {task_id} ===")
        logger.debug(f"Args: {args}")
        logger.debug(f"Kwargs: {kwargs}")
        self._session = global_session()
        logger.debug("Database session created in before_start")

    def after_return(self, status, retval, task_id, args, kwargs, einfo):
        logger.debug(f"=== TASK AFTER_RETURN: {task_id} ===")
        logger.debug(f"Status: {status}")
        logger.debug(f"Return value: {retval}")
        logger.debug(f"Exception info: {einfo}")
        
        try:
            self.session.commit()
            logger.debug("Database session committed successfully")
        except DatabaseError as e:
            logger.error(f"Database error during commit: {e}")
            self.session.rollback()
        finally:
            global_session.remove()
            logger.debug("Database session removed")

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(f"=== TASK FAILURE: {task_id} ===")
        logger.error(f"Exception: {exc}")
        logger.error(f"Args: {args}")
        logger.error(f"Kwargs: {kwargs}")
        logger.error(f"Exception info: {einfo}")
        super().on_failure(exc, task_id, args, kwargs, einfo)

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        logger.warning(f"=== TASK RETRY: {task_id} ===")
        logger.warning(f"Exception: {exc}")
        logger.warning(f"Args: {args}")
        logger.warning(f"Kwargs: {kwargs}")
        logger.warning(f"Exception info: {einfo}")
        super().on_retry(exc, task_id, args, kwargs, einfo)

    def on_success(self, retval, task_id, args, kwargs):
        logger.debug(f"=== TASK SUCCESS: {task_id} ===")
        logger.debug(f"Return value: {retval}")
        logger.debug(f"Args: {args}")
        logger.debug(f"Kwargs: {kwargs}")
        super().on_success(retval, task_id, args, kwargs)


class FirebaseTaskBase(TaskBase, FirebaseClient):
    autoretry_for = (Aborted, ClientError,)
    retry_backoff = 10
    _batch = None

    def __init__(self):
        logger.debug(f"=== FIREBASE TASKBASE INIT: {self.__class__.__name__} ===")
        super().__init__()

    @property
    def batch(self):
        if self._batch is None:
            logger.debug("Creating new Firebase batch")
            self._batch = self.fs_client.batch()
        return self._batch
