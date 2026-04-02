import logging

from ._connection import redis_conn
from ._utils import write_set

logger = logging.getLogger(__name__)


class IterableSyncQueue:
    """
    The write method of this class can take either a string or a list of strings that are inserted into the queue set.
    This class may also be used as an iterable returning one item in the set until the set is empty.
    """
    iterable_queue_name = "iterable:user_sync:queue"
    iterable_queue_task = "iterable:user_sync:task"

    @classmethod
    def set_iterable_queue_name(cls, iterable_queue_name):
        """
        This method is used to change the queue name, in normal operation, this is unnecessary
        :param iterable_queue_name:
        :return:
        """
        cls.iterable_queue_name = iterable_queue_name

    @classmethod
    def set_queue_task(cls, task_id):
        """
        Setting is only allowed if the key does not exist
        :param task_id:
        :return:
        """
        if task_id is None:
            raise ValueError("Task id is required")
        return redis_conn.set(cls.iterable_queue_task, task_id, ex=300, nx=True)

    @classmethod
    def get_queue_task(cls, task_id=None):
        """
        If no task_id is passed, returns the value of the queue task, None if there is no task assigned. If a task_id
        is passed and it matches the currently registered task id, then update the expire time, if t is not set, then
        the passed in task_id is used to set it.
        :param task_id:
        :return:
        """
        t = redis_conn.get(cls.iterable_queue_task)
        if task_id is not None:
            if task_id == t:
                return redis_conn.setex(cls.iterable_queue_task, 300, task_id)
            if t is None:
                return cls.set_queue_task(task_id=task_id)
        return t

    @classmethod
    def remove_queue_task(cls, task_id):
        t = redis_conn.get(cls.iterable_queue_task)
        if t == task_id:
            redis_conn.delete(cls.iterable_queue_task)

    @classmethod
    def write(cls, items):
        if isinstance(items, list):
            write_set(items, cls.iterable_queue_name)
        elif isinstance(items, str):
            redis_conn.sadd(cls.iterable_queue_name, items)
        else:
            logger.error("Items must be a list or str")

    @classmethod
    def get(cls, count=1):
        return redis_conn.spop(cls.iterable_queue_name, count)

    @classmethod
    def get_queue_len(cls):
        return redis_conn.scard(cls.iterable_queue_name)

    @classmethod
    def __next__(cls):
        item = cls.get(count=1)
        if not item:
            raise StopIteration
        else:
            return item.pop()

    def __iter__(self):
        return self
