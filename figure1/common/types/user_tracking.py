from typing import Optional, Union, List
from pydantic import BaseModel, Field, validator, EmailStr, root_validator
from .screen_constants import CasePostingScreens, RegistrationSections


class CaseDraftData(BaseModel):
    title: Optional[str]
    caption: Optional[str]
    caseUid: Optional[str]


class ScreenTrackingData(BaseModel):
    screenId: Optional[str] = Field(alias='screen_id')
    caseDraftData: Optional[CaseDraftData] = Field(alias='case_data')

    @validator('screenId')
    def validate_screen_id(cls, value):
        if value in CasePostingScreens.draft_list() or value in RegistrationSections.sync_only_list():
            return value
        raise ValueError("Screen not in Case Posting list or registration list")


class MixpanelUserData(BaseModel):
    """
    To support mixpanel property naming conventions, this model is reversed.  Alias values hold the expected
    exported format, and the property names are the expected input.
    """
    email: str = Field(alias='$email')
    userUuid: str = Field(alias='User Uuid')
    userUid: Optional[str] = Field(alias='User Uid')
    username: Optional[str] = Field(alias='Username')
    firstName: Optional[str] = Field(alias='$first_name')
    lastName: Optional[str] = Field(alias='$last_name')
    professionName: Optional[str] = Field(alias='Profession')
    professionUuid: Optional[str] = Field(alias='Profession Uuid')
    npiNumber: Optional[str] = Field(alias='NPI Number')
    schoolName: Optional[str] = Field(alias='School')
    schoolUuid: Optional[str] = Field(alias='School Uuid')
    licenseNumber: Optional[str] = Field(alias='Medical License Number')
    graduationDate: Optional[str] = Field(alias='Date of Graduation')
    institutionalEmail: Optional[str] = Field(alias='Institutional Email')
    specialtyName: Optional[str] = Field(alias='Specialty')
    subspecialtyName: Optional[str] = Field(alias='Subspecialty')
    interests: Optional[List[str]] = Field(alias='Interests')
    interestsCount: Optional[int] = Field(alias='Interest Count')
    subscribedChannels: Optional[List[str]] = Field(alias='Subscribed Channels')
    subscribedChannelsCount: Optional[int] = Field(alias='Subscribed Channel Count')
    createdAt: Optional[str] = Field(alias='Account Created Date')
    verificationStatus: Optional[str] = Field(alias='Verification Status')
    practiceLocation: Optional[str] = Field(alias='Practice Location')
    practiceHospital: Optional[str] = Field(alias='Practice Hospital')
    followingCount: Optional[int] = Field(alias='Following Count')
    followerCount: Optional[int] = Field(alias='Follower Count')
    groups: Optional[List[str]] = Field(alias='Groups')

    class Config:
        orm_mode = True
        allow_population_by_field_name = True

    @root_validator(pre=True)
    def handle_properties(cls, values):
        verification = values.get('verification')
        if isinstance(verification, dict):
            values.update(**verification)
            npi = verification.get('npi')
            license_ = verification.get('license')
            instEmail = verification.get('institutionalEmail')
            if isinstance(npi, dict):
                values.update(**npi)
            if isinstance(license_, dict):
                values.update(**license_)
            if isinstance(instEmail, dict):
                values.update({'institutionalEmail': instEmail.get("email")})

        values['interestsCount'] = len(values.get('interests') or [])
        values['subscribedChannelsCount'] = len(values.get('subscribedChannels') or [])
        return values

    @validator('interests', pre=True, allow_reuse=True)
    def handle_interests(cls, value):
        if not value or not isinstance(value, List):
            return None
        return [x.get('interestName') for x in value]

    @validator('groups', pre=True, allow_reuse=True)
    def handle_groups(cls, value):
        return [each.get('groupUuid') for each in value]


class MixpanelLegacyUserData(BaseModel):
    """
    Mixpanel data for legacy user.  This data differs from the main MixpanelUserData class in that it should not be
    sent to mixpanel on a continuous basis.  Instead it is sent on first login to preserve legacy fields which
    may be changed during pro onboarding.
    """
    legacyAccount: Optional[bool] = Field(alias='Legacy')
    isVerified: Optional[bool] = Field(alias='Legacy Verified')
    hcp: Optional[bool] = Field(alias='Legacy HCP')
    mappedProfession: Optional[bool] = Field(alias='Legacy Mapped Profession')
    mappedSpecialty: Optional[bool] = Field(alias='Legacy Mapped Specialty')

    class Config:
        orm_mode = True
        allow_population_by_field_name = True


class MixpanelUserDeviceData(BaseModel):
    deviceId: str = Field(alias='Device Id')
    deviceType: str = Field(alias='Device Type')
    deviceLanguage: str = Field(alias='Device Language')

    class Config:
        allow_population_by_field_name = True
