class TrackingException(Exception):
    def __init__(self, *args, **kwargs):
        self.rc = kwargs.get('return_code', 404)
        self.msg = kwargs.get("msg", "Tracking Exception")

    def as_dict(self):
        return {'return_code': self.rc, 'msg': self.msg}


class UserRegistrationTrackingError(TrackingException):
    def __init__(self, *args, **kwargs):
        super(UserRegistrationTrackingError, self).__init__(args, kwargs)
        self.msg = kwargs.get("msg", "Registration Screen Tracked Exception")
        self.screen_id = kwargs.get("screen_id")

    def __str__(self):
        return f"Attempt to track a user profile or registration update has failed: {self.msg}"

    def as_dict(self):
        return {'return_code': self.rc, 'msg': self.msg, 'screen_id': self.screen_id}


class UnknownScreenTrackedError(TrackingException):
    def __init__(self, *args, **kwargs):
        super(UnknownScreenTrackedError, self).__init__(args, kwargs)
        self.msg = kwargs.get("msg", "Unknown Screen Tracked Exception")

    def __str__(self):
        return f"UnknownScreenTracked rc={self.rc} and msg={self.msg}"

    def as_dict(self):
        return {'return_code': self.rc, 'msg': self.msg}
