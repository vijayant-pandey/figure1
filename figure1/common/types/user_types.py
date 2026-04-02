from enum import Enum
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, HttpUrl, Field, validator, EmailStr, root_validator, constr

from .anonymizable_model import AnonymizableBaseModel, AnonymousAuthorFields
from .user_state import OnboardingState
from .verification import UserVerificationDocument
from .specialties import SpecialtyTreeModel
from .reference import CountryModel


class _UserEduExpAffBase(BaseModel):
    isCurrent: bool = Field(alias='is_current', default=False)
    description: Optional[str]
    location: Optional[str]
    startYear: Optional[str] = Field(alias='start_year')
    endYear: Optional[str] = Field(alias='end_year')

    class Config:
        orm_mode = True
        allow_population_by_field_name = True

    @validator('educationUuid', 'experienceUuid', 'affiliationUuid', pre=True, check_fields=False)
    def stringify_uuid(cls, value):
        return str(value)

    @root_validator
    def set_end_year(cls, values):
        if values.get('isCurrent', False) is True:
            if values.get('endYear'):
                values['endYear'] = None
        return values


class UserEducationDocument(_UserEduExpAffBase):
    educationUuid: Optional[str] = Field(alias='education_uuid')


class UserExperienceDocument(_UserEduExpAffBase):
    experienceUuid: Optional[str] = Field(alias='experience_uuid')


class UserAffiliationsDocument(_UserEduExpAffBase):
    affiliationUuid: Optional[str] = Field(alias='affiliation_uuid')


class UserGroupDocument(BaseModel):
    groupUuid: Optional[str] = Field(alias='group_uuid')

    class Config:
        orm_mode = True
        allow_population_by_field_name = True

    @validator('groupUuid', pre=True, check_fields=False)
    def stringify_uuid(cls, value):
        return str(value) if value else None


class UserInterestV2Model(BaseModel):
    interestUuid: str = Field(alias='specialtyUuid')
    interestName: str = Field(alias='specialtyName')

    class Config:
        orm_mode = True


class UserDatabaseModel(BaseModel):
    firstName: Optional[str] = Field(alias='first_name')
    lastName: Optional[str] = Field(alias='last_name')
    createdAt: Optional[str] = Field(alias='created_at')
    followerCount: Optional[int] = Field(alias='user_follower_count', default=0)
    followingCount: Optional[int] = Field(alias='user_following_count', default=0)
    approvedCommentCount: Optional[int] = Field(alias='approved_comment_count')
    deletedCommentCount: Optional[int] = Field(alias='deleted_comment_count')
    reportedCommentCount: Optional[int] = Field(alias='reported_comment_count')
    approvedCaseCount: Optional[int] = Field(alias='approved_case_count')
    affiliations: Optional[List[UserAffiliationsDocument]] = Field(alias='user_affiliations', default=[])
    experience: Optional[List[UserExperienceDocument]] = Field(alias='user_experience', default=[])
    education: Optional[List[UserEducationDocument]] = Field(alias='user_education', default=[])
    groups: Optional[List[UserGroupDocument]] = Field(alias='user_groups', default=[])
    username: Optional[str]
    email: Optional[str]
    isDeleted: Optional[bool] = Field(alias='deleted_at', default=False)
    legacyAccount: Optional[bool] = Field(alias='legacy_account', default=False)
    userUid: Optional[str] = Field(alias='user_uid')
    userUuid: Optional[str] = Field(alias='user_uuid')

    @validator('userUuid', 'createdAt', pre=True)
    def stringify_uuid(cls, value):
        return str(value) if value else None

    @validator('isDeleted', pre=True)
    def user_deleted(cls, value):
        return True if value else False

    @validator('followerCount',
               'followingCount',
               'approvedCommentCount',
               'deletedCommentCount',
               'approvedCaseCount',
               pre=True)
    def set_default_count(cls, value):
        if value is None:
            return 0
        return value

    @validator('legacyAccount', pre=True)
    def force_bool_default(cls, value):
        if value is None:
            return False
        return value

    class Config:
        orm_mode = True
        allow_population_by_field_name = True


class UserStateDatabaseModel(BaseModel):
    lastSeen: Optional[datetime] = Field(alias='last_seen')
    onboardingCompleted: Optional[bool] = Field(alias='onboarding_completed')
    onboardingInterestsCompleted: Optional[bool] = Field(alias='onboarding_interests_completed')
    onboardingState: Optional[OnboardingState] = Field(alias='onboarding_state')
    userHiddenFromSearch: Optional[bool] = Field(alias='hidden_from_search', default=False)

    @validator('userHiddenFromSearch', pre=True)
    def force_default(cls, value):
        if value is None:
            return False
        return value

    class Config:
        orm_mode = True
        allow_population_by_field_name = True


