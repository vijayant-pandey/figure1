import uuid
from sqlalchemy import Column
from sqlalchemy import String
from sqlalchemy import Integer
from sqlalchemy import Date
from sqlalchemy import Enum
from sqlalchemy import ForeignKey
from sqlalchemy import ARRAY
from sqlalchemy import BigInteger
from sqlalchemy import Boolean
from sqlalchemy.orm import backref, relationship
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy_utils import observes

from figure1.common.types.verification import UserVerificationSource
from figure1.core import HasCreateUpdateTime
from figure1.core import Base
from figure1.common.types import VerificationType
from figure1.common.types import VerificationStatus
from .u_user_model import User
from figure1.common.models.db.reference_data_models import School
from figure1.common.models.db.reference_data_models import Country


class UserVerification(Base, HasCreateUpdateTime):
    __tablename__ = "u_user_verification"
    verification_uuid = Column(UUID(as_uuid=True), primary_key=True)
    user_uuid = Column(UUID(as_uuid=True), ForeignKey(User.user_uuid), index=True)
    verification_type = Column(Enum(VerificationType))
    verification_status = Column(Enum(VerificationStatus))
    verification_photo = Column(String)
    verification_photo2 = Column(String)
    verification_photo3 = Column(String)
    verification_photo4 = Column(String)
    graduation_year = Column(Integer)
    school_uuid = Column(UUID(as_uuid=True), ForeignKey(School.school_uuid), index=True)
    institutional_email = Column(String, nullable=True)
    flagged_for_review = Column(Boolean, nullable=True, default=False)
    profession_tree_uuid = Column(UUID(as_uuid=True), nullable=True)
    last_modified_by = Column(UUID(as_uuid=True), ForeignKey(User.user_uuid), index=True)
    source = Column(Enum(UserVerificationSource), nullable=True)
    school = relationship("School", uselist=False, foreign_keys=school_uuid, viewonly=True)
    verification_history = relationship("UserVerificationHistory", uselist=True, backref='verification')
    user = relationship("User",
                        uselist=False,
                        foreign_keys=user_uuid,
                        backref=backref('user_verification', uselist=False))

    @observes('flagged_for_review', 'last_modified_by', 'verification_status')
    def record_moderator_actions(self, flagged_for_review, last_modified_by, verification_status):
        """
        Listener that listens for moderator status changes and records them.
        :param flagged_for_review:
        :param last_modified_by:
        :param verification_status:
        :return:
        """
        event_list = []
        if last_modified_by:
            if flagged_for_review is True:
                h = UserVerificationHistory()
                h.verification_event_uuid = uuid.uuid4()
                h.verification_event_initiator = last_modified_by
                h.verification_status = self.verification_status.name
                h.verification_event_description = f"Verification flagged"
                event_list.append(h)
            elif flagged_for_review is False:
                h = UserVerificationHistory()
                h.verification_event_uuid = uuid.uuid4()
                h.verification_event_initiator = last_modified_by
                h.verification_status = self.verification_status.name
                h.verification_event_description = f"Verification un-flagged"
                event_list.append(h)

            if verification_status:
                h = UserVerificationHistory()
                h.verification_event_uuid = uuid.uuid4()
                h.verification_event_initiator = last_modified_by
                h.verification_status = self.verification_status.name
                h.verification_event_description = f"Verification status updated {verification_status.name}"
                event_list.append(h)
        else:
            if verification_status:
                h = UserVerificationHistory()
                h.verification_event_uuid = uuid.uuid4()
                h.verification_status = self.verification_status.name
                h.verification_event_description = f"Verification status updated {verification_status.name}"
                event_list.append(h)

            if flagged_for_review is True or flagged_for_review is False:
                h = UserVerificationHistory()
                h.verification_event_uuid = uuid.uuid4()
                h.verification_status = self.verification_status.name
                h.verification_event_description = f"Verification status updated, but the moderator was not recorded"
                event_list.append(h)
        if event_list:
            self.verification_history.extend(event_list)

    def as_dict(self):
        verification_photos = []
        if self.verification_photo:
            verification_photos.append(self.verification_photo)
        if self.verification_photo2:
            verification_photos.append(self.verification_photo2)
        if self.verification_photo3:
            verification_photos.append(self.verification_photo3)
        if self.verification_photo4:
            verification_photos.append(self.verification_photo4)

        return {
            'verificationUuid': str(self.verification_uuid),
            'userUuid': str(self.user_uuid),
            'verificationType': self.verification_type.name.lower(),
            'verificationStatus': self.verification_status.name.lower(),
            'submissionDate': self.created_at,
            'lastUpdatedDate': self.updated_at,
            'verificationPhoto': verification_photos,
            'graduationYear': self.graduation_year,
            'institutionalEmail': self.institutional_email,
            'schoolUuid': to_string_or_none(self.school_uuid),
            'flaggedForReview': self.flagged_for_review,
        }


class UserVerificationHistory(Base, HasCreateUpdateTime):
    __tablename__ = "h_verification_history"
    verification_event_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    verification_record_uuid = Column(UUID(as_uuid=True), ForeignKey(UserVerification.verification_uuid), index=True)
    verification_event_initiator = Column(UUID(as_uuid=True), ForeignKey(User.user_uuid), index=True)
    verification_status = Column(String)
    verification_event_description = Column(String)
    initiator = relationship("User", uselist=False, backref='verification_history_event')

    def as_dict(self):
        initiator_username = 'unknown'
        if hasattr(self, 'initiator'):
            if hasattr(self.initiator, 'username'):
                initiator_username = self.initiator.username

        return {
            'verificationEventInitiatorUsername': initiator_username,
            'verificationEventInitiator': str(self.verification_event_initiator),
            'verificationEventDescription': str(self.verification_event_description),
            'verificationEventUuid': str(self.verification_event_uuid),
            'verificationStatus': str(self.verification_status),
            'verificationEventCreatedAt': str(self.created_at)
        }


