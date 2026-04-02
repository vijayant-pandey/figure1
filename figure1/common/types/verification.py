import enum
from typing import Optional
from typing import List
from datetime import datetime
from pydantic import BaseModel
from pydantic import validator
from pydantic import Field
from pydantic import root_validator
from pydantic import HttpUrl
from pydantic import EmailStr

from figure1.common.types.field_validators import stringify_uuid
from figure1.common.utils import validate_npi


class VerificationStatus(enum.Enum):
    ARCHIVED = "archived"
    UNVERIFIABLE = "unverifiable"
    PENDING_MANUAL_VERIFICATION = "pending_manual_verification"
    UPDATED_INFO = "updated_info"
    INFO_NEEDED = "info_needed"
    VERIFIED = "verified"
    DUPLICATE_NPI = "duplicate_npi"
    LEGACY_UNVERIFIED = "legacy_unverified"
    REVIEW_REQUIRED = "review_required"
    CHANGE_REQUESTED = "change_requested"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


class VerificationType(enum.Enum):
    PHOTO = "photo"
    NPI = "npi"
    LICENSE = "license"
    INSTITUTIONAL_EMAIL = "institutional_email"
    LEGACY = "legacy"


class UserNPIVerificationDocument(BaseModel):
    npiNumber: int = Field(alias='npi_number')
    npiEnumerationDate: Optional[str] = Field(alias='npi_enumeration_date')
    npiLastUpdate: Optional[str] = Field(alias='npi_last_update')
    npiDeactivationDate: Optional[str] = Field(alias='npi_deactivation_date')
    npiReactivationDate: Optional[str] = Field(alias='npi_reactivation_date')
    npiFirstName: Optional[str] = Field(alias='npi_first_name')
    npiMiddleName: Optional[str]
    npiLastName: Optional[str] = Field(alias='npi_last_name')
    npiGender: Optional[str] = Field(alias='npi_gender')
    npiStatus: Optional[str] = Field(alias='npi_status')
    npiPostalCode: Optional[str]
    npiAddress: Optional[str] = Field(alias='npi_address')
    npiCity: Optional[str]
    npiCountry: Optional[str]
    npiState: Optional[str]
    npiDuplicatedBy: Optional[List[str]] = Field(alias='npi_duplicated_by', default=[])
    npiCountryUuid: Optional[str] = Field(alias='npi_country_uuid')
    npiStateUuid: Optional[str] = Field(alias='npi_state_uuid')

    class Config:
        allow_population_by_field_name = True
        orm_mode = True

    @validator('npiDuplicatedBy', pre=True)
    def stringify_uuid_list(cls, value):
        return_list = []
        if isinstance(value, list):
            for v in value:
                return_list.append(str(v))
        else:
            return []

    @validator('npiNumber', pre=True)
    def npi_validator(cls, value):
        if not validate_npi(value):
            raise ValueError(f"Invalid NPI number: {value}")
        return value

    _stringify_uuid = validator('npiCountryUuid',
                                'npiStateUuid',
                                'npiEnumerationDate',
                                'npiLastUpdate',
                                'npiDeactivationDate',
                                'npiReactivationDate', allow_reuse=True, pre=True)(stringify_uuid)


class UserLicenseVerificationDocument(BaseModel):
    licenseNumber: Optional[str] = Field(alias='license_number')
    licenseCountry: Optional[str] = Field(alias='license_country')
    licenseState: Optional[str] = Field(alias='license_state')
    licenseCountryUuid: Optional[str] = Field(alias='license_country_uuid')
    licenseStateUuid: Optional[str] = Field(alias='license_state_uuid')

    class Config:
        orm_mode = True

    _stringify_uuid = validator('licenseCountryUuid', 'licenseStateUuid', allow_reuse=True, pre=True)(stringify_uuid)


class UserProfessionChangeRequestDocument(BaseModel):
    professionTreeUuid: Optional[str] = Field(alias='requested_profession')
    requestResolved: Optional[bool] = Field(alias='request_resolved')
    archivedVerificationUuid: Optional[str] = Field(alias='archived_verification_uuid')

    class Config:
        orm_mode = True

    _stringify_uuid = validator('professionTreeUuid', 'archivedVerificationUuid', allow_reuse=True, pre=True)(
        stringify_uuid)


class UserInstitutionalEmailDocument(BaseModel):
    email: Optional[str] = Field(alias='institutional_email')

    class Config:
        orm_mode = True


class UserVerificationHistoryModel(BaseModel):
    verificationEventInitiator: Optional[str] = Field(alias='verification_event_initiator')
    verificationEventDescription: Optional[str] = Field(alias='verification_event_description')
    verificationEventUuid: Optional[str] = Field(alias='verification_event_uuid')
    verificationEventInitiatorUsername: Optional[str]
    verificationEventCreatedAt: Optional[str] = Field(alias='created_at')

    class Config:
        orm_mode = True

    @validator('verificationEventCreatedAt', pre=True)
    def stringify_date(cls, date) -> Optional[str]:
        return str(date) if date else None

    _stringify_uuid = validator('verificationEventUuid', 'verificationEventInitiator', allow_reuse=True, pre=True)(
        stringify_uuid)


class UserVerificationPhotos(BaseModel):
    """
    This is a little ugly, but it was the most general way I could come up with to collapse the multiple photos into
    a single list.

    The root validator means that only verificationPhotos will ever be returned from a validated model. This can be
    an empty list or currently up to 4 photos.
    """
    verification_photo: Optional[HttpUrl]
    verification_photo2: Optional[HttpUrl]
    verification_photo3: Optional[HttpUrl]
    verification_photo4: Optional[HttpUrl]
    verificationPhoto: Optional[List[HttpUrl]]

    @root_validator()
    def generate_list(cls, values):
        photo_list = []
        for k, v in values.items():
            if v is not None:
                photo_list.append(v)
        return {'verificationPhoto': photo_list}

    class Config:
        orm_mode = True