class UserProfileDatabaseModel(BaseModel):
    displayName: Optional[str] = Field(alias='display_name')
    countryUuid: Optional[str] = Field(alias='country_uuid')
    stateUuid: Optional[str] = Field(alias='state_uuid')
    caseFeedEnabled: Optional[bool] = Field(alias='case_feed_enabled', default=False)
    caseFeedTitle: Optional[str] = Field(alias='case_feed_title')
    profileLink: Optional[HttpUrl] = Field(alias='profile_link')
    profileLinkText: Optional[str] = Field(alias='profile_link_text')
    profileDisplayName: Optional[str]
    caseCommentDisplayName: Optional[str]
    practiceHospital: Optional[str] = Field(alias='practice_hospital')
    practiceLocation: Optional[str] = Field(alias='practice_location')
    graduationDate: Optional[str] = Field(alias='graduation_date')
    avatar: Optional[HttpUrl] = None
    userBio: Optional[str] = Field(alias='user_bio')

    @validator('stateUuid', 'countryUuid', pre=True)
    def stringify_uuid(cls, value):
        return str(value) if value else None

    class Config:
        orm_mode = True
        allow_population_by_field_name = True

    @validator('graduationDate', pre=True)
    def parse_graduation_date(cls, value):
        if value:
            if isinstance(value, datetime):
                return value.strftime('%Y-%m-%d')
            elif isinstance(value, str):
                return value


class UserAuthorModel(AnonymizableBaseModel):
    """
    This model is intended to filter out unneeded fields to generate a compact model for comment and case authorship.
    It should take the dict output from user_detail and filter from there.
    """
    displayName: Optional[str]
    caseCommentDisplayName: Optional[str]
    profileDisplayName: Optional[str]
    avatar: Optional[HttpUrl] = None
    username: Optional[str]
    userUid: Optional[str]
    userUuid: Optional[str]
    profileLink: Optional[HttpUrl]
    profileLinkText: Optional[str]
    isDeleted: Optional[bool] = False
    isVerified: Optional[bool] = False
    professionName: Optional[str]
    userType: Optional[str]
    countryUuid: Optional[str]
    specialtyName: Optional[str]
    subspecialtyName: Optional[str]
    stateUuid: Optional[str]
    treeUuid: Optional[str]
    specialtyUuid: Optional[str]
    isPartner: Optional[bool] = False
    legacyAccount: Optional[bool] = False

    # If the self.isAnonymous is True, only fields not in self.fieldsToExcludeIfAnonymous would be
    # returned if self.dict is called.
    fieldsToExcludeIfAnonymous: dict = Field(default=AnonymousAuthorFields().toExclude,
                                             exclude=True)


class BaseUserModel(UserDatabaseModel, UserProfileDatabaseModel, UserStateDatabaseModel):
    userType: str = 'Figure1Member'
    onboardingDisplayName: Optional[str]
    professionName: Optional[str]
    professionUuid: Optional[str]
    specialtyName: Optional[str]
    subspecialtyName: Optional[str]
    isPartner: bool = False
    activityCount: int = 0
    isVerified: bool = Field(alias='is_verified', default=False)
    interests: Optional[List[UserInterestV2Model]]
    verification: Optional[UserVerificationDocument]
    specialties: Optional[SpecialtyTreeModel]
    primarySpecialty: Optional[SpecialtyTreeModel] = {}
    secondarySpecialties: Optional[List[SpecialtyTreeModel]] = []
    country: Optional[CountryModel]
    canEdit: bool = True
    professionChangeRequest: Optional[SpecialtyTreeModel] = {}
    archivedVerification: Optional[UserVerificationDocument]

    class Config:
        orm_mode = True
        allow_population_by_field_name = True
        use_enum_values = True


class UserModel(BaseUserModel):
    isVerified: bool = Field(alias='is_verified', default=False)

    class Config:
        orm_mode = True


class F100UserModel(BaseUserModel):
    isPartner: bool = True
    userType: str = 'Figure100'


class F1FriendsUserModel(BaseUserModel):
    isPartner: bool = True
    userType: str = 'Figure1Friends'


class F1InternalUserModel(BaseUserModel):
    userHiddenFromSearch: bool = True
    userType: str = 'Figure1Internal'


class F1OfficialUserModel(BaseUserModel):
    userType: str = 'Figure1Official'
    caseCommentDisplayName: Optional[str] = Field(alias="case_comment_display_name")
    profileDisplayName: Optional[str] = Field(alias="profile_display_name")


class PaidContributorUserModel(BaseUserModel):
    isPartner: bool = True
    userType: str = 'Figure1PaidContributor'


class EditorialPartnerUserModel(BaseUserModel):
    isPartner: bool = True
    userType: str = 'Figure1EditorialPartner'


class EditorialSubscriberUserModel(BaseUserModel):
    isPartner: bool = True
    userType: str = 'Figure1EditorialSubscriber'


class SponsoredUserModel(BaseUserModel):
    isPartner: bool = True
    userType: str = 'SponsoredUser'
    disclosureText: Optional[str] = Field(alias="disclosure_text")
    backgroundImage: Optional[HttpUrl] = Field(alias="background_image")
    canEdit: bool = False

    class Config:
        allow_population_by_field_name = True
        orm_mode = True


