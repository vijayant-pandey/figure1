"""
Defines the Data Model for Case, CaseComments and CaseRaw
"""
from datetime import datetime, timedelta, timezone
from sqlalchemy import Column, String
from figure1.core import managed_session, Base, HasCreateUpdateTime
from figure1.exceptions import TaskLockedException


class TaskLock(Base, HasCreateUpdateTime):
    __tablename__ = "q_scheduled_task_lock"
    scheduled_task_name = Column(String, nullable=False, primary_key=True)
    scheduled_task_id = Column(String, nullable=False)

    def islocked(self, scheduled_task_name, session=None):
        if not session:
            return False
        return session.query(TaskLock) \
            .filter(TaskLock.scheduled_task_name == scheduled_task_name) \
            .one_or_none()

    def lock(self, scheduled_task_name, scheduled_task_id, session=None):
        if not session:
            return False
        dt = datetime.now(tz=timezone.utc) - timedelta(hours=6)
        locked = self.islocked(scheduled_task_name, session=session)
        if locked:
            if locked.created_at > dt:
                raise TaskLockedException
            else:
                session.delete(locked)
                session.commit()
        task_lock = TaskLock()
        task_lock.scheduled_task_name = scheduled_task_name
        task_lock.scheduled_task_id = scheduled_task_id
        session.add(task_lock)
        session.commit()
        return task_lock

    def unlock(self, scheduled_task_name, scheduled_task_id, session=None):
        if not session:
            return False
        if self.islocked(scheduled_task_name):
            session.query(TaskLock) \
                .filter(TaskLock.scheduled_task_name == scheduled_task_name) \
                .filter(TaskLock.scheduled_task_id == scheduled_task_id) \
                .delete()
            session.commit()
        else:
            return None

    @managed_session
    def unlock_by_task_id(self, scheduled_task_id, session=None):
        if session.query(TaskLock).filter(TaskLock.scheduled_task_id == scheduled_task_id).one_or_none():
            session.query(TaskLock).filter(TaskLock.scheduled_task_id == scheduled_task_id).delete()
            session.commit()
