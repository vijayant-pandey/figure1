class CommentError(Exception):
    def __init__(self, *args, **kwargs):
        self.rc = kwargs.pop('return_code', 404)
        self.msg = kwargs.pop('msg', 'Comment Not Found')
        self.comment_uuid = kwargs.pop('comment_uuid', '')

    def __str__(self):
        return f"Comment error for UUID {self.comment_uuid}: {self.msg}"

    def __repr__(self):
        return f"Raised error {self.msg} - return code {self.rc}"

    def as_dict(self):
        return {'return_code': self.rc, 'msg': self.msg}


class CommentNotFound(CommentError):
    pass


class CommentEditNotSupported(CommentError):
    def __init__(self, *args, **kwargs):
        self.rc = kwargs.pop('return_code', 422)
        self.msg = kwargs.pop('msg', 'Comment edit not supported')
        self.comment_uuid = kwargs.pop('comment_uuid', '')


class AcceptedAnswerError(CommentError):
    def __init__(self, *args, **kwargs):
        self.rc = kwargs.pop('return_code', 422)
        self.msg = kwargs.pop('msg', 'There was an error with the accepted answer')
        self.comment_uuid = kwargs.pop('comment_uuid', '')
