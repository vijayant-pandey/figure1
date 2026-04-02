from enum import Enum
from pydantic import BaseModel
from typing import Optional, List


class CampaignState(Enum):
    ARCHIVED = -1,
    DRAFT = 1,
    ACTIVE = 2,

    @classmethod
    def has_key(cls, name):
        return name.upper() in cls.__members__


class CampaignTactic(BaseModel):
    campaignUuid: str
    campaignState: str
    tacticName: Optional[str]
    startDate: Optional[str]
    endDate: Optional[str]
    treeTargets: List[Optional[str]]
    countryTargets: List[Optional[str]]
    languageTargets: Optional[str]
    verificationTarget: Optional[bool]
    tacticPriority: Optional[int]
    campaignPriority: Optional[int]

    class Config:
        extra = 'forbid'
