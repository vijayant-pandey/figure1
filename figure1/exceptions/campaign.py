class CampaignException(Exception):
    def __init__(self, *args, **kwargs):
        self.rc = kwargs.get('return_code', 500)
        self.msg = kwargs.get('msg', 'General campaign error raised')
        self.campaign_uuid = kwargs.get('campaign_uuid')

    def as_dict(self):
        return {
            'return_code': self.rc,
            'error': self.msg,
            'campaign_uuid': self.campaign_uuid
        }


class TacticError(CampaignException):
    def __init__(self, *args, **kwargs):
        self.rc = kwargs.get('return_code', 500)
        self.msg = kwargs.get('msg', 'General tactic error raised')
        self.case_uuid = kwargs.get('case_uuid')

    def as_dict(self):
        return {
            'return_code': self.rc,
            'error': self.msg,
            'case_uuid': self.case_uuid
        }


class InvalidCampaignDates(CampaignException):
    def __init__(self, *args, **kwargs):
        self.rc = kwargs.get('return_code', 422)
        self.msg = kwargs.get('msg', 'Invalid campaign dates')


class CampaignNotFound(CampaignException):
    def __init__(self, *args, **kwargs):
        self.campaign_uuid = kwargs.get('campaign_uuid', "")
        self.rc = kwargs.get('return_code', 404)
        self.msg = kwargs.get('msg', f"Could not find campaign with UUID {self.campaign_uuid}")


class TacticNotFound(TacticError):
    pass


class TacticDeleted(TacticError):
    pass


class TacticInvalidDates(TacticError):
    pass


class TacticUpdateError(TacticError):
    pass


class InvalidFeedCardType(TacticError):
    pass


class InvalidContentType(TacticError):
    pass


class InvalidSection(TacticError):
    pass


class InvalidPassingScore(TacticError):
    pass


class InvalidPostTest(TacticError):
    pass
