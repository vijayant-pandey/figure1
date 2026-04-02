from typing import List
from typing import Optional

from pydantic import BaseModel
from pydantic import Field
from pydantic import HttpUrl
from pydantic import validator

from figure1.common.utils import markdown_all_urls
from .case import ContentSection
from .case import ContentType
from .case import ContentUpdateType
from .case import FeedCardType
from .field_validators import stringify_uuid
from .media import MediaModel
from .sponsored_content import FeaturesModel
from .sponsored_content import SponsoredContentModel


class ContentExtensionModel(BaseModel):
    buttonText: Optional[str] = Field(alias='button_text')
    buttonUrl: Optional[str] = Field(alias='button_url')
    questionAnswerDetails: Optional[str] = Field(alias='question_answer_details')
    externalLinkUrl: Optional[str] = Field(alias='external_link_url')
    externalLinkText: Optional[str] = Field(alias='external_link_text')
    heading: Optional[str] = Field(alias='heading')
    colour: Optional[str] = Field(alias='colour')
    isiLink: Optional[HttpUrl] = Field(alias='isi_link')
    isiText: Optional[str] = Field(alias='isi_text')
    isiEmbeddedContentLink: Optional[HttpUrl] = Field(alias='isi_embedded_content_link')
    feedCardLabel: Optional[str] = Field(alias='feed_card_label')
    feedCardTitle: Optional[str] = Field(alias='feed_card_title')
    references: Optional[str] = Field(alias='references')

    class Config:
        orm_mode = True


class ContentUpdateTranslationModel(BaseModel):
    text: Optional[str] = Field(alias='text')
    language: Optional[str] = Field(alias='language')

    class Config:
        orm_mode = True


class ContentUpdatesModel(BaseModel):
    text: str = Field(alias='text')
    createdAt: str = Field(alias='created_at')
    updatedAt: str = Field(alias='updated_at')
    updateType: ContentUpdateType = Field(alias='update_type')
    translations: Optional[List[ContentUpdateTranslationModel]] = Field(alias='translation')
    linkedUpdateUuid: Optional[str] = Field(alias='linked_update_uuid')

    _stringify_uuid = validator('createdAt',
                                'updatedAt',
                                'linkedUpdateUuid',
                                allow_reuse=True,
                                pre=True)(stringify_uuid)

    class Config:
        use_enum_values = True
        orm_mode = True


class ContentTranslationModel(BaseModel):
    title: Optional[str] = Field(alias='title')
    caption: Optional[str] = Field(alias='caption')
    language: Optional[str] = Field(alias='target_language')

    class Config:
        orm_mode = True


class ContentModel(BaseModel):
    contentUuid: str = Field(alias='content_uuid')
    caseUuid: str = Field(alias='case_uuid')
    commentCount: Optional[int] = Field(alias='approved_comments_count', default=0)
    displayOrder: Optional[int] = Field(alias='display_order', default=0)
    contentType: Optional[ContentType] = Field(alias='content_type', default=ContentType.CONTENT)
    title: Optional[str] = Field(alias='title')
    caption: Optional[str] = Field(alias='caption')
    isFeedCard: bool = Field(alias='is_feed_card', default=False)
    feedCardType: Optional[FeedCardType] = Field(alias='feed_card_type')
    section: Optional[ContentSection] = Field(alias='section')
    sponsoredContent: Optional[SponsoredContentModel] = Field(alias='sponsored_content', default={})
    features: Optional[FeaturesModel] = Field(alias='features', default={})
    updates: Optional[List[ContentUpdatesModel]] = Field(alias='updates', default=[])
    media: Optional[List[MediaModel]] = Field(alias='media', default=[])
    translations: Optional[List[ContentTranslationModel]] = Field(alias='translation', default=[])
    hasComments: Optional[bool] = Field(alias='has_comments', default=False)

    class Config:
        orm_mode = True
        arbitrary_types_allowed = True
        allow_population_by_field_name = True
        use_enum_values = True

    _stringify_uuid = validator('caseUuid', 'contentUuid', allow_reuse=True, pre=True)(stringify_uuid)

    @validator('media', pre=True)
    def strip_feed_card_media(cls, value):
        return [m for m in value if m.is_feed_card_media is not True]

    @validator('caption', pre=True)
    def handle_embedded_url(cls, value):
        if not value:
            return value
        return markdown_all_urls(value)