class UserInstitutionalEmail(BaseModel):
    email: Optional[EmailStr]

    class Config:
        orm_mode = True


class UserVerificationDocument(BaseModel):
    verificationStatus: Optional[VerificationStatus] = Field(alias='verification_status', default='unknown')
    verificationUuid: Optional[str] = Field(alias='verification_uuid')
    verificationType: Optional[VerificationType] = Field(alias='verification_type')
    verificationHistory: List[UserVerificationHistoryModel] = Field(alias='verification_history', default=[])
    verificationFlaggedForReview: Optional[bool] = Field(default=False, alias='flagged_for_review')
    npi: Optional[UserNPIVerificationDocument] = Field(alias='npi')
    license: Optional[UserLicenseVerificationDocument] = Field(alias='license')
    professionChangeRequest: Optional[UserProfessionChangeRequestDocument] = Field(alias='profession_change_request')
    institutionalEmail: Optional[UserInstitutionalEmail] = Field(alias='institutional_email')
    verificationPhoto: Optional[List[HttpUrl]] = []
    verificationCreatedAt: Optional[datetime] = Field(alias='created_at')
    verificationUpdatedAt: Optional[datetime] = Field(alias='updated_at')
    graduationYear: Optional[str]
    schoolName: Optional[str]
    schoolUuid: Optional[str]
    isVerified: Optional[bool] = False
    professionTreeUuid: Optional[str] = Field(alias='profession_tree_uuid')

    class Config:
        orm_mode = True
        use_enum_values = True

    @validator('institutionalEmail', pre=True)
    def handle_institutional_email(cls, value):
        if value is not None:
            return UserInstitutionalEmail(email=value)

    @root_validator()
    def validate_model(cls, values):
        if values.get('verificationStatus', None) in ('verified', 'change_requested'):
            values.update({'isVerified': True})
        return values

    _stringify_uuid = validator('schoolUuid', 'verificationUuid', 'professionTreeUuid', allow_reuse=True, pre=True)(
        stringify_uuid)


class UserVerificationUpdate(BaseModel):
    method: VerificationType
    user_uid: str
    license_number: Optional[str]
    license_country_code: Optional[str]
    license_state_code: Optional[str]
    license_school_code: Optional[str]
    npi_number: Optional[int]
    primary_specialty_code: Optional[str]
    graduation_year: Optional[int]
    institutional_email: Optional[EmailStr]
    photos: Optional[List[HttpUrl]]

    @root_validator
    def validate_required_values(cls, values):
        if values.get('method') is VerificationType.NPI:
            if not values.get('npi_number'):
                raise ValueError("Missing value for npi_number")

        elif values.get('method') is VerificationType.INSTITUTIONAL_EMAIL:
            if not values.get('institutional_email'):
                raise ValueError("Missing value for institutional_email")

        elif values.get('method') is VerificationType.PHOTO:
            if not values.get('photos'):
                raise ValueError("Missing value for photos")
            elif len(values.get('photos')) > 4:
                raise ValueError("Number of photos exceeds limit")

        elif values.get('method') is VerificationType.LICENSE:
            required = ['license_number', 'license_country_code', 'graduation_year']
            for r in required:
                if not values.get(r):
                    raise ValueError(f"Missing value for {r}")

        else:
            raise ValueError("Unsupported method")

        return values


class UserVerificationSource(enum.Enum):
    DMD = 'dmd'


class DmdNpiDataModel(BaseModel):
    user_uuid: str
    email: str
    first_name: Optional[str]
    last_name: Optional[str]
    npi_number: Optional[int]
    profession: Optional[str]
    specialty: Optional[str] = Field(alias='speciality')
    subspecialty: Optional[str]
    country: Optional[str]
    state: Optional[str]
    practice_hospital: Optional[str]
    practice_location: Optional[str]
    graduation_date: Optional[datetime]
    school: Optional[str]

    dmd_hcp_type: Optional[str] = Field(alias='DMD_HCP_TYPE')
    dmd_dgid: Optional[str] = Field(alias='DMD_DGID')
    dmd_firstname: Optional[str] = Field(alias='DMD_FIRSTNAME')
    dmd_lastname: Optional[str] = Field(alias='DMD_LASTNAME')
    dmd_degree: Optional[str] = Field(alias='DMD_DEGREE')
    dmd_primary_specialty: Optional[str] = Field(alias='DMD_PRIMARY_SPECIALTY')
    dmd_specialty_long_description: Optional[str] = Field(alias='DMD_SPECIALTY_LONG_DESCRIPTION')
    dmd_npi: Optional[int] = Field(alias='DMD_NPI')
    dmd_state: Optional[str] = Field(alias='DMD_STATE')

    @validator('npi_number', 'dmd_npi', pre=True)
    def parse_npi(cls, value):
        if value:
            if isinstance(value, int):
                return value
            if isinstance(value, str):
                return int(value)
            else:
                raise ValueError(f"Invalid npi number: {value}")

        return None

    @validator('graduation_date', pre=True)
    def parse_graduation_date(cls, value):
        if value:
            if isinstance(value, datetime):
                return value
            elif isinstance(value, str):
                return datetime.fromisoformat(value)

        return None


UserProfessionChangeRequestDocument.update_forward_refs()
