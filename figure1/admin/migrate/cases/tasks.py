import logging
import signal
from datetime import datetime

from sqlalchemy import or_
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import Session

from figure1.core import TaskBase, celery_app
from figure1.common.models.db import LegacyCaseQueue, TaskLock, LegacyCase, Case
from figure1.common.types import CaseState
from figure1.exceptions import TaskLockedException, TaskUnlockException
from .create_legacy_case import upsert_legacy_case
from .create_pro_case import upsert_pro_case
from .prequel_model import CasesPrequelModel

logger = logging.getLogger("figure1.migrate.cases.tasks")


@celery_app.task(bind=True,
                 base=TaskBase,
                 name='figure1.backend.populate_case_queue')
def populate_case_queue(self):
    tl = TaskLock()
    lc = LegacyCaseSync()

    def unlock_on_exception():
        logging.error(f"Caught unexpected error or exception, attempting to unlock")
        tl.unlock(scheduled_task_name=self.request.task, scheduled_task_id=self.request.id, session=self.session)

    try:
        tl.lock(scheduled_task_name=self.request.task, scheduled_task_id=self.request.id, session=self.session)
        lc.get_legacy_cases(session=self.session)
        tl.unlock(scheduled_task_name=self.request.task, scheduled_task_id=self.request.id, session=self.session)
        return
    except TaskLockedException as task_locked:
        logging.error(f"Task {self.request.task} is locked by task id {self.request.id}")
        return
    except TaskUnlockException as unlock_err:
        logging.fatal(f"Task failed to unlock {unlock_err}")
        return

    except Exception as e:
        unlock_on_exception()
        raise e


@celery_app.task(bind=True,
                 base=TaskBase,
                 name='figure1.backend.propagate_case_updates')
def propagate_case_updates(self):
    tl = TaskLock()
    lc = LegacyCaseSync()

    def unlock_on_exception():
        logging.error(f"Caught unexpected error or exception, attempting to unlock")
        tl.unlock(scheduled_task_name=self.request.task, scheduled_task_id=self.request.id, session=self.session)

    try:
        tl.lock(scheduled_task_name=self.request.task, scheduled_task_id=self.request.id, session=self.session)
        lc.propagate_updates(session=self.session)
        tl.unlock(scheduled_task_name=self.request.task, scheduled_task_id=self.request.id, session=self.session)
        return
    except TaskLockedException as task_locked:
        logging.error(f"Task {self.request.task} is locked by task id {self.request.id}")
        return
    except TaskUnlockException as unlock_err:
        logging.fatal(f"Task failed to unlock {unlock_err}")
        return

    except Exception as e:
        unlock_on_exception()
        raise e


@celery_app.task(bind=True,
                 base=TaskBase,
                 name='figure1.backend.handle_deleted_cases')
def handle_deleted_cases(self):
    tl = TaskLock()
    lc = LegacyCaseSync()

    def unlock_on_exception():
        logging.error(f"Caught unexpected error or exception, attempting to unlock")
        tl.unlock(scheduled_task_name=self.request.task, scheduled_task_id=self.request.id, session=self.session)

    try:
        tl.lock(scheduled_task_name=self.request.task, scheduled_task_id=self.request.id, session=self.session)
        lc.handle_deleted_cases(session=self.session)
        tl.unlock(scheduled_task_name=self.request.task, scheduled_task_id=self.request.id, session=self.session)
        return
    except TaskLockedException as task_locked:
        logging.error(f"Task {self.request.task} is locked by task id {self.request.id}")
        return
    except TaskUnlockException as unlock_err:
        logging.fatal(f"Task failed to unlock {unlock_err}")
        return

    except Exception as e:
        unlock_on_exception()
        raise e


@celery_app.task(bind=True, base=TaskBase,
                 name='figure1.frontend.migrate_case')
def migrate_legacy_case(self, legacy_id=None):
    q = self.session.query(LegacyCaseQueue) \
        .filter(LegacyCaseQueue.legacy_case_id == legacy_id) \
        .one_or_none()

    if q:
        _migrate_legacy_case(q=q, prequel_model=CasesPrequelModel(), session=self.session)


