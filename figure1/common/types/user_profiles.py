from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, HttpUrl
from typing import List, Optional
from datetime import datetime
from .verification import UserVerificationDocument

public_profile_exclude_keys = {
    'profile': {
        'countryUuid': ...,
        'stateUuid': ...,
        'userUuid': ...,
        'verification': ...,
    }
}


class UserProfileRoute(Enum):
    PROFILE_DETAIL_ROOT = "/profile"
    PROFILE_NOT_FOUND_ROOT = "/profile/user_not_found"


class UserEducationDocument(BaseModel):
    educationUuid: Optional[str]
    description: Optional[str]
    location: Optional[str]
    startYear: Optional[str]
    endYear: Optional[str]


class UserExperienceDocument(UserEducationDocument):
    experienceUuid: Optional[str]


class UserAffiliationsDocument(UserEducationDocument):
    affiliationUuid: Optional[str]


class ProfileDocument(BaseModel):
    username: Optional[str]
    email: Optional[str]
    displayName: Optional[str]
    practiceHospital: Optional[str]
    practiceLocation: Optional[str]


class UserPublicProfileDocument(BaseModel):
    """
    The reference to profile ends up being circular, but this is handled without too much fuss. To instantiate this
    for firestore, you will instantiate a user profile model and assign it to the profile variable. Then export
    it as a dict to sync to firestore, the whole process looks like this:
    a = UserPublicProfileDocument(activityCount=3)
    p = UserProfile(username='me')
    a.profile = p
    print(a.dict(exclude=public_profile_exclude_keys, exclude_none=True))
    > {'activityCount': 3, 'affiliations': [], 'experience': [], 'education': [], 'specialties': [],
     'profile': {'username': 'me'}}
    """
    activityCount: int = 0
    isVerified: bool = False
    affiliations: Optional[List[UserAffiliationsDocument]] = []
    experience: Optional[List[UserExperienceDocument]] = []
    education: Optional[List[UserEducationDocument]] = []
    specialties: Optional[List] = []
    profile: Optional[UserProfileDocument]

    class Config:
        extra = 'allow'


class UserProfileDocument(ProfileDocument):
    """
    The reference to public in this model ends up being circular, however the same method is used for this model as is
    used for UserPublicProfileDocument. First create the UserProfile instantiation, then create the public profile model
    without the profile class variable defined, and assign it to the UserProfile instantiated model.

    """
    firstName: Optional[str]
    lastName: Optional[str]
    userBio: Optional[str]
    userProfession: Optional[str]
    userSpecialty: Optional[str]
    userUid: Optional[str]
    userUuid: Optional[str]
    userProfessionUuid: List[Optional[str]] = []
    userSpecialtyUuid: List[Optional[str]] = []
    userSubSpecialtyUuid: List[Optional[str]] = []
    lastSeen: Optional[datetime]
    isVerified: bool = False
    language: str = 'EN'
    interests: Optional[List[str]] = []
    specialties: Optional[List[str]] = []
    countryUuid: Optional[str]
    stateUuid: Optional[str]
    verification: Optional[UserVerificationDocument]
    public: UserPublicProfileDocument = None

    class Config:
        extra = 'allow'


class InstitutionalProfileDocument(ProfileDocument):
    institutionalBio: Optional[str]
    backgroundImage: Optional[HttpUrl]
    disclosureText: Optional[str]
    profileLink: Optional[HttpUrl]
    avatar: Optional[HttpUrl]
    isInstitutionalProfile: bool = True

    class Config:
        extra = 'allow'


UserPublicProfileDocument.update_forward_refs()
UserProfileDocument.update_forward_refs()
