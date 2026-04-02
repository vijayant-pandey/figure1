class VimeoError(Exception):
    def __init__(self, *args, **kwargs):
        self.rc = kwargs.get('return_code', 400)
        self.msg = kwargs.get('msg', 'General vimeo error raised')

    def __str__(self):
        return f"Vimeo error: f{self.msg}"

    def __repr__(self):
        return f"Raised error {self.msg} - return code {self.rc}"

    def as_dict(self):
        return {'return_code': self.rc, 'msg': self.msg}


class VimeoVideoNotFound(VimeoError):
    def __init__(self, *args, **kwargs):
        self.rc = kwargs.get('return_code', 404)
        self.msg = kwargs.get('msg', 'Video not found')

    def __str__(self):
        return f"Vimeo video was not found: f{self.msg}"
