class NotificationException(Exception):
    def __init__(self, *args, **kwargs):
        self.rc = kwargs.get('return_code', 406)
        self.msg = kwargs.get('msg', 'notification error')
        self.notification_uuid = kwargs.get('notification_uuid', '')

    def as_dict(self):
        return {'return_code': self.rc, 'error': self.msg}


class NotificationNotFound(NotificationException):
    def __init__(self, *args, **kwargs):
        self.rc = kwargs.get('return_code', 404)
        self.msg = kwargs.get('msg', 'notification not found')

    def as_dict(self):
        return {'return_code': self.rc, 'error': self.msg}


class InvalidDeviceLanguage(NotificationException):
    def __init__(self, *args, **kwargs):
        self.rc = kwargs.get('return_code', 400)
        self.msg = kwargs.get('msg', 'Invalid device language')

    def as_dict(self):
        return {'return_code': self.rc, 'error': self.msg}
