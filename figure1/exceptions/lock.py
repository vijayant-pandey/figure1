class TaskLockedException(Exception):
    pass


class TaskUnlockException(Exception):
    pass


class TooManyRequests(Exception):
    retry_after = 3
    return_code = 429
    msg = "Too Many Requests"

    def __init__(self, return_code=None, msg=None, retry_after=None):
        if retry_after is not None:
            self.retry_after = retry_after
        if msg is not None:
            self.msg = msg
        if return_code is not None:
            self.return_code = return_code

    def as_dict(self):
        return {'return_code': self.return_code, 'msg': self.msg, 'error': self.msg}
