class VerificationException(Exception):
    def __init__(self, *args, **kwargs):
        self.rc = kwargs.get('return_code', 400)
        self.user_uid = kwargs.get('user_uid')
        self.user_uuid = kwargs.get('user_uuid')


class InvalidVerificationType(VerificationException):
    pass


class InvalidVerificationStatus(VerificationException):
    pass


class VerificationNotFound(VerificationException):
    pass


class InvalidOperationForVerificationType(VerificationException):
    pass


class DuplicateVerificationRequest(VerificationException):
    def __init__(self, *args, **kwargs):
        self.rc = kwargs.get('return_code', 409)
        self.user_uuid = kwargs.get('user_uuid')
        self.verification_uuid = kwargs.get('verification_uuid')

    def __str__(self):
        return "Duplicate verification request received for %s from user %s" % (self.verification_uuid, self.user_uuid)


class VerificationMethodNotFound(VerificationException):
    pass


class NPIException(VerificationException):
    def __init__(self, *args, **kwargs):
        self.rc = kwargs.get('return_code', 400)
        self.user_uid = kwargs.get('user_uid')
        self.user_uuid = kwargs.get('user_uuid')
        self.npi_number = kwargs.get('npi')


class InvalidNPINumber(NPIException):
    pass


class InvalidAPIResponse(NPIException):
    pass


class NPIAPIError(NPIException):
    pass
