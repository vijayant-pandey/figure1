import logging
from typing import List, Optional
from ._connection import redis_conn
from ._utils import write_list

logger = logging.getLogger(__name__)


class TaskQueue:
    def __init__(self, task_name):
        self.task_queue_key = f"queue:{task_name}"

    def get_queue_len(self) -> int:
        return redis_conn.llen(self.task_queue_key)

    def write_queue(self, items: List) -> int:
        """
        Appends items to the head of the queue, does not delete existing items. There is no duplicate check.

        Queue items must be serialized, but there are no other restrictions.
        :param items:
        :return: Length of queue
        """
        if isinstance(items, list):
            if not items:
                return self.get_queue_len()
            write_list(items, self.task_queue_key)
        return self.get_queue_len()

    def delete_queue(self):
        """
        Delete queue, not normally necessary unless a task didn't complete
        :return:
        """
        redis_conn.delete(self.task_queue_key)

    def get_items(self, size: int) -> Optional[List]:
        """
        Get this number of items from the queue, this removes items from the queue.
        :param size:
        :return: None or list of items
        """
        if not size:
            return None
        try:
            size = int(size)
        except TypeError:
            return None

        p = redis_conn.pipeline()
        p.lrange(self.task_queue_key, start=0, end=size - 1)
        p.ltrim(self.task_queue_key, start=size, end=-1)
        resp = p.execute()
        return resp[0]

    def get_item(self):
        """
        Return the top item
        :return:
        """
        return redis_conn.lpop(self.task_queue_key)
