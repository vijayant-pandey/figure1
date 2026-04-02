import logging
import uuid
from sqlalchemy import func
from sqlalchemy.orm import Session

from figure1.common.models.db import UserVerification, UserNPI, UserLicense, User, Country, ProfessionChangeRequest
from figure1.common.helpers import UserManagement, get_user_verification_record
from figure1.common.types import VerificationStatus
from figure1.common.types import VerificationType
from figure1.common.types import UpdateUserModel
from figure1.common.npi.api import NPIResponseItem
from figure1.exceptions import InvalidVerificationType, \
    InvalidVerificationStatus, \
    VerificationNotFound

logger = logging.getLogger("figure1.verification.npi")


def update_verification_request(session,
                                user_uuid=None,
                                verification_uuid=None,
                                verification_type=None,
                                verification_status=VerificationStatus.PENDING_MANUAL_VERIFICATION,
                                verification_photos=None,
                                graduation_year=None,
                                school_uuid=None,
                                institutional_email=None):
    if not isinstance(verification_type, VerificationType):
        raise InvalidVerificationType

    if not isinstance(verification_status, VerificationStatus):
        raise InvalidVerificationStatus
    logger.error("Update using session %s", session)
    user_verification_entry = get_user_verification_record(user_uuid=user_uuid, session=session)
    entry = None

    if user_verification_entry is None:
        logger.error("No user verification entry found for user %s, creating a new one", user_uuid)
        entry = UserVerification()
        if verification_uuid:
            entry.verification_uuid = verification_uuid
        else:
            entry.verification_uuid = uuid.uuid4()

        entry.user_uuid = user_uuid

    elif isinstance(user_verification_entry, UserVerification):
        entry = user_verification_entry
        if verification_uuid:
            entry.verification_uuid = verification_uuid

    else:
        logger.error("Condition outside of bounds in update verification request")
        raise ValueError("Unexpected condition in verification request")
    if entry.verification_status is None:
        entry.verification_status = verification_status
    entry.verification_type = verification_type

    if graduation_year:
        entry.graduation_year = graduation_year
    if school_uuid:
        entry.school_uuid = school_uuid
    if verification_type == VerificationType.PHOTO:
        entry.verification_photo = verification_photos.pop(0) if verification_photos else None
        entry.verification_photo2 = verification_photos.pop(0) if verification_photos else None
        entry.verification_photo3 = verification_photos.pop(0) if verification_photos else None
        entry.verification_photo4 = verification_photos.pop(0) if verification_photos else None

    if verification_type is VerificationType.INSTITUTIONAL_EMAIL:
        entry.institutional_email = institutional_email

    logger.error("Added entry for user %s", user_uuid)
    v_entry = session.merge(entry)
    logger.error("Created entry with verification type %s, and status %s, and uuid %s",
                 v_entry.verification_type,
                 v_entry.verification_status,
                 v_entry.verification_uuid)
    return v_entry


def set_user_location(user_uuid, session, country_uuid, state_uuid):
    user_mgmt = UserManagement(session=session, user_uuid=user_uuid)
    user_mgmt.update_user_profile(profile_update=UpdateUserModel(country_uuid=country_uuid, state_uuid=state_uuid))
    session.flush()


def verify_user(user_uuid, verification_status, session, verification_uuid=None):
    """
    Passing in review required as the verification status sets the flagged_for_review flag to true and sets
    the verification status to verified.
    :param user_uuid:
    :param verification_status:
    :param session:
    :return:
    """
    if not isinstance(verification_status, VerificationStatus):
        raise InvalidVerificationStatus

    if not verification_uuid:
        user_verification_record = get_user_verification_record(user_uuid=user_uuid, session=session)
    else:
        user_verification_record = session.query(UserVerification).get(verification_uuid)

    if not user_verification_record:
        raise ValueError("No verification record found")

    if verification_status == VerificationStatus.REVIEW_REQUIRED:
        if user_verification_record.verification_status is VerificationStatus.CHANGE_REQUESTED:
            logger.info("User has requested change - set to change requested")
        else:
            user_verification_record.flagged_for_review = True
            user_verification_record.verification_status = VerificationStatus.VERIFIED

    elif user_verification_record.verification_status is VerificationStatus.CHANGE_REQUESTED:
        logger.info("User should not change from change_requested through this endpoint")

    elif user_verification_record.verification_status == VerificationStatus.VERIFIED:
        logger.info("Do not unverify user through user endpoint")
    else:
        user_verification_record.verification_status = verification_status

    return session.merge(user_verification_record)


