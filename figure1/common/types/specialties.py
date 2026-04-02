from pydantic import BaseModel, Field, validator
from enum import Enum
from typing import Optional
import re


class StudentType(Enum):
    other_student = 'Other Student'
    other_non_hcp_student = 'Other non-HCP Student'
    medical_student = 'Medical Student'


class ProfessionCategoryDisplayOrder(Enum):
    physician = 0
    medicalresident = 1
    physicianassistant = 2
    registerednurse = 3
    nursepractitioner = 4
    medicalstudent = 5
    dentist = 6
    otherhcp = 7
    otherstudent = 8


class ProfessionModel(BaseModel):
    professionName: str = Field(alias='name')
    professionLabel: str = Field(alias='label')
    professionUuid: str = Field(alias='specialty_uuid')
    professionCategoryName: str = Field(alias='profession_category')
    professionCategoryLabel: str = Field(alias='profession_category')

    class Config:
        orm_mode = True
        extra = 'ignore'
        validate_assignment = True

    @validator('professionCategoryLabel', pre=True)
    def normalize_label(cls, value):
        label = re.sub(r'\s+', repl="", string=value)
        return label.lower()

    @validator('professionCategoryName', pre=True)
    def munge_category_names(cls, value):
        v = re.sub(r'\s+', repl="", string=value)
        if v.lower() == 'otherhcp':
            return 'Other Healthcare Professional'
        return value

    @validator('professionUuid', pre=True)
    def stringify_uuid(cls, value):
        return str(value)


class SpecialtyModel(BaseModel):
    specialtyName: str = Field(alias='name')
    specialtyLabel: str = Field(alias='label')
    specialtyUuid: str = Field(alias='specialty_uuid')
    isValidCaseTag: bool = Field(alias='is_valid_case_tag')
    isValidInterest: bool = Field(alias='is_valid_interest')

    class Config:
        orm_mode = True
        extra = 'ignore'
        validate_assignment = True

    @validator('specialtyUuid', pre=True)
    def stringify_uuid(cls, value):
        return str(value)


class SpecialtyTreeModel(BaseModel):
    treeUuid: Optional[str] = Field(alias='specialty_uuid')
    treeName: Optional[str] = Field(alias='name')
    displayOrder: Optional[int] = Field(alias='display_order')
    onboardingDisplayName: Optional[str] = Field(alias='onboarding_display_label')
    profileDisplayName: Optional[str] = Field(alias='profile_display_label')
    caseCommentDisplayName: Optional[str] = Field(alias='case_comment_display_label')
    profession: Optional[ProfessionModel]
    specialty: Optional[SpecialtyModel]
    subspecialty: Optional[SpecialtyModel]

    class Config:
        extra = 'ignore'
        orm_mode = True
        validate_assignment = True

    @validator('treeUuid', pre=True)
    def stringify_uuid(cls, value):
        return str(value)


class UserSpecialtyTreeV2Model(BaseModel):
    userUuid: str = Field(alias='user_uuid')
    treeUuid: str = Field(alias='tree_uuid')
    onboardingDisplayName: Optional[str]
    profileDisplayName: Optional[str]
    caseCommentDisplayName: Optional[str]
    isPrimary: Optional[bool] = Field(alias='is_primary')
    tree: SpecialtyTreeModel

    class Config:
        orm_mode = True

    @validator('treeUuid', 'userUuid', pre=True)
    def stringify_uuid(cls, value):
        return str(value)


class UserProfessionV2Model(BaseModel):
    userUuid: str = Field(alias='user_uuid')
    professionUuid: str = Field(alias='profession_uuid')
    profession: Optional[ProfessionModel]
    professionTree: Optional[SpecialtyTreeModel]
    onboardingDisplayName: Optional[str] = None
    profileDisplayName: Optional[str] = None
    caseCommentDisplayName: Optional[str] = None

    class Config:
        orm_mode = True
        ignore_extra = False

    @validator('professionUuid', 'userUuid', pre=True)
    def stringify_uuid(cls, value):
        return str(value)


class PublicTaxonomyModel(BaseModel):
    code: str
    grouping: Optional[str]
    classification: Optional[str]
    specialization: Optional[str]
    definition: Optional[str]
    notes: Optional[str]
    displayName: Optional[str] = Field(alias='display_name')
    section: Optional[str]

    profession: Optional[ProfessionModel]
    specialty: Optional[SpecialtyModel]
    subspecialty: Optional[SpecialtyModel]

    treeUuid: Optional[str]

    class Config:
        orm_mode = True
