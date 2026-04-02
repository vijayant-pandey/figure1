class S3Error(Exception):
    def __init__(self, *args, **kwargs):
        self.rc = kwargs.get('return_code', 400)
        self.msg = kwargs.get('msg', '')

    def as_dict(self):
        return {'return_code': self.rc, 'msg': self.msg}
