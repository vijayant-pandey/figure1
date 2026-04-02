import json
import logging
import logging.config
import sys

from celery.signals import after_setup_logger
from pythonjsonlogger import jsonlogger

from .settings import AppSettings


class TaskFormatter(jsonlogger.JsonFormatter):
    """Formatter for tasks, adding the task name and id."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            from celery._state import get_current_task
            self.get_current_task = get_current_task
        except ImportError:
            self.get_current_task = lambda: None

    def formatException(self, exec_info):
        result = super(TaskFormatter, self).formatException(exec_info)
        r = repr(result)
        return json.dumps({'traceback': r})

    def format(self, record):
        task = self.get_current_task()
        if task and task.request:
            record.__dict__.update(task_id=task.request.id,
                                   task_name=task.name)
        else:
            record.__dict__.setdefault('task_name', '+++')
            record.__dict__.setdefault('task_id', '+++')
        return super().format(record)


def setup_worker_logger(app_settings=None):
    if not app_settings:
        app_settings = AppSettings() # type: ignore
    if not app_settings.console_log_enabled:
        worker_console_handler = logging.NullHandler()
    else:
        worker_console_handler = logging.StreamHandler()
        worker_console_handler.setStream(sys.stdout)
        worker_console_handler.setFormatter(task_formatter)
        worker_console_handler.setLevel(app_settings.log_level)

    return worker_console_handler


def configure_log_settings(app_settings=None):
    if not app_settings:
        app_settings = AppSettings() # type: ignore

    logging.config.dictConfig({
        'version': 1,
        'disable_existing_loggers': True,
    })
    logging.root.setLevel(app_settings.log_level)

    if not app_settings.console_log_enabled:
        console_handler = logging.NullHandler()
    else:
        console_handler = logging.StreamHandler()
        console_handler.setStream(sys.stdout)
        console_handler.setFormatter(console_formatter)

    f1 = logging.getLogger('figure1')
    f1.setLevel(app_settings.log_level)
    f1.addHandler(console_handler)
    f1.propagate = False

    sqlalchemy_logger = logging.getLogger('sqlalchemy')
    sqlalchemy_logger.setLevel(app_settings.log_level_sqlalchemy)
    sqlalchemy_logger.addHandler(console_handler)
    sqlalchemy_logger.propagate = False

    es_logger = logging.getLogger('elasticsearch')
    es_logger.setLevel(app_settings.log_level_elasticsearch)
    es_logger.addHandler(console_handler)
    es_logger.propagate = False

    gunicorn_access_logger = logging.getLogger('gunicorn.access')
    gunicorn_access_logger.setLevel(app_settings.log_level_gunicorn)
    gunicorn_access_logger.addHandler(console_handler)
    gunicorn_access_logger.propagate = True

    gunicorn_logger = logging.getLogger('gunicorn.error')
    gunicorn_logger.setLevel(app_settings.log_level_gunicorn)
    gunicorn_logger.addHandler(console_handler)
    gunicorn_logger.propagate = True


@after_setup_logger.connect
def setup_worker_loggers(logger, *args, **kwargs):
    """
    This is run after the celery task process has run through its setup, we are using the logger provided
    by celery so we don't have to deal with the multi-process mess. This configuration controls the output
    and default level. Do not override the logger that is passed in.

    """
    worker_console_handler = setup_worker_logger()
    logger.addHandler(worker_console_handler)


console_formatter = logging.Formatter(fmt='%(asctime)s [%(process)d] - %(name)s" - %(levelname)s - %(message)s')
json_formatter = jsonlogger.JsonFormatter(fmt='%(asctime)s %(process)d %(name)s %(levelname)s %(message)s',
                                          timestamp=True)
task_formatter = TaskFormatter(timestamp=True)
