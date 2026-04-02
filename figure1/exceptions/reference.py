class ReferenceDataException(Exception):
    def __init__(self, *args, **kwargs):
        self.msg = kwargs.get('msg', "General Reference Data exception")


class ReferenceDataReadError(ReferenceDataException):
    def __str__(self):
        return f'Reference data failed to read: {self.msg}'


class CommunicationSettingNotFound(ReferenceDataException):
    def __init__(self, *args, **kwargs):
        self.communication_uuid = kwargs.get('communication_uuid', '')
        self.return_code = kwargs.get('return_code', 404)
        self.msg = kwargs.get('msg', 'Communication setting not found')

    def as_dict(self):
        return {'return_code': self.return_code, 'msg': self.msg}


class CommunicationChannelNotFound(ReferenceDataException):
    def __init__(self, *args, **kwargs):
        self.communication_channel_uuid = kwargs.get('communication_channel_uuid', '')
        self.return_code = kwargs.get('return_code', 404)
        self.msg = kwargs.get('msg', 'Communication channel not found')

    def as_dict(self):
        return {'return_code': self.return_code, 'msg': self.msg}
