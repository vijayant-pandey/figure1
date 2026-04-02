import logging

from celery import chain
from sqlalchemy import event

from figure1.core import global_session

logger = logging.getLogger(__name__)


@event.listens_for(global_session, 'after_commit')
def handle_session_commit(session):
    tasks = session.info.get('tasks')
    if tasks:
        logger.debug("Session committed.  Running %s pending tasks", len(tasks))
        chain(*tasks).delay()
        session.info['tasks'] = None
