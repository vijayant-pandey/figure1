class CaseError(Exception):
    def __init__(self, *args, **kwargs):
        self.rc = kwargs.get('return_code', 404)
        self.msg = kwargs.get('msg', 'General case error')
        self.case_uuid = kwargs.get('case_uuid', '')
        self.content_uuid = kwargs.get('content_uuid', '')

    def __str__(self):
        return f"Case error for UUID {self.case_uuid}: {self.msg}"

    def __repr__(self):
        return f"Raised error {self.msg} - return code {self.rc}"

    def as_dict(self):
        return {'return_code': self.rc, 'msg': self.msg}


class CaseNotFound(CaseError):
    def __str__(self):
        return f"Failed to find case with UUID {self.case_uuid}: {self.msg}"


class ContentNotFound(CaseError):
    def __str__(self):
        return f"Failed to find content with UUID {self.content_uuid}: {self.msg}"


class CaseStateError(CaseError):
    def __init__(self, *args, **kwargs):
        self.rc = kwargs.get('return_code', 422)
        self.msg = kwargs.get('msg', f"Case is in invalid state")

    def __str__(self):
        return f"Case with UUID {self.case_uuid} is in an invalid state for this action: {self.msg}"


class CaseNotCompletedError(CaseError):
    def __init__(self, *args, **kwargs):
        self.rc = kwargs.get('return_code', 403)
        self.msg = kwargs.get('msg', f"Case has not been completed")
        self.case_uuid = kwargs.get('case_uuid', '')
        self.user_uuid = kwargs.get('user_uuid', '')


class CertificateTemplateNotFound(CaseError):
    def __init__(self, *args, **kwargs):
        self.rc = kwargs.get('return_code', 404)
        self.msg = kwargs.get('msg', f"Could not find certificate template")
        self.case_uuid = kwargs.get('case_uuid', '')
        self.user_uuid = kwargs.get('user_uuid', '')


class CertificateCreationError(CaseError):
    def __init__(self, *args, **kwargs):
        self.rc = kwargs.get('return_code', 404)
        self.msg = kwargs.get('msg', f"Failed to create the cme certificate")


class DraftNotFound(CaseError):
    def __str__(self):
        return f"Failed to find case draft with case UUID {self.case_uuid}: {self.msg}"


class CaseSyncThrottled(CaseError):
    pass


class CaseTranslationError(CaseError):
    pass


class FailedToCloneCaseToGroup(CaseError):
    def __str__(self):
        return f"Failed to clone case with case UUID {self.case_uuid}: {self.msg}"