class ProfessionChangeRequest(Base, HasCreateUpdateTime):
    __tablename__ = "u_user_verification_change_request"
    verification_uuid = Column(UUID(as_uuid=True),
                               ForeignKey(UserVerification.verification_uuid,
                                          ondelete="CASCADE"),
                               primary_key=True)
    requested_profession = Column(UUID(as_uuid=True), nullable=False)
    request_resolved = Column(Boolean, default=False)
    archived_verification_uuid = Column(UUID(as_uuid=True), nullable=True)
    archived_verification = relationship("UserVerification",
                                         uselist=False,
                                         viewonly=True,
                                         foreign_keys=archived_verification_uuid,
                                         primaryjoin="and_(ProfessionChangeRequest.archived_verification_uuid=="
                                                     "UserVerification.verification_uuid,"
                                                     " UserVerification.verification_status=='ARCHIVED')",
                                         backref=backref("linked_change_request",
                                                         uselist=False))
    verification = relationship("UserVerification",
                                uselist=False,
                                backref=backref("profession_change_request",
                                                cascade="all, delete",
                                                passive_deletes=True,
                                                uselist=False))


class UserLicense(Base, HasCreateUpdateTime):
    __tablename__ = "u_user_license"
    verification_uuid = Column(UUID(as_uuid=True),
                               ForeignKey(UserVerification.verification_uuid, ondelete="CASCADE"),
                               primary_key=True)
    license_number = Column(String, index=True)
    license_country_uuid = Column(String)
    license_state_uuid = Column(String)
    user_uuid = Column(UUID(as_uuid=True), ForeignKey(User.user_uuid), index=True)
    verification = relationship("UserVerification", uselist=False, backref=backref("license",
                                                                                   cascade="all, delete",
                                                                                   passive_deletes=True,
                                                                                   uselist=False))

    def as_dict(self):
        return {
            'verificationUuid': str(self.verification_uuid),
            'userUuid': str(self.user_uuid),
            'licenseNumber': to_string_or_none(self.license_number),
            'licenseCountryUuid': to_string_or_none(self.license_country_uuid),
            'licenseStateUuid': to_string_or_none(self.license_state_uuid),
        }


class UserNPI(Base, HasCreateUpdateTime):
    __tablename__ = "u_user_npi"
    verification_uuid = Column(UUID(as_uuid=True),
                               ForeignKey(UserVerification.verification_uuid,
                                          ondelete="CASCADE"),
                               primary_key=True)
    verification = relationship("UserVerification", uselist=False, backref=backref("npi",
                                                                                   cascade="all, delete",
                                                                                   passive_deletes=True,
                                                                                   uselist=False))
    user_uuid = Column(UUID(as_uuid=True), ForeignKey(User.user_uuid), index=True, nullable=False)
    npi_number = Column(BigInteger, index=True, nullable=False)
    npi_enumeration_date = Column(Date, nullable=True)
    npi_last_update = Column(Date, nullable=True)
    npi_deactivation_date = Column(Date, nullable=True)
    npi_reactivation_date = Column(Date, nullable=True)
    npi_first_name = Column(String, nullable=True)
    npi_middle_name = Column(String, nullable=True)
    npi_last_name = Column(String, nullable=True)
    npi_gender = Column(String, nullable=True)
    npi_status = Column(String, nullable=True)
    npi_postal_code = Column(String, nullable=True)
    npi_address = Column(String, nullable=True)
    npi_city = Column(String, nullable=True)
    npi_country_uuid = Column(UUID(as_uuid=True), ForeignKey(Country.country_uuid))
    npi_state_uuid = Column(UUID(as_uuid=True), ForeignKey(Country.country_uuid))
    npi_duplicated_by = Column(ARRAY(UUID(as_uuid=True)), default=[], nullable=True)

    def as_dict(self):
        return {
            'userUuid': str(self.user_uuid),
            'verificationUuid': str(self.verification_uuid),
            'npiNumber': to_string_or_none(self.npi_number),
            'npiEnumerationDate': to_string_or_none(self.npi_enumeration_date),
            'npiLastUpdate': to_string_or_none(self.npi_last_update),
            'npiDeactivationDate': to_string_or_none(self.npi_deactivation_date),
            'npiReactivationDate': to_string_or_none(self.npi_reactivation_date),
            'npiFirstName': to_string_or_none(self.npi_first_name),
            'npiMiddleName': to_string_or_none(self.npi_middle_name),
            'npiLastName': to_string_or_none(self.npi_last_name),
            'npiGender': to_string_or_none(self.npi_gender),
            'npiStatus': to_string_or_none(self.npi_status),
            'npiPostalCode': to_string_or_none(self.npi_postal_code),
            'npiAddress': to_string_or_none(self.npi_address),
            'npiCity': to_string_or_none(self.npi_city),
            'npiCountryUuid': to_string_or_none(self.npi_country_uuid),
            'npiStateUuid': to_string_or_none(self.npi_state_uuid),
            'npiDuplicatedBy': [str(x) for x in self.npi_duplicated_by] if self.npi_duplicated_by else [],
        }


def to_string_or_none(value):
    return str(value) if value else None
