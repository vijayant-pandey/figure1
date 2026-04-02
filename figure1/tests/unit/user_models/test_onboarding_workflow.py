import string
import uuid
from random import choice
from typing import Optional

import pytest
from sqlalchemy.orm import Session

from figure1.common.helpers import UserManagement, OnboardingWorkflow
from figure1.common.models.db import Country, UserVerification, SpecialtyTreeV2, SpecialtyV2, ProfessionV2
from figure1.common.types import OnboardingState, VerificationType, VerificationStatus, USAInformationState, \
    InformationState, GradDateState


def _random_string(length):
    letters = string.ascii_letters
    return ''.join(choice(letters) for _ in range(length))


def _all_onboarding_states():
    yield None
    for s in OnboardingState:
        yield s


def _get_country(code, session):
    c = session.query(Country).filter(Country.alpha_3 == code).one_or_none()
    if c:
        return c
    c = Country.create_or_update(name="Test country",
                                 code=code,
                                 type="Country",
                                 path_str=code,
                                 alpha_3=code,
                                 session=session,
                                 skip_commit=True)
    session.flush()
    return c


def _setup_user(is_verified: bool,
                has_specialty: bool,
                name: Optional[str],
                username: Optional[str],
                country_code: Optional[str],
                current_state: Optional[OnboardingState],
                session: Session,
                specialty_uuid: Optional[str] = None,
                has_profession: Optional[bool] = False,
                grad_date: Optional[str] = None,
                is_student=False,
                is_legacy=False):
    uid = _random_string(16)
    mgmt = UserManagement(session=session, is_new_user=True, user_uid=uid)
    mgmt.add_user(first_name=name,
                  last_name=name,
                  user_uuid=None,
                  email=f"test+{uid}@figure1.com",
                  legacy=is_legacy)
    if country_code:
        c = _get_country(code=country_code, session=session)
        mgmt.user.user_profile.country_uuid = c.country_uuid
    if is_verified:
        v = UserVerification()
        v.verification_uuid = uuid.uuid4()
        v.user_uuid = mgmt.user.user_uuid
        v.verification_type = VerificationType.PHOTO
        v.verification_status = VerificationStatus.VERIFIED
        session.add(v)
    if has_specialty:
        if specialty_uuid:
            mgmt.set_primary_specialty(specialty_uuid)
        else:
            s = session.query(SpecialtyTreeV2).filter(SpecialtyTreeV2.specialty_v2_uuid.isnot(None)).first()
            mgmt.set_primary_specialty(s.specialty_uuid)
    if has_profession or is_student:
        if is_student:
            p = session.query(ProfessionV2).filter(ProfessionV2.profession_category == 'Other Student').first()
            s = session.query(SpecialtyTreeV2).filter(SpecialtyTreeV2.profession_uuid == p.specialty_uuid).first()
        else:
            s = session.query(SpecialtyTreeV2).filter(SpecialtyTreeV2.specialty_v2_uuid.isnot(None)).first()

        mgmt.set_primary_specialty(specialty=s.specialty_uuid, check_verify=False)
    if grad_date:
        mgmt.user.user_profile.graduation_date = grad_date

    mgmt.set_onboarding_state(onboarding_state=current_state)
    mgmt.update_username(username=username)
    return mgmt.user


@pytest.mark.parametrize('current_state', _all_onboarding_states())
def test_user_missing_all(current_state: Optional[OnboardingState],
                          load_db: Session):
    expected_state = OnboardingState.COUNTRY
    session = load_db
    u = _setup_user(is_verified=False,
                    has_specialty=False,
                    name=None,
                    username=None,
                    country_code=None,
                    current_state=current_state,
                    session=session)

    OnboardingWorkflow.update_onboarding_state(user_uuid=u.user_uuid, session=session)
    assert u.user_state.onboarding_state == expected_state


@pytest.mark.parametrize('current_state', _all_onboarding_states())
def test_user_missing_name_non_us(current_state: Optional[OnboardingState], load_db: Session):
    expected_state = OnboardingState.INFORMATION
    session = load_db
    u = _setup_user(is_verified=False,
                    has_specialty=True,
                    name=None,
                    username=None,
                    country_code='CAN',
                    current_state=current_state,
                    session=session)

    OnboardingWorkflow.update_onboarding_state(user_uuid=u.user_uuid, session=session)
    assert u.user_state.onboarding_state == expected_state


@pytest.mark.parametrize('current_state', _all_onboarding_states())
def test_user_missing_specialty_non_us(current_state: Optional[OnboardingState], load_db: Session):
    expected_state = OnboardingState.INFORMATION
    session = load_db
    u = _setup_user(is_verified=False,
                    has_specialty=False,
                    name=_random_string(length=16),
                    username=None,
                    country_code='CAN',
                    current_state=current_state,
                    session=session)

    OnboardingWorkflow.update_onboarding_state(user_uuid=u.user_uuid, session=session)
    assert u.user_state.onboarding_state == expected_state