def _migrate_legacy_case(q: LegacyCaseQueue,
                         prequel_model: CasesPrequelModel,
                         session: Session):
    case_dict = prequel_model.get_case(case_id=q.legacy_case_id)
    if not case_dict:
        logging.error(f"No case found or validation failed {q.legacy_case_id}")
        q.propagated_at = datetime.utcnow()
        session.add(q)
        return

    legacy_case = upsert_legacy_case(case_dict=case_dict,
                                     prequel_model=prequel_model,
                                     session=session)
    if not legacy_case:
        return

    pro_case = upsert_pro_case(legacy_case=legacy_case,
                               prequel_model=prequel_model,
                               session=session)
    if pro_case:
        q.case_uuid = pro_case.case_uuid
        q.propagated_at = datetime.now()


class LegacyCaseSync:
    def __init__(self):
        self.kill_signal = False
        signal.signal(signal.SIGINT, self.kill)
        signal.signal(signal.SIGHUP, self.kill)

    def kill(self, signum, stack):
        logging.error(f"Caught signal {signum}, shutting down")
        self.kill_signal = True

    def get_legacy_cases(self, session):
        prequel_model = CasesPrequelModel()
        legacy_queue = LegacyCaseQueue()
        logging.info("Syncing cases to legacy case queue")
        count = 0

        for case in prequel_model.get_case_ids():
            if self.kill_signal:
                logging.error("Caught kill signal, shutting down")
                session.commit()
                break
            count += 1
            legacy_queue.create_or_update(legacy_case_id=case["_id"],
                                          follower_count=case['followCount'],
                                          vote_count=case['voteCount'],
                                          comment_count=case['commentCount'],
                                          session=session)
            if not count % 10000:
                session.commit()
                logging.info("Committing case queue, completed %d", count)
        logging.info("Done syncing cases, completed %d", count)
        return self.kill_signal

    def propagate_updates(self, session):
        prequel_model = CasesPrequelModel()
        count = 0
        for q in session.query(LegacyCaseQueue) \
                .filter(or_(LegacyCaseQueue.updated_at > LegacyCaseQueue.propagated_at,
                            LegacyCaseQueue.propagated_at.is_(None))) \
                .order_by(LegacyCaseQueue.updated_at.desc()) \
                .limit(1000) \
                .all():
            if self.kill_signal:
                logging.error("Caught kill signal, shutting down")
                session.commit()
                break
            count += 1
            _migrate_legacy_case(q=q,
                                 prequel_model=prequel_model,
                                 session=session)
            if not count % 100:
                logger.info('Committing cases, completed %d', count)
                try:
                    session.commit()
                except DatabaseError as e:
                    logger.error("Failed to commit cases: %s", e)
                    session.rollback()
                    raise
        logging.info("Done updating cases, completed %d", count)
        return count

    def handle_deleted_cases(self, session):
        prequel_model = CasesPrequelModel()
        count = 0
        deleted_count = 0
        for res in session.query(LegacyCase, Case) \
                .join(Case, Case.case_uuid == LegacyCase.case_uuid) \
                .order_by(LegacyCase.created_at.asc()) \
                .filter(Case.deleted_at.is_(None)) \
                .all():
            if self.kill_signal:
                logger.error("Caught kill signal, shutting down")
                session.commit()
                break

            lc = res[0]
            c = res[1]

            count += 1
            if not count % 1000:
                logger.info('Committing cases, completed %d', count)
                try:
                    session.commit()
                except DatabaseError as e:
                    logger.error("Failed to commit cases: %s", e)
                    session.rollback()
                    raise
            if not prequel_model.get_case_exists(case_id=lc.legacy_id):
                deleted_count += 1
                logger.debug("Marking case deleted: %s", c.case_uuid)
                c.mark_deleted()
                c.state = CaseState.DELETED
                session.query(LegacyCaseQueue) \
                    .filter(LegacyCaseQueue.legacy_case_id == lc.legacy_id) \
                    .delete()
        logger.info("Finished.  Processed %d cases, marked %d as deleted", count, deleted_count)
        return count
