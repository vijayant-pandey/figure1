import uuid
import string
from random import choice

from pydantic import ValidationError
import pytest

from figure1.common.models.db import UserVerification, UserProfile, SpecialtyTreeV2
from figure1.common.types import VerificationType, VerificationStatus, UserVerificationUpdate, UserVerificationDocument
from figure1.common.helpers import UserManagement, \
    UserDocument, \
    get_user_verification_record, \
    create_profession_change_request, \
    VerificationManagement
from figure1.pro.verification.verify import verify_user, parse_npi_data


def _random_string(length):
    letters = string.ascii_letters
    return ''.join(choice(letters) for _ in range(length))


def _get_profession_change_specialty(profession_uuid, session):
    return session.query(SpecialtyTreeV2).filter(SpecialtyTreeV2.profession_uuid != profession_uuid).first().as_object()


@pytest.fixture
def valid_npi_model_v2(verification_user):
    """
    The NPI method requires only the number
    :return:
    """
    valid_npi = UserVerificationUpdate(method='npi',
                                       npi_number=1356609333,
                                       user_uid=verification_user.get('userUid'))
    assert isinstance(valid_npi, UserVerificationUpdate)
    yield valid_npi


@pytest.fixture
def valid_npi_model_v1(verification_user, test_school):
    """
    Returns an populated UserVerificationUpdate model
    :return:
    """

    valid_npi = UserVerificationUpdate(method='npi',
                                       npi_number=1356609333,
                                       graduation_year=2019,
                                       license_school_code=str(test_school.school_uuid),
                                       user_uid=verification_user.get('userUid'))
    assert isinstance(valid_npi, UserVerificationUpdate)
    yield valid_npi


@pytest.fixture
def valid_license_model_v1(verification_user, test_school, test_country):
    """
    The NPI method requires only the number
    :return:
    """
    valid_license = UserVerificationUpdate(method='license',
                                           license_number='1234',
                                           license_school_code=str(test_school.school_uuid),
                                           license_country_code=str(test_country.country_uuid),
                                           graduation_year=2019,
                                           user_uid=verification_user.get('userUid'))
    assert isinstance(valid_license, UserVerificationUpdate)
    yield valid_license


@pytest.fixture
def valid_institutional_email_v1(verification_user, test_country):
    valid_institutional_email = UserVerificationUpdate(method='institutional_email',
                                                       institutional_email='user@harvard.edu',
                                                       license_country_code=str(test_country.country_uuid),
                                                       user_uid=verification_user.get('userUid'))
    assert isinstance(valid_institutional_email, UserVerificationUpdate)
    yield valid_institutional_email


@pytest.fixture
def valid_institutional_email_v2(verification_user):
    valid_institutional_email = UserVerificationUpdate(method='institutional_email',
                                                       institutional_email='user2@harvard.edu',
                                                       user_uid=verification_user.get('userUid'))
    assert isinstance(valid_institutional_email, UserVerificationUpdate)
    yield valid_institutional_email


@pytest.fixture
def valid_single_photo(verification_user):
    valid_photo = UserVerificationUpdate(method='photo',
                                         photos=['https://picsum.photos/100'],
                                         user_uid=verification_user.get('userUid'))
    assert isinstance(valid_photo, UserVerificationUpdate)
    yield valid_photo


@pytest.fixture
def valid_multiple_photo(verification_user):
    valid_photo = UserVerificationUpdate(method='photo',
                                         photos=['https://picsum.photos/100',
                                                 'https://picsum.photos/200',
                                                 'https://picsum.photos/300',
                                                 'https://picsum.photos/400'],
                                         user_uid=verification_user.get('userUid'))
    assert isinstance(valid_photo, UserVerificationUpdate)
    yield valid_photo


@pytest.fixture(scope='function')
def verification_user(load_db):
    user = _random_string(16)
    mgmt = UserManagement(session=load_db, is_new_user=True, user_uuid=uuid.uuid4(), user_uid=f"test_{user}")
    tree = load_db.query(SpecialtyTreeV2).filter(SpecialtyTreeV2.profession_uuid.isnot(None)).first().as_object()
    mgmt.add_user(first_name=f"test_{user}_first_name",
                  last_name=f"test_{user}_last_name",
                  user_uuid=None,
                  email=f"test_{user}@figure1.com")
    mgmt.set_primary_specialty(specialty=tree.treeUuid, check_verify=False)
    mgmt.set_user_flags(flag='onboarding_completed', state=True)
    load_db.commit()
    yield UserDocument.get_full_profile(session=load_db, user_uuid=mgmt.user.user_uuid)
    mgmt.delete_user()