@pytest.mark.parametrize('current_state', _all_onboarding_states())
def test_user_profession_only_non_us(current_state: Optional[OnboardingState], load_db: Session):
    expected_state = OnboardingState.INFORMATION
    session = load_db
    s = session.query(SpecialtyTreeV2).filter(SpecialtyTreeV2.specialty_v2_uuid.is_(None)).first()
    u = _setup_user(is_verified=False,
                    has_specialty=True,
                    specialty_uuid=s.specialty_uuid,
                    name=_random_string(length=16),
                    username=None,
                    country_code='CAN',
                    current_state=current_state,
                    session=session)

    OnboardingWorkflow.update_onboarding_state(user_uuid=u.user_uuid, session=session)
    assert u.user_state.onboarding_state == expected_state


@pytest.mark.parametrize('current_state', _all_onboarding_states())
def test_user_missing_name_us(current_state: Optional[OnboardingState], load_db: Session):
    expected_state = OnboardingState.USA_INFORMATION
    session = load_db
    u = _setup_user(is_verified=False,
                    has_specialty=True,
                    name=None,
                    username=None,
                    country_code='USA',
                    current_state=current_state,
                    session=session)

    OnboardingWorkflow.update_onboarding_state(user_uuid=u.user_uuid, session=session)
    assert u.user_state.onboarding_state == expected_state


@pytest.mark.parametrize('current_state', _all_onboarding_states())
def test_user_missing_specialty_us(current_state: Optional[OnboardingState], load_db: Session):
    expected_state = OnboardingState.USA_INFORMATION
    session = load_db
    u = _setup_user(is_verified=False,
                    has_specialty=False,
                    name=_random_string(length=16),
                    username=None,
                    country_code='USA',
                    current_state=current_state,
                    session=session)

    OnboardingWorkflow.update_onboarding_state(user_uuid=u.user_uuid, session=session)
    assert u.user_state.onboarding_state == expected_state


@pytest.mark.parametrize('current_state', _all_onboarding_states())
def test_user_profession_only_us(current_state: Optional[OnboardingState], load_db: Session):
    expected_state = OnboardingState.USA_INFORMATION
    session = load_db
    s = session.query(SpecialtyTreeV2).filter(SpecialtyTreeV2.specialty_v2_uuid.is_(None)).first()
    u = _setup_user(is_verified=False,
                    has_specialty=True,
                    specialty_uuid=s.specialty_uuid,
                    name=_random_string(length=16),
                    username=None,
                    country_code='USA',
                    current_state=current_state,
                    session=session)

    OnboardingWorkflow.update_onboarding_state(user_uuid=u.user_uuid, session=session)
    assert u.user_state.onboarding_state == expected_state


@pytest.mark.parametrize('current_state', _all_onboarding_states())
def test_user_missing_verification(current_state: Optional[OnboardingState], load_db: Session):
    expected_state = OnboardingState.VERIFICATION
    session = load_db
    u = _setup_user(is_verified=False,
                    has_specialty=True,
                    name=_random_string(length=16),
                    username=None,
                    country_code='CAN',
                    current_state=current_state,
                    session=session)

    OnboardingWorkflow.update_onboarding_state(user_uuid=u.user_uuid, session=session)
    assert u.user_state.onboarding_state == expected_state


@pytest.mark.parametrize('current_state', _all_onboarding_states())
def test_user_missing_username(current_state: Optional[OnboardingState], load_db: Session):
    expected_state = OnboardingState.USERNAME
    session = load_db
    u = _setup_user(is_verified=True,
                    has_specialty=True,
                    name=_random_string(length=16),
                    username=None,
                    country_code='CAN',
                    current_state=current_state,
                    session=session,
                    has_profession=True,
                    grad_date='2055-12-01')

    OnboardingWorkflow.update_onboarding_state(user_uuid=u.user_uuid, session=session)
    assert u.user_state.onboarding_state == expected_state


@pytest.mark.parametrize('current_state', _all_onboarding_states())
def test_user_completed(current_state: Optional[OnboardingState], load_db: Session):
    expected_state = OnboardingState.COMPLETED
    session = load_db
    u = _setup_user(is_verified=True,
                    has_specialty=True,
                    name=_random_string(length=16),
                    username=_random_string(length=16),
                    country_code='CAN',
                    current_state=current_state,
                    session=session,
                    has_profession=True,
                    grad_date='2055-12-01')

    OnboardingWorkflow.update_onboarding_state(user_uuid=u.user_uuid, session=session)
    assert u.user_state.onboarding_state == expected_state


