from ._connection import redis_conn


class TaskLock:
    def __init__(self, task_identifier):
        self.lock_key = f"lock:{task_identifier}"

    def check_lock_status(self, task_id):
        """
        :param task id: The unique identifier that identifies the lock
        :return: Returns True if locked, None if there is no key, False if the task_id does not match
        """
        lock = redis_conn.get(self.lock_key)
        if lock == task_id:
            return True
        if lock is None:
            return None
        return False

    def refresh_lock(self, task_id, expire_time=300):
        if self.check_lock_status(task_id):
            return self.set_ttl(task_id, expire_time)
        return False

    def create_lock(self, task_id, expire_time=300):
        """
        If lock exists with this task id, refresh the ttl
        If no lock exists, create one and set this expire time
        If a lock exists and is not owned by this task_id, return false
        """
        lock_status = self.check_lock_status(task_id)
        if lock_status is None:
            ret = redis_conn.setnx(self.lock_key, task_id)
            self.set_ttl(task_id, expire_time)
            return ret

        if lock_status is True:
            return self.set_ttl(task_id, expire_time)

        if lock_status is False:
            return False

    def unlock(self, task_id):
        if self.check_lock_status(task_id):
            redis_conn.delete(self.lock_key)

    def set_ttl(self, task_id, expire_time=300):
        if self.check_lock_status(task_id):
            return redis_conn.expire(self.lock_key, expire_time)
        return False