@pytest.fixture(scope='function')
def inst_email_verified_user(load_db, verification_user, valid_institutional_email_v2):
    session = load_db
    verify_user(update=valid_institutional_email_v2, session=session)
    v = session.query(UserVerification).filter(UserVerification.user_uuid == verification_user.get('userUuid')).one()
    assert v.verification_type is VerificationType.INSTITUTIONAL_EMAIL
    assert v.verification_status is VerificationStatus.PENDING_MANUAL_VERIFICATION
    v.verification_status = VerificationStatus.VERIFIED
    session.add(v)
    session.flush()
    yield verification_user.get('userUuid')
    session.refresh(v)
    for h in v.verification_history:
        session.delete(h)
    session.delete(v)
    session.flush()


@pytest.fixture(scope='function')
def npi_verified_user(load_db, verification_user, valid_npi_model_v2):
    session = load_db
    verify_user(update=valid_npi_model_v2, session=load_db)
    v = session.query(UserVerification).filter(UserVerification.user_uuid == verification_user.get('userUuid')).one()
    assert v.verification_type is VerificationType.NPI
    assert v.verification_status is VerificationStatus.VERIFIED
    assert v.npi.npi_number == valid_npi_model_v2.npi_number
    yield verification_user.get('userUuid')
    session.refresh(v)
    for h in v.verification_history:
        session.delete(h)
    session.delete(v)
    session.flush()


def test_npi_profession_change(npi_verified_user, load_db):
    user_uuid = npi_verified_user
    user_detail = UserDocument.user_detail(user_uuid=user_uuid, session=load_db)
    profession_uuid = user_detail.get('professionUuid')
    new_prof = _get_profession_change_specialty(profession_uuid=profession_uuid, session=load_db)
    assert user_detail.get('professionUuid') is not None
    load_db.commit()
    mgmt = UserManagement(user_uuid=user_uuid, session=load_db)
    mgmt.set_primary_specialty(specialty=new_prof.treeUuid)
    load_db.flush()
    v = get_user_verification_record(session=load_db, user_uuid=user_uuid)

    assert str(v.profession_change_request.requested_profession) == new_prof.treeUuid


def test_approve_inst_email_profession_change(inst_email_verified_user, load_db):
    user_uuid = inst_email_verified_user
    user_detail = UserDocument.user_detail(user_uuid=user_uuid, session=load_db)
    profession_uuid = user_detail.get('professionUuid')
    new_prof = _get_profession_change_specialty(profession_uuid=profession_uuid, session=load_db)
    assert user_detail.get('professionUuid') is not None
    mgmt = UserManagement(user_uuid=user_uuid, session=load_db)
    mgmt.set_primary_specialty(specialty=new_prof.treeUuid)
    load_db.flush()
    v = get_user_verification_record(session=load_db, user_uuid=user_uuid)
    assert v.profession_change_request.request_resolved is False
    assert str(v.profession_change_request.requested_profession) == new_prof.treeUuid
    user_detail_2 = UserDocument.user_detail(user_uuid=user_uuid, session=load_db)
    assert user_detail_2.get('isVerified') is True
    load_db.commit()
    v_mg = VerificationManagement(user_uuid=user_uuid, moderator_uuid=user_uuid, session=load_db)
    v_mg.approve_change_request()
    load_db.refresh(v)
    assert v.profession_change_request.request_resolved is True
    assert v.verification_status is VerificationStatus.VERIFIED


def test_reject_inst_email_profession_change(inst_email_verified_user, load_db):
    user_uuid = inst_email_verified_user
    user_detail = UserDocument.user_detail(user_uuid=user_uuid, session=load_db)
    profession_uuid = user_detail.get('professionUuid')
    new_prof = _get_profession_change_specialty(profession_uuid=profession_uuid, session=load_db)
    assert user_detail.get('professionUuid') is not None
    mgmt = UserManagement(user_uuid=user_uuid, session=load_db)
    mgmt.set_primary_specialty(specialty=new_prof.treeUuid)
    load_db.flush()
    v = get_user_verification_record(session=load_db, user_uuid=user_uuid)
    assert v.profession_change_request.request_resolved is False
    assert str(v.profession_change_request.requested_profession) == new_prof.treeUuid

    v_mg = VerificationManagement(user_uuid=user_uuid, moderator_uuid=user_uuid, session=load_db)
    v_mg.reject_change_request()

    v2 = get_user_verification_record(session=load_db, user_uuid=user_uuid)
    assert v2.profession_change_request is None
    assert v2.verification_status is VerificationStatus.VERIFIED
    user_detail_2 = UserDocument.user_detail(user_uuid=user_uuid, session=load_db)
    assert user_detail_2.get('isVerified') is True
    assert user_detail_2.get('professionUuid') == profession_uuid


