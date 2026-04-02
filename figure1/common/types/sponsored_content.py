from pydantic import BaseModel, Field, validator
from typing import Optional
from .field_validators import stringify_uuid


class FeaturesModel(BaseModel):
    featuresUuid: Optional[str] = Field(alias='features_uuid')
    isDefault: Optional[bool] = Field(alias='is_default')

    commentsEnabled: bool = Field(alias='comments_enabled', default=True)
    commentQueueEnabled: bool = Field(alias='comment_queue_enabled', default=False)
    commentTabsEnabled: bool = Field(alias='comment_tabs_enabled', default=True)
    dismissButton: bool = Field(alias='dismiss_button', default=True)
    dismissOnClick: bool = Field(alias='dismiss_on_click', default=True)
    reactionsEnabled: bool = Field(alias='reactions_enabled', default=True)
    reportEnabled: bool = Field(alias='report_enabled', default=True)
    saveEnabled: bool = Field(alias='save_enabled', default=True)
    shareEnabled: bool = Field(alias='share_enabled', default=True)
    showInMobile: bool = Field(alias='show_in_mobile', default=True)
    showInWeb: bool = Field(alias='show_in_web', default=True)
    showLabels: bool = Field(alias='show_labels', default=True)
    showViews: bool = Field(alias='show_views', default=True)
    similarCasesEnabled: bool = Field(alias='similar_cases_enabled', default=True)
    zoomEnabled: bool = Field(alias='zoom_enabled', default=True)

    _stringify_uuid = validator('featuresUuid', allow_reuse=True, pre=True)(stringify_uuid)

    class Config:
        allow_population_by_field_name = True
        orm_mode = True


class SponsoredContentModel(BaseModel):
    sponsoredText: Optional[str] = Field(alias='sponsored_text')
    disclosureText: Optional[str] = Field(alias='disclosure_text')
    jobCode: Optional[str] = Field(alias='job_code')

    class Config:
        allow_population_by_field_name = True
        orm_mode = True
