class IterableException(Exception):
    def __init__(self, *args, **kwargs):
        self.rc = kwargs.get('return_code', 501)
        self.msg = kwargs.get('msg', 'Iterable error')

    def as_dict(self):
        return {'return_code': self.rc, 'msg': self.msg}


class IterableMisconfiguredException(IterableException):
    def __init__(self, *args, **kwargs):
        self.rc = kwargs.get('return_code', 401)
        self.msg = kwargs.get('msg', 'Iterable API misconfigured')
        self.status = kwargs.get('status', 'API Error')

    def __str__(self):
        return 'Iterable misconfigured(%d) - error %s, msg: %s' % (self.rc, self.status, self.msg)


class IterableAPIException(IterableException):
    def __init__(self, *args, **kwargs):
        self.rc = kwargs.get('return_code')
        self.msg = kwargs.get('msg', 'No message passed')
        self.status = kwargs.get('status', 'Unknown error')

    def as_dict(self):
        return {'return_code': self.rc, 'msg': self.msg, 'status': self.status}

    def __str__(self):
        return 'Raised iterable exception: - %s\n Message: - %s' % (self.status, self.msg)


class IterableOverloadedException(IterableException):
    pass


class IterableUpdateException(IterableAPIException):
    pass


class IterableUserNotFound(IterableException):
    pass


class IterableUnsupportedDeviceType(IterableException):
    pass