_sample_npi_1 = {
    "result_count": 1,
    "results": [
        {
            "addresses": [
                {
                    "address_1": "5160 N FRESNO ST",
                    "address_2": "",
                    "address_purpose": "LOCATION",
                    "address_type": "DOM",
                    "city": "FRESNO",
                    "country_code": "US",
                    "country_name": "United States",
                    "postal_code": "937106825",
                    "state": "CA",
                    "telephone_number": "559-320-2667"
                }
            ],
            "basic": {
                "credential": "PA-C",
                "enumeration_date": "2006-02-27",
                "first_name": "THOMAS",
                "gender": "M",
                "last_name": "ADAIR",
                "last_updated": "2008-06-19",
                "middle_name": "GLENN",
                "name": "ADAIR THOMAS",
                "name_prefix": "MR.",
                "sole_proprietor": "NO",
                "status": "A"
            },
            "created_epoch": 1140998400,
            "enumeration_type": "NPI-1",
            "identifiers": [],
            "last_updated_epoch": 1213833600,
            "number": 1780650028,
            "other_names": [],
            "taxonomies": [
                {
                    "code": "363A00000X",
                    "desc": "Physician Assistant",
                    "license": "PA11232",
                    "primary": True,
                    "state": "CA"
                }
            ]
        }
    ]
}

_sample_npi_2 = {
    "result_count": 1,
    "results": [
        {
            "addresses": [
                {
                    "address_1": "5160 N FRESNO ST",
                    "address_2": "",
                    "address_purpose": "LOCATION",
                    "address_type": "DOM",
                    "city": "FRESNO",
                    "country_code": "US",
                    "country_name": "United States",
                    "postal_code": "937106825",
                    "state": "CA",
                    "telephone_number": "559-320-2667"
                }
            ],
            "basic": {
                "credential": "PA-C",
                "enumeration_date": "2006-02-27",
                "first_name": "THOMAS",
                "gender": "M",
                "last_name": "ADAIR",
                "last_updated": "2008-06-19",
                "middle_name": "GLENN",
                "name": "ADAIR THOMAS",
                "name_prefix": "MR.",
                "sole_proprietor": "NO",
                "status": "A"
            },
            "created_epoch": 1140998400,
            "enumeration_type": "NPI-2",
            "identifiers": [],
            "last_updated_epoch": 1213833600,
            "number": 1780650028,
            "other_names": [],
            "taxonomies": []
        }
    ]
}

_sample_npi_3 = {
    "result_count": 1
}


def test_npi_verification_v1(load_db, verification_user, test_school, valid_npi_model_v1):
    session = load_db
    verify_user(update=valid_npi_model_v1, session=load_db)
    v = session.query(UserVerification).filter(UserVerification.user_uuid == verification_user.get('userUuid')).one()
    assert v.verification_type is VerificationType.NPI
    assert v.verification_status is VerificationStatus.VERIFIED
    assert v.graduation_year == valid_npi_model_v1.graduation_year
    assert v.school_uuid == test_school.school_uuid
    assert v.npi.npi_number == valid_npi_model_v1.npi_number
    session.delete(v)
    session.flush()


def test_npi_verification_v2(load_db, verification_user, test_school, valid_npi_model_v2):
    session = load_db
    verify_user(update=valid_npi_model_v2, session=load_db)
    v = session.query(UserVerification).filter(UserVerification.user_uuid == verification_user.get('userUuid')).one()
    assert v.verification_type is VerificationType.NPI
    assert v.verification_status is VerificationStatus.VERIFIED
    assert v.npi.npi_number == valid_npi_model_v2.npi_number
    session.delete(v)
    session.flush()