def test_usa_information_state(load_db: Session):
    session = load_db

    # Valid name, primarySpecialty returns True
    u = _setup_user(is_verified=True,
                    has_specialty=True,
                    name=_random_string(length=16),
                    username=_random_string(length=16),
                    country_code='USA',
                    current_state=None,
                    session=session)
    assert USAInformationState.has_required_data(user=u)

    # Missing name returns False
    u2 = _setup_user(is_verified=True,
                     has_specialty=True,
                     name=None,
                     username=_random_string(length=16),
                     country_code='USA',
                     current_state=None,
                     session=session)
    assert not USAInformationState.has_required_data(user=u2)

    # Missing primarySpecialty returns False
    u3 = _setup_user(is_verified=True,
                     has_specialty=False,
                     name=_random_string(length=16),
                     username=_random_string(length=16),
                     country_code='USA',
                     current_state=None,
                     session=session)
    assert not USAInformationState.has_required_data(user=u3)

    # primarySpecialty is profession not specialty returns False
    t = session.query(SpecialtyTreeV2).filter(SpecialtyTreeV2.specialty_v2_uuid.is_(None)).first()
    u3 = _setup_user(is_verified=True,
                     has_specialty=True,
                     specialty_uuid=t.specialty_uuid,
                     name=_random_string(length=16),
                     username=_random_string(length=16),
                     country_code='USA',
                     current_state=None,
                     session=session)
    assert not USAInformationState.has_required_data(user=u3)

    # primarySpecialty is 'Other Specialist' returns false
    s = session.query(SpecialtyV2).filter(SpecialtyV2.label == 'otherspecialist').first()
    t = session.query(SpecialtyTreeV2).filter(SpecialtyTreeV2.specialty_v2_uuid == s.specialty_uuid).first()
    u3 = _setup_user(is_verified=True,
                     has_specialty=True,
                     specialty_uuid=t.specialty_uuid,
                     name=_random_string(length=16),
                     username=_random_string(length=16),
                     country_code='USA',
                     current_state=None,
                     session=session)
    assert not USAInformationState.has_required_data(user=u3)

    # primarySpecialty with professionCategory 'Other Student' returns True
    p = session.query(ProfessionV2).filter(ProfessionV2.profession_category == 'Other Student').first()
    t = session.query(SpecialtyTreeV2).filter(SpecialtyTreeV2.profession_uuid == p.specialty_uuid).first()
    u3 = _setup_user(is_verified=True,
                     has_specialty=True,
                     specialty_uuid=t.specialty_uuid,
                     name=_random_string(length=16),
                     username=_random_string(length=16),
                     country_code='USA',
                     current_state=None,
                     session=session)
    assert USAInformationState.has_required_data(user=u3)

    # primarySpecialty with professionCategory 'Other HCP' returns True
    p = session.query(ProfessionV2).filter(ProfessionV2.profession_category == 'Other HCP').first()
    t = session.query(SpecialtyTreeV2).filter(SpecialtyTreeV2.profession_uuid == p.specialty_uuid).first()
    u3 = _setup_user(is_verified=True,
                     has_specialty=True,
                     specialty_uuid=t.specialty_uuid,
                     name=_random_string(length=16),
                     username=_random_string(length=16),
                     country_code='USA',
                     current_state=None,
                     session=session)
    assert USAInformationState.has_required_data(user=u3)


