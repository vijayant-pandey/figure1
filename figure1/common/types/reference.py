from typing import TypedDict, Optional, List
from pydantic.types import UUID
from pydantic import BaseModel, Field, validator


class SchoolReferenceDocument(TypedDict):
    school_name: str
    country_alpha3: str
    country_name: str
    region_name: str
    school_abbrev: str
    profession_name: str
    profession_uuid: UUID


class CountrySubDivModel(BaseModel):
    regionUuid: str = Field(alias='country_uuid')
    regionName: str = Field(alias='name')
    regionCode: Optional[str] = Field(alias='code')
    regionAlpha3: Optional[str] = Field(alias='alpha_3')
    regionType: Optional[str] = Field(alias='type')

    @validator('regionUuid', pre=True)
    def stringify(cls, value):
        return str(value) if value else None

    class Config:
        orm_mode = True


class CountryModel(BaseModel):
    countryUuid: str = Field(alias='country_uuid')
    countryName: str = Field(alias='name')
    countryCode: Optional[str] = Field(alias='code')
    countryAlpha3: Optional[str] = Field(alias='alpha_3')
    countryType: Optional[str] = Field(alias='type')

    @validator('countryUuid', pre=True)
    def stringify(cls, value):
        return str(value) if value else None

    class Config:
        orm_mode = True