class InstitutionalUserModel(BaseUserModel):
    isPartner: bool = True
    userType: str = 'InstitutionalUser'
    canEdit: bool = False
    caseFeedEnabled: Optional[bool] = Field(alias="case_feed_enabled", default=True)
    disclosureText: Optional[str] = Field(alias="disclosure_text")
    backgroundImage: Optional[HttpUrl] = Field(alias="background_image")
    caseCommentDisplayName: Optional[str] = Field(alias="case_comment_display_name")
    profileDisplayName: Optional[str] = Field(alias="profile_display_name")

    class Config:
        orm_mode = True
        allow_population_by_field_name = True


class UserTypes(Enum):
    USER = UserModel
    FIGURE1_100 = F100UserModel
    FIGURE1_FRIENDS = F1FriendsUserModel
    FIGURE1_INTERNAL = F1InternalUserModel
    FIGURE1_OFFICIAL = F1OfficialUserModel
    FIGURE1_PAID_CONTRIBUTOR = PaidContributorUserModel
    FIGURE1_EDITORIAL_PARTNER = EditorialPartnerUserModel
    FIGURE1_EDITORIAL_SUBSCRIBER = EditorialSubscriberUserModel
    FIGURE1_SPONSORED = SponsoredUserModel
    FIGURE1_INSTITUTIONAL = InstitutionalUserModel


class UpdateUserModel(BaseModel):
    """
    This model is used to validate user updates so the name translation goes from the incoming structure
    to the database field name. This is why it appears backwards from other models that translate from the
    database field name to the external name.

    The fields that have max constraints on them are essentially guesses, if we need to adjust them, it should
    be noted in the description field so we know which ones are not guesses.
    They are set to try to keep us from crashing in case of a bug or much larger than expected input.
    """
    userType: Optional[UserTypes]
    first_name: Optional[constr(strip_whitespace=True, max_length=1000)] = Field(alias='firstName')
    last_name: Optional[constr(strip_whitespace=True, max_length=1000)] = Field(alias='lastName')
    email: Optional[EmailStr]
    username: Optional[str] = Field(min_length=3, max_length=100)
    user_bio: Optional[str] = Field(alias='userBio', max_length=10_000)
    practice_location: Optional[str] = Field(alias='userPracticeLocation', max_length=1000)
    practice_hospital: Optional[str] = Field(alias='userPracticeHospital', max_length=1000)
    display_name: Optional[str] = Field(alias='userDisplayName', max_length=1000)
    graduation_date: Optional[datetime] = Field(alias='graduationDate')
    sponsoredContentEnabled: Optional[bool] = Field(alias='sponsored_content_enabled')
    avatar: Optional[HttpUrl]
    country_uuid: Optional[str]
    state_uuid: Optional[str]
    interests: Optional[List[str]] = Field(max_items=100)
    specialtyTreeUuids: Optional[List[str]] = Field(alias='specialties', max_items=100)
    primarySpecialty: Optional[str]
    custom_specialty: Optional[str] = Field(alias='userCustomSpecialty', max_length=1000)
    custom_school: Optional[str] = Field(alias='userCustomSchool', max_length=1000)
    experience: Optional[List[UserExperienceDocument]] = Field(max_items=100)
    education: Optional[List[UserEducationDocument]] = Field(max_items=100)
    affiliations: Optional[List[UserAffiliationsDocument]] = Field(max_items=100)
    screen_id: Optional[str]
    onboardingCompleted: Optional[bool] = Field(alias='onboarding_completed')
    onboardingInterestsCompleted: Optional[bool] = Field(alias='onboarding_interests_completed')
    onboardingState: Optional[OnboardingState] = Field(alias='onboarding_state')
    userHiddenFromSearch: Optional[bool] = Field(alias='hidden_from_search', default=False)
    # Institutional User properties
    background_image: Optional[HttpUrl] = Field(alias='backgroundImage')
    disclosure_text: Optional[str] = Field(alias='disclosureText', max_length=10_000)
    profile_link: Optional[HttpUrl] = Field(alias='profileLink')
    profile_link_text: Optional[str] = Field(alias='profileLinkText', max_length=1000)
    case_comment_display_name: Optional[str] = Field(alias='caseCommentDisplayName', max_length=1000)
    profile_display_name: Optional[str] = Field(alias='profileDisplayName', max_length=1000)
    case_feed_enabled: Optional[bool] = Field(alias='caseFeedEnabled')
    case_feed_title: Optional[str] = Field(alias='caseFeedTitle', max_length=1000)

    class Config:
        allow_population_by_field_name = True

    @validator('country_uuid', 'state_uuid', pre=True)
    def stringify_uuid(cls, value):
        return str(value) if value else None

    @validator('graduation_date', pre=True)
    def parse_graduation_date(cls, value):
        if value:
            if isinstance(value, datetime):
                return value
            elif isinstance(value, str):
                return datetime.fromisoformat(value)
            else:
                raise ValueError