def test_information_state(load_db: Session):
    session = load_db

    # Valid name, primarySpecialty returns True
    u = _setup_user(is_verified=True,
                    has_specialty=True,
                    name=_random_string(length=16),
                    username=_random_string(length=16),
                    country_code='CAN',
                    current_state=None,
                    session=session)
    assert InformationState.has_required_data(user=u)

    # Missing name returns False
    u2 = _setup_user(is_verified=True,
                     has_specialty=True,
                     name=None,
                     username=_random_string(length=16),
                     country_code='CAN',
                     current_state=None,
                     session=session)
    assert not InformationState.has_required_data(user=u2)

    # Missing primarySpecialty returns False
    u3 = _setup_user(is_verified=True,
                     has_specialty=False,
                     name=_random_string(length=16),
                     username=_random_string(length=16),
                     country_code='CAN',
                     current_state=None,
                     session=session)
    assert not InformationState.has_required_data(user=u3)

    # primarySpecialty is profession not specialty returns False
    t = session.query(SpecialtyTreeV2).filter(SpecialtyTreeV2.specialty_v2_uuid.is_(None)).first()
    u3 = _setup_user(is_verified=True,
                     has_specialty=True,
                     specialty_uuid=t.specialty_uuid,
                     name=_random_string(length=16),
                     username=_random_string(length=16),
                     country_code='CAN',
                     current_state=None,
                     session=session)
    assert not InformationState.has_required_data(user=u3)

    # primarySpecialty is 'Other Specialist' returns false
    s = session.query(SpecialtyV2).filter(SpecialtyV2.label == 'otherspecialist').first()
    t = session.query(SpecialtyTreeV2).filter(SpecialtyTreeV2.specialty_v2_uuid == s.specialty_uuid,
                                              SpecialtyTreeV2.subspecialty_uuid.is_(None)).first()
    u3 = _setup_user(is_verified=True,
                     has_specialty=True,
                     specialty_uuid=t.specialty_uuid,
                     name=_random_string(length=16),
                     username=_random_string(length=16),
                     country_code='CAN',
                     current_state=None,
                     session=session)
    assert not InformationState.has_required_data(user=u3)

    # primarySpecialty is subspecialty of 'Other Specialist' returns True
    s = session.query(SpecialtyV2).filter(SpecialtyV2.label == 'otherspecialist').first()
    t = session.query(SpecialtyTreeV2).filter(SpecialtyTreeV2.specialty_v2_uuid == s.specialty_uuid,
                                              SpecialtyTreeV2.subspecialty_uuid.isnot(None)).first()
    u3 = _setup_user(is_verified=True,
                     has_specialty=True,
                     specialty_uuid=t.specialty_uuid,
                     name=_random_string(length=16),
                     username=_random_string(length=16),
                     country_code='CAN',
                     current_state=None,
                     session=session)
    assert InformationState.has_required_data(user=u3)

    # primarySpecialty with professionCategory 'Other Student' returns True
    p = session.query(ProfessionV2).filter(ProfessionV2.profession_category == 'Other Student').first()
    t = session.query(SpecialtyTreeV2).filter(SpecialtyTreeV2.profession_uuid == p.specialty_uuid).first()
    u3 = _setup_user(is_verified=True,
                     has_specialty=True,
                     specialty_uuid=t.specialty_uuid,
                     name=_random_string(length=16),
                     username=_random_string(length=16),
                     country_code='CAN',
                     current_state=None,
                     session=session)
    assert InformationState.has_required_data(user=u3)

    # primarySpecialty with professionCategory 'Other HCP' returns True
    p = session.query(ProfessionV2).filter(ProfessionV2.profession_category == 'Other HCP').first()
    t = session.query(SpecialtyTreeV2).filter(SpecialtyTreeV2.profession_uuid == p.specialty_uuid).first()
    u3 = _setup_user(is_verified=True,
                     has_specialty=True,
                     specialty_uuid=t.specialty_uuid,
                     name=_random_string(length=16),
                     username=_random_string(length=16),
                     country_code='CAN',
                     current_state=None,
                     session=session)
    assert InformationState.has_required_data(user=u3)


def test_grad_date_state(load_db: Session):
    session = load_db

    p = session.query(ProfessionV2).filter(ProfessionV2.profession_category == 'Other HCP').first()
    t = session.query(SpecialtyTreeV2).filter(SpecialtyTreeV2.profession_uuid == p.specialty_uuid).first()

    # Missing grad_date, not student, return True
    user1 = _setup_user(is_verified=True,
                        has_specialty=True,
                        specialty_uuid=t.specialty_uuid,
                        name=_random_string(length=16),
                        username=_random_string(length=16),
                        country_code='CAN',
                        current_state=None,
                        session=session,
                        has_profession=True)

    assert GradDateState.has_required_data(user=user1)

    # Missing grad_date, student, return False
    user2 = _setup_user(is_verified=True,
                        has_specialty=True,
                        specialty_uuid=t.specialty_uuid,
                        name=_random_string(length=16),
                        username=_random_string(length=16),
                        country_code='CAN',
                        current_state=None,
                        session=session,
                        has_profession=True,
                        is_student=True)

    assert not GradDateState.has_required_data(user=user2)

    # Valid grad_date, student, not legacy user; return True
    user3 = _setup_user(is_verified=True,
                        has_specialty=True,
                        specialty_uuid=t.specialty_uuid,
                        name=_random_string(length=16),
                        username=_random_string(length=16),
                        country_code='CAN',
                        current_state=None,
                        session=session,
                        has_profession=True,
                        grad_date='2034-12-01',
                        is_student=True)
    assert GradDateState.has_required_data(user=user3)

    # Valid grad_date, not student; return True
    user4 = _setup_user(is_verified=True,
                        has_specialty=True,
                        specialty_uuid=t.specialty_uuid,
                        name=_random_string(length=16),
                        username=_random_string(length=16),
                        country_code='CAN',
                        current_state=None,
                        session=session,
                        has_profession=True,
                        grad_date='2034-12-01')
    assert GradDateState.has_required_data(user=user4)
