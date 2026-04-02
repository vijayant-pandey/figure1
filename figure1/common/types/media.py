import enum
from typing import Dict
from typing import List
from typing import Optional

from pydantic import BaseModel
from pydantic import Field
from pydantic import HttpUrl
from pydantic import validator

from .field_validators import force_lower_case
from .field_validators import stringify_uuid


class MediaType(enum.Enum):
    IMAGE = 'image'
    IMAGE_SERIES = 'image_series'
    VIDEO = 'video'


class MediaModel(BaseModel):
    mediaUuid: str = Field(alias='media_uuid')
    contentUuid: str = Field(alias='content_uuid')
    type: Optional[MediaType] = Field(alias='type')
    mediaId: Optional[str] = Field(alias='legacy_id')
    filename: Optional[str] = Field(alias='filename')
    originalFilename: Optional[str] = Field(alias='original_filename')
    url: Optional[HttpUrl] = Field(alias='url')
    media_url: Optional[HttpUrl] = Field(alias='url', description="Deprecated - kept for backwards compatibility")
    displayOrder: int = Field(alias='display_order')
    width: Optional[int] = Field(alias='width')
    height: Optional[int] = Field(alias='height')

    _stringify_uuid = validator('mediaUuid', 'contentUuid', allow_reuse=True, pre=True)(stringify_uuid)
    _force_lower = validator('type', allow_reuse=True, pre=True)(force_lower_case)

    class Config:
        use_enum_values = True
        orm_mode = True
        allow_population_by_field_name = True


class MediaUploadModel(BaseModel):
    """
    Similar to media model, but handles media before there is a media entry in Media
    """
    type: MediaType = Field(alias='type')
    url: HttpUrl = Field(alias='url')
    displayOrder: int = Field(alias='index')
    filename: Optional[str] = Field(alias='filename')
    width: Optional[int] = Field(default=0)
    height: Optional[int] = Field(default=0)
    originalFilename: Optional[str] = Field(alias='original_filename')

    _force_lower = validator('type', allow_reuse=True, pre=True)(force_lower_case)

    class Config:
        allow_population_by_field_name = True


class MediaModelByCase(BaseModel):
    caseUuid: str
    feedCard: MediaModel
    contentMedia: Dict[str, List[MediaModel]]

    _stringify_uuid = validator('caseUuid', allow_reuse=True, pre=True)(stringify_uuid)

    class Config:
        orm_mode = True
