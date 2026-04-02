from pydantic import BaseModel
from pydantic import Field
from pydantic import validator
from pydantic import root_validator
from pydantic import EmailStr
from email_validator import validate_email
from email_validator import EmailUndeliverableError
from typing import List, Optional
from datetime import datetime


__all__ = ['ItblBulkUserObject',
           'ItblSubscriptionUpdateRequest',
           'ItblUserBulkSubscriptionUpdate',
           'ItblUserBulkUpdate',
           'ItblUserProfile',
           'ItblUserProfileTarget']


class ItblUserProfileTarget(BaseModel):
    """
    This model is derived from the dictionary returned from UserDocument.user_detail, so the alias reflect the
    fieldnames that are in the user_types models.
    Many of these are stripped down however, so we have to manually pull out the data that is needed.
    """
    language: Optional[str]
    country: Optional[str]
    profession: Optional[str] = Field(alias='professionName')
    professionSpecialty: Optional[str] = Field(alias='profileDisplayName')
    specialtySubspecialty: Optional[str] = Field(alias='onboardingDisplayName')
    primarySpecialty: Optional[str]
    specialtyList: List[str] = []
    interests: Optional[List[str]] = []
    isVerified: bool = Field(alias='isVerified', default=False)
    isLegacy: bool = Field(alias='legacyAccount', default=False)
    isBio: bool = False
    isAvatar: bool = False
    isPracticeHospital: bool = False
    isPracticeLocation: bool = False
    isExperience: bool = False
    isEducation: bool = False
    isAffiliations: bool = False
    subscribedChannels: List[str] = []
    deviceLanguage: Optional[str]


class ItblUserProfile(BaseModel):
    """
    Parsing this object from the orm model will not populate the targetV1 object or the userType object.
    """
    userUid: Optional[str]
    userUuid: str
    username: Optional[str]
    email: EmailStr
    firstName: Optional[str]
    lastName: Optional[str]
    lastActive: Optional[str] = Field(alias='lastSeen', description='Changed due to incorrect formatting')
    phoneNumber: Optional[str]
    userType: Optional[str]
    isDeleted: Optional[bool] = False
    targetV1: Optional[ItblUserProfileTarget]
    graduationDate: Optional[str]

    @validator('lastActive', 'graduationDate', pre=True)
    def iterable_date_format(cls, value):
        if value:
            if isinstance(value, datetime):
                return value.strftime('%Y-%m-%d %H:%M:%S')
            elif isinstance(value, str):
                return datetime.fromisoformat(value).strftime('%Y-%m-%d %H:%M:%S')
            else:
                raise ValueError

    @validator('userUuid', pre=True)
    def stringify_uuid(cls, value):
        return str(value) if value else None

    @root_validator
    def get_user_email(cls, values):
        """
        If a user is deleted, we do not want to recreate the account in iterable
        """
        if values.get('isDeleted') is True:
            values['email'] = f"{values['userUuid']}@figure1.com"
        try:
            validate_email(values['email'])
        except EmailUndeliverableError:
            raise ValueError
        return values

    class Config:
        orm_mode = True
        extra = 'ignore'


class ItblBulkUserObject(BaseModel):
    email: EmailStr
    mergeNestedObject: bool = True
    userId: str
    dataFields: ItblUserProfile


class ItblSubscriptionUpdateRequest(BaseModel):
    email: Optional[EmailStr]
    userId: Optional[str]
    emailListIds: List[int] = []
    unsubscribedChannelIds: List[int] = []
    unsubscribedMessageTypeIds: List[int] = []
    subscribedMessageTypeIds: List[int] = []
    campaignId: int = 0
    templateId: int = 0


class ItblUserBulkUpdate(BaseModel):
    users: List[ItblBulkUserObject]


class ItblUserBulkSubscriptionUpdate(BaseModel):
    updateSubscriptionsRequests: List[ItblSubscriptionUpdateRequest]
