from abc import abstractmethod


class NotAllowed(Exception):
    def __init__(self, *args, rc=422, message="Invalid Structure", **kwargs):
        self.rc = rc
        self.message = message

    @abstractmethod
    def as_dict(self):
        pass

    def __repr__(self):
        return f'Root Not Allowed exception'


class FoundNotAllowedWord(NotAllowed):
    def __init__(self, *args, rc=422, word=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.rc = rc
        self.word = word
        self.message = f'Found word {self.word} which is not allowed in this context'

    def __repr__(self):
        return f'Exception message {self.message} return code {self.rc}'

    def as_dict(self):
        return {'return_code': self.rc, 'error': self.message}


class UsernameNotAllowed(FoundNotAllowedWord):
    """
    Specific to usernames, this can also be raised if a username does not match required regex. Pass message if
    the regex does not match.
    """

    def __init__(self, *args, message=None, **kwargs):
        super().__init__(*args, **kwargs)
        if message:
            self.message = message
        else:
            self.message = f'Found word {self.word} which is not allowed as a username'

    def as_dict(self):
        return {'return_code': self.rc, 'error': self.message}
