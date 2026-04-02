from typing import List
from typing import Optional

from enum import Enum
from pydantic import BaseModel
from pydantic import Field
from pydantic import validator
from pydantic import constr
from sqlalchemy.orm import Session

from figure1.common.types.field_validators import stringify_uuid


class MixpanelEvent(Enum):
    CASE_APPROVED = 'Approve Case'
    USER_VERIFIED = 'Verified'
    ONBOARDING_STARTED = 'Onboarding Started'
    ONBOARDING_COMPLETED = 'Onboarding Completed'


class MixpanelCaseEventData(BaseModel):
    """
    To support mixpanel property naming conventions, this model is reversed.  Alias values hold the expected
    exported format, and the property names are the expected input.
    """
    case_uuid: str = Field(alias='Case UUID')
    title: constr(curtail_length=20) = Field(alias='Title')
    status: str = Field(alias='Case Status')
    labels: List[str] = Field(alias='Case Labels')
    paging_type: str = Field(alias='Case Type')
    case_classification: str = Field(alias='caseClassification')
    author_uuid: Optional[str] = Field(alias='Author UUID')
    author_username: Optional[str] = Field(alias='Author Username')
    case_specialties: Optional[List[str]] = Field(alias='Case Specialties')

    class Config:
        allow_population_by_field_name = True

    _stringify_uuid = validator('case_uuid', 'author_uuid', allow_reuse=True, pre=True)(stringify_uuid)