def test_verification_license_v1(load_db, test_school, test_country, verification_user, valid_license_model_v1):
    session = load_db

    verify_user(update=valid_license_model_v1, session=session)
    v = session.query(UserVerification) \
        .filter(UserVerification.user_uuid == verification_user.get('userUuid')) \
        .one()

    assert v.verification_type is VerificationType.LICENSE
    assert v.verification_status is VerificationStatus.PENDING_MANUAL_VERIFICATION
    assert v.graduation_year == valid_license_model_v1.graduation_year
    assert v.school_uuid == test_school.school_uuid
    assert v.license.license_number == valid_license_model_v1.license_number
    p = session.query(UserProfile).get(verification_user.get('userUuid'))
    session.refresh(p)
    assert p.country_uuid == test_country.country_uuid
    session.delete(v)
    session.flush()


def test_verification_institutional_email_reg_v1(load_db,
                                                 verification_user,
                                                 test_country,
                                                 valid_institutional_email_v1):
    session = load_db
    verify_user(update=valid_institutional_email_v1, session=session)

    v = session.query(UserVerification).filter(UserVerification.user_uuid == verification_user.get('userUuid')).one()
    assert v.verification_type is VerificationType.INSTITUTIONAL_EMAIL
    assert v.verification_status is VerificationStatus.PENDING_MANUAL_VERIFICATION
    assert v.institutional_email == valid_institutional_email_v1.institutional_email
    p = session.query(UserProfile).get(verification_user.get('userUuid'))
    session.refresh(p)
    assert p.country_uuid == test_country.country_uuid
    user_detail = UserDocument.elasticsearch_user_detail(user_uuid=verification_user.get('userUuid'),
                                                         session=session).to_dict()
    assert user_detail['institutionalEmail']['email'] == valid_institutional_email_v1.institutional_email
    session.delete(v)
    session.flush()


def test_verification_institutional_email_reg_v2(load_db,
                                                 verification_user,
                                                 valid_institutional_email_v2):
    session = load_db
    verify_user(update=valid_institutional_email_v2, session=session)

    v = session.query(UserVerification).filter(UserVerification.user_uuid == verification_user.get('userUuid')).one()
    assert v.verification_type is VerificationType.INSTITUTIONAL_EMAIL
    assert v.verification_status is VerificationStatus.PENDING_MANUAL_VERIFICATION
    assert v.institutional_email == valid_institutional_email_v2.institutional_email
    session.delete(v)
    session.flush()


def test_verification_photo_multiple(load_db, verification_user, valid_multiple_photo):
    session = load_db
    verify_user(update=valid_multiple_photo, session=session)
    v = session.query(UserVerification).filter(UserVerification.user_uuid == verification_user.get('userUuid')).one()
    assert v.verification_type is VerificationType.PHOTO
    assert v.verification_status is VerificationStatus.PENDING_MANUAL_VERIFICATION
    assert v.verification_photo == 'https://picsum.photos/100'
    assert v.verification_photo2 == 'https://picsum.photos/200'
    assert v.verification_photo3 == 'https://picsum.photos/300'
    assert v.verification_photo4 == 'https://picsum.photos/400'

    session.delete(v)
    session.flush()


def test_verification_photo_single(load_db, verification_user, valid_single_photo):
    session = load_db

    verify_user(update=valid_single_photo, session=session)
    v = session.query(UserVerification).filter(UserVerification.user_uuid == verification_user.get('userUuid')).one()
    assert v.verification_type is VerificationType.PHOTO
    assert v.verification_status is VerificationStatus.PENDING_MANUAL_VERIFICATION
    assert v.verification_photo == 'https://picsum.photos/100'
    assert v.verification_photo2 is None
    assert v.verification_photo3 is None
    assert v.verification_photo4 is None
    session.delete(v)
    session.flush()


def test_parse_npi():
    res = parse_npi_data(data=_sample_npi_1)

    assert res['resultCount'] == 1
    assert res['results'][0]['firstName'] == 'Thomas'
    assert res['results'][0]['lastName'] == 'Adair'
    assert res['results'][0]['npiNumber'] == 1780650028

    # Test rejecting organization NPI Number

    res1 = parse_npi_data(data=_sample_npi_2)

    assert res1['resultCount'] == 0
    assert res1['results'] == []

    # Missing 'results' in json
    with pytest.raises(ValidationError):
        parse_npi_data(data=_sample_npi_3)