def check_and_flag_duplicate_npi(npi, user_uuid, session):
    set_duplicates = []
    for dup in session.query(UserNPI.user_uuid) \
            .filter(UserNPI.npi_number == npi, UserNPI.user_uuid != user_uuid).all():
        set_duplicates.append(dup[0])
    session.query(UserNPI).filter(UserNPI.user_uuid == user_uuid).update({'npi_duplicated_by': set_duplicates})
    return set_duplicates


def add_license_data(user_uuid,
                     license_number,
                     session,
                     country_uuid=None,
                     state_uuid=None,
                     verification_uuid=None):
    if verification_uuid:
        u = UserLicense()
        u.verification_uuid = verification_uuid
        u.user_uuid = user_uuid
        u.license_number = license_number
        u.license_country_uuid = country_uuid
        u.license_state_uuid = state_uuid
    else:
        logger.error("Verification uuid required")
        return
    set_user_location(user_uuid=user_uuid, state_uuid=state_uuid, country_uuid=country_uuid, session=session)
    return session.merge(u)


def add_npi_data(user_uuid, npi_number, session=None, verification_uuid=None):
    """
    At this point, the npi number is validated, so we set the user to verified.
    """
    logger.error("npi using session %s and user %s", session, user_uuid)

    npi = UserNPI()
    npi.user_uuid = user_uuid
    npi.verification_uuid = verification_uuid
    npi.npi_number = npi_number
    updated = session.merge(npi)
    check_and_flag_duplicate_npi(npi=npi_number, user_uuid=user_uuid, session=session)
    verify_user(user_uuid=user_uuid,
                verification_status=VerificationStatus.REVIEW_REQUIRED,
                session=session,
                verification_uuid=verification_uuid)
    session.flush()
    return updated


def add_npi_data_from_json(npi_data: NPIResponseItem,
                           user_uuid: str,
                           npi_number: str,
                           session: Session):
    user_verification_record = get_user_verification_record(user_uuid=user_uuid, session=session)
    if not user_verification_record:
        raise InvalidVerificationStatus
    if user_verification_record.verification_type is not VerificationType.NPI:
        logger.error("user (%s) verification type is %s", user_uuid, user_verification_record.verification_type)
        raise InvalidVerificationType

    if not user_verification_record.npi:
        npi = UserNPI()
        npi.npi_uuid = uuid.uuid4()
        npi.npi_number = npi_number
        npi.user_uuid = user_uuid
        npi.verification_uuid = user_verification_record.verification_uuid
    else:
        npi = user_verification_record.npi
    if npi_data.basic:
        npi.npi_enumeration_date = npi_data.basic.enumeration_date
        npi.npi_last_update = npi_data.basic.last_updated
        npi.npi_deactivation_date = npi_data.basic.deactivation_date
        npi.npi_reactivation_date = npi_data.basic.reactivation_date
        npi.npi_first_name = npi_data.basic.first_name
        npi.npi_middle_name = npi_data.basic.middle_name
        npi.npi_last_name = npi_data.basic.last_name
        npi.npi_gender = npi_data.basic.gender
    if len(npi_data.addresses) > 1:
        npi.npi_postal_code = npi_data.addresses[0].postal_code
        npi.npi_address = npi_data.addresses[0].address_1 + npi_data.addresses[0].address_2
        npi.npi_city = npi_data.addresses[0].city
        country_code = npi_data.addresses[0].country_code
        npi.npi_country_uuid = get_country_uuid_from_code(country_code, session=session)
        state_code = npi_data.addresses[0].state
        npi.npi_state_uuid = get_subdivision_uuid_from_code(country_uuid=npi.npi_country_uuid,
                                                            code=state_code,
                                                            session=session)
    session.add(npi)
    session.flush()


def get_country_uuid_from_code(code, session):
    if not code:
        return None

    c = session.query(Country). \
        filter(Country.code == code,
               func.nlevel(Country.path) == 1). \
        one_or_none()

    return c.country_uuid if c else None


def get_subdivision_uuid_from_code(country_uuid, code, session):
    if not code or not country_uuid:
        return None

    country = session.query(Country) \
        .filter(Country.country_uuid == country_uuid).one()

    s = session.query(Country). \
        filter(Country.path.descendant_of(country.path),
               Country.code == code,
               func.nlevel(Country.path) != 1). \
        one_or_none()

    return s.country_uuid if s else None
