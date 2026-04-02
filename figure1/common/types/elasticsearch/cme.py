from pydantic import BaseModel, HttpUrl, validator
from pydantic.color import Color
from typing import Optional, List
from figure1.common.types import MediaType, FeedCardType, ContentType, ContentSection, CaseState, CaseType


class ESMediaModel(BaseModel):
    mediaUuid: str
    type = MediaType
    filename = str
    url = HttpUrl
    displayOrder: int
    width: Optional[int]
    height: Optional[int]


class ESContentItemModel(BaseModel):
    contentUuid: str
    caseUuid: str
    title: Optional[str]
    caption: Optional[str]
    contentType: ContentType
    isFeedCard: Optional[bool]
    section: Optional[ContentSection]
    media: List[ESMediaModel] = []
    externalLinkUrl: Optional[HttpUrl]
    externalLinkText: Optional[str]
    heading: Optional[str]
    colour: Optional[Color]
    isiLink: Optional[HttpUrl]
    isiText: Optional[str]
    isiEmbeddedContentLink: Optional[HttpUrl]
    feedCardLabel: Optional[str]
    feedCardTitle: Optional[str]
    references: Optional[str]
    buttonText: Optional[str]
    buttonUrl: Optional[HttpUrl]


class ESCaseModel(BaseModel):
    caseState: CaseState
    caseType: CaseType
    contentItems: List[ESContentItemModel]

    @validator('caseState', pre=True)
    def lower_case_state(cls, value):
        if value and isinstance(value, str):
            return value.lower()
        return value

    class Config:
        allow_population_by_field_name = True
        use_enum_values = True
