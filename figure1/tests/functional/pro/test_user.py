import string
import time
import uuid
from random import choice

import pytest

from figure1.common.helpers import UserDocument
from figure1.common.helpers import UserManagement
from figure1.common.helpers import GroupManagement
from figure1.common.models.db import User
from figure1.common.models.db import UserFollow
from figure1.common.models.db import UserVerification
from figure1.common.models.db import UserProfile
from figure1.common.models.db import SpecialtyTreeV2
from figure1.common.models.db import AnonymousUser
from figure1.common.models.db import CaseProgress
from figure1.common.models.db import GroupMemberFilter
from figure1.common.models.db import UserNPI
from figure1.common.models.db import ProfessionV2
from figure1.common.models.db import UserSpecialtyTreeV2
from figure1.common.models.db import GroupMember
from figure1.common.types import VerificationType
from figure1.common.types import OnboardingState
from figure1.common.types import CaseType
from figure1.common.types import CaseState
from figure1.common.types import VerificationStatus
from figure1.common.types import UpdateUserModel
from figure1.common.types.user_tracking import MixpanelUserData
from figure1.common.iterable.domain import get_user_for_bulk_update
from figure1.common.iterable.domain import generate_iterable_user_object
from figure1.common.iterable.domain import get_user_comm_preference_for_bulk_update
from figure1.common.iterable import IterableAPI
from figure1.pro.users.domain import update_user_internal
from figure1.pro.users.domain import update_user_avatar_internal
from figure1.events import UserEvents
from figure1.tests.functional.pro.test_cme import _create_case


def _random_string(length):
    letters = string.ascii_letters
    return ''.join(choice(letters) for _ in range(length))


def _get_fs_doc(documents, collections, fs):
    count = 0
    for d, c in zip(documents, collections):
        fs = fs.collection(c).document(d)
    doc = fs.get()
    while not doc.exists:
        doc = fs.get()
        count += 1
        if count >= 10:
            raise TimeoutError
        time.sleep(1 * count)
    return doc.to_dict()


def _create_user(session):
    user = _random_string(16)
    mgmt = UserManagement(user_uid=f'test_{user}', session=session, is_new_user=True)
    mgmt.add_user(first_name=f'test_{user}_first_name',
                  last_name=f'test_{user}_last_name',
                  email=f'test_{user}@figure1.com',
                  user_uuid=None,
                  legacy=False)
    session.flush()
    return mgmt.user


def _create_group_member_filter(session,
                                user_uuid=None,
                                group_uuid=None,
                                email=None,
                                first_name=None,
                                last_name=None,
                                npi_number=None,
                                tree_uuid=None,
                                country_uuid=None):
    group_member_filter = GroupMemberFilter()
    group_member_filter.group_filter_uuid = uuid.uuid4()
    if user_uuid:
        group_member_filter.user_uuid = user_uuid
    if group_uuid:
        group_member_filter.group_uuid = group_uuid
    if email:
        group_member_filter.user_email = email
    if first_name:
        group_member_filter.user_first_name = first_name
    if last_name:
        group_member_filter.user_last_name = last_name
    if npi_number:
        group_member_filter.user_npi = npi_number
    if tree_uuid:
        group_member_filter.tree_uuid = tree_uuid
    if country_uuid:
        group_member_filter.country_uuid = country_uuid

    session.add(group_member_filter)
    session.commit()

    return group_member_filter


def test_create_user_validation(client, headers):
    user = _random_string(16)
    # Missing user_uid returns 400
    response = client.post('/pro/v1/user/create',
                           headers=headers,
                           json={
                               'first_name': f"test_{user}_first_name",
                               'last_name': f"test_{user}_last_name",
                               'email': f"test_{user}@figure1.com",
                           })
    assert response.status_code == 400

    # Missing email returns 400
    response = client.post('/pro/v1/user/create', headers=headers, json={
        'user_uid': f"test_{user}",
        'first_name': f"test_{user}_first_name",
        'last_name': f"test_{user}_last_name",
    })
    assert response.status_code == 400


def test_create_user_with_spaces(client, headers, load_db):
    first_name_with_spaces = " jenna "
    last_name_with_spaces = " waltz "
    user = _random_string(16)

    session = load_db
    response = client.post('/pro/v1/user/create', headers=headers, json={
        'user_uid': f"test_{user}",
        'first_name': first_name_with_spaces,
        'last_name': last_name_with_spaces,
        'email': f"test_{user}@figure1.com",
    })
    assert response.status_code == 200

    u = User.get_user_by_uid_as_dict(f"test_{user}", session=session)
    assert u.get('firstName') == first_name_with_spaces.strip()
    assert u.get('lastName') == last_name_with_spaces.strip()


def test_create_user(client, headers, load_db, test_country, test_campaign, create_group, test_user):
    user1 = _random_string(16)
    user2 = _random_string(16)
    user3 = _random_string(16)
    user4 = _random_string(16)
    user5 = _random_string(16)
    session = load_db
    group_uuid = create_group.groupUuid
    # Creating a new user returns 200
    response = client.post('/pro/v1/user/create', headers=headers, json={
        'user_uid': f"test_{user1}",
        'first_name': f"test_{user1}_first_name",
        'last_name': f"test_{user1}_last_name",
        'email': f"test_{user1}@figure1.com",
    })
    assert response.status_code == 200

    # Creating a user with existing uid returns 409
    response = client.post('/pro/v1/user/create', headers=headers, json={
        'user_uid': f"test_{user1}",
        'first_name': f"test_{user2}_first_name",
        'last_name': f"test_{user2}_last_name",
        'email': f"test_{user2}@figure1.com",
    })
    assert response.status_code == 409

    # Creating a user with existing email returns 409
    response = client.post('/pro/v1/user/create', headers=headers, json={
        'user_uid': f"test_{user2}",
        'first_name': f"test_{user2}_first_name",
        'last_name': f"test_{user2}_last_name",
        'email': f"test_{user1}@figure1.com",
    })
    assert response.status_code == 409

    # Creating a new user returns 200
    response = client.post('/pro/v1/user/create', headers=headers, json={
        'user_uid': f"test_{user2}",
        'first_name': f"test_{user2}_first_name",
        'last_name': f"test_{user2}_last_name",
        'email': f"TEST_{user2}@figure1.com",
    })
    assert response.status_code == 200

    u = User.get_user_by_uid_as_dict(f"test_{user2}", session=session)
    assert u.get('userUid') == f"test_{user2}"
    assert u.get('firstName') == f"test_{user2}_first_name"
    assert u.get('lastName') == f"test_{user2}_last_name"
    assert u.get('email') == f"test_{user2.lower()}@figure1.com"

    # Creating a new user with country returns 200
    response = client.post('/pro/v1/user/create',
                           headers=headers,
                           json={
                               'user_uid': f"test_{user3}",
                               'country_uuid': str(test_country.country_uuid),
                               'email': f"test_{user3}@figure1.com",
                           })
    assert response.status_code == 200

    u = User.get_user_by_uid_as_dict(f"test_{user3}", session=session)
    user_metadata = session.query(UserProfile).filter(UserProfile.user_uuid == u.get('userUuid')).one()
    assert user_metadata.country_uuid == test_country.country_uuid

    # creating a user with group uuid
    response = client.post('/pro/v1/user/create',
                           headers=headers,
                           json={
                               'user_uid': f"test_{user4}",
                               'country_uuid': str(test_country.country_uuid),
                               'email': f"test_{user4}@figure1.com",
                               'group_uuid': group_uuid,
                           })
    assert response.status_code == 200
    assert response.json.get('group_uuids') == [group_uuid]
    u = User.get_user_by_uid_as_dict(f"test_{user4}", session=session)
    assert GroupMember.get_by_user_and_group(user_uuid=u.get('userUuid'), group_uuid=group_uuid, session=session)

    GroupManagement.remove_user_from_group(user_uuid=response.json.get('user_uuid'),
                                           group_uuid=group_uuid, session=session)
    session.flush()


def test_create_user_with_assigned_email(client, headers, load_db, test_country, create_group, initialize_data):
    user = _random_string(16)
    user2 = _random_string(16)
    user3 = _random_string(16)
    user4 = _random_string(16)
    user5 = _random_string(16)
    session = load_db
    group_uuid = create_group.groupUuid

    # create a user with email that has been assigned to a group
    new_user_email = f"test_{user}@figure1.com".lower()
    _create_group_member_filter(session,
                                group_uuid=group_uuid,
                                email=new_user_email,
                                first_name="Test",
                                last_name="User")
    response = client.post('/pro/v1/user/create',
                           headers=headers,
                           json={
                               'user_uid': f"test_{user}",
                               'country_uuid': str(test_country.country_uuid),
                               'email': new_user_email
                           })
    assert response.status_code == 200
    assert response.json.get('group_uuids') == [group_uuid]
    user_in_db = session.query(User).filter(User.email == new_user_email).one_or_none()
    session.query(GroupMemberFilter).filter(GroupMemberFilter.user_email == new_user_email).delete()
    assert GroupMember.get_by_user_and_group(user_uuid=user_in_db.user_uuid, group_uuid=group_uuid, session=session)
    assert user_in_db.first_name == 'Test'
    assert user_in_db.last_name == 'User'
    assert user_in_db.user_profile.display_name == 'Test User'
    GroupManagement.remove_user_from_group(user_uuid=response.json.get('user_uuid'),
                                           group_uuid=group_uuid, session=session)
    session.commit()

    # group member filter with valid npi number
    new_user_email2 = f"test_{user2}@figure1.com".lower()
    _create_group_member_filter(session, group_uuid=group_uuid, email=new_user_email2, npi_number=1234567893)
    response = client.post('/pro/v1/user/create',
                           headers=headers,
                           json={
                               'user_uid': f"test_{user2}",
                               'country_uuid': str(test_country.country_uuid),
                               'email': new_user_email2
                           })
    assert response.status_code == 200
    assert response.json.get('group_uuids') == [group_uuid]
    user_uuid = response.json.get('user_uuid')
    user_in_db = session.query(User).filter(User.email == new_user_email2).one_or_none()
    assert user_in_db is not None
    assert GroupMember.get_by_user_and_group(user_uuid=user_in_db.user_uuid, group_uuid=group_uuid, session=session)

    verification = user_in_db.user_verification
    assert verification is not None
    assert verification.verification_type == VerificationType.NPI
    assert verification.verification_status == VerificationStatus.VERIFIED
    assert verification.npi.npi_number == 1234567893

    npi = session.query(UserNPI).filter(UserNPI.user_uuid == user_uuid).one_or_none()
    assert npi is not None
    assert npi.npi_number == 1234567893

    session.query(GroupMemberFilter).filter(GroupMemberFilter.user_email == new_user_email2).delete()
    GroupManagement.remove_user_from_group(user_uuid=user_uuid,
                                           group_uuid=group_uuid, session=session)
    session.commit()

    # group member filter with invalid npi number
    new_user_email3 = f"test_{user3}@figure1.com".lower()
    _create_group_member_filter(session, group_uuid=group_uuid, email=new_user_email3, npi_number=123)
    response = client.post('/pro/v1/user/create',
                           headers=headers,
                           json={
                               'user_uid': f"test_{user3}",
                               'country_uuid': str(test_country.country_uuid),
                               'email': new_user_email3
                           })
    assert response.status_code == 200
    assert response.json.get('group_uuids') == [group_uuid]
    user_uuid = response.json.get('user_uuid')
    user_in_db = session.query(User).filter(User.email == new_user_email3).one_or_none()
    assert user_in_db is not None
    assert GroupMember.get_by_user_and_group(user_uuid=user_uuid, group_uuid=group_uuid, session=session)

    verification = user_in_db.user_verification
    assert verification is None

    npi = session.query(UserNPI).filter(UserNPI.user_uuid == user_uuid).one_or_none()
    assert npi is None

    session.query(GroupMemberFilter).filter(GroupMemberFilter.user_email == new_user_email3).delete()
    GroupManagement.remove_user_from_group(user_uuid=user_uuid,
                                           group_uuid=group_uuid, session=session)
    session.commit()

    # group member filter with tree_uuid
    new_user_email4 = f"test_{user4}@figure1.com".lower()
    specialty_uuid = session.query(SpecialtyTreeV2.specialty_uuid) \
        .filter(SpecialtyTreeV2.specialty_v2_uuid.isnot(None)) \
        .first()[0]
    _create_group_member_filter(session, group_uuid=group_uuid, email=new_user_email4, tree_uuid=specialty_uuid)
    response = client.post('/pro/v1/user/create',
                           headers=headers,
                           json={
                               'user_uid': f"test_{user4}",
                               'country_uuid': str(test_country.country_uuid),
                               'email': new_user_email4
                           })
    assert response.status_code == 200
    assert response.json.get('group_uuids') == [group_uuid]
    user_uuid = response.json.get('user_uuid')
    user_in_db = session.query(User).filter(User.email == new_user_email4).one_or_none()
    assert user_in_db is not None
    assert GroupMember.get_by_user_and_group(user_uuid=user_in_db.user_uuid, group_uuid=group_uuid, session=session)

    assert user_in_db.primary_specialty
    assert user_in_db.primary_specialty.tree_uuid == specialty_uuid

    session.query(GroupMemberFilter).filter(GroupMemberFilter.user_email == new_user_email4).delete()
    GroupManagement.remove_user_from_group(user_uuid=user_uuid,
                                           group_uuid=group_uuid, session=session)
    session.commit()

    # group member filter with country_uuid
    new_user_email5 = f"test_{user5}@figure1.com".lower()
    specialty_uuid = session.query(SpecialtyTreeV2.specialty_uuid) \
        .filter(SpecialtyTreeV2.specialty_v2_uuid.isnot(None)) \
        .first()[0]
    _create_group_member_filter(session, group_uuid=group_uuid, email=new_user_email5,
                                tree_uuid=specialty_uuid, country_uuid=str(test_country.country_uuid))
    response = client.post('/pro/v1/user/create',
                           headers=headers,
                           json={
                               'user_uid': f"test_{user5}",
                               'email': new_user_email5
                           })
    assert response.status_code == 200
    assert response.json.get('group_uuids') == [group_uuid]
    user_uuid = response.json.get('user_uuid')
    user_in_db = session.query(User).filter(User.email == new_user_email5).one_or_none()
    assert user_in_db is not None

    assert GroupMember.get_by_user_and_group(user_uuid=user_in_db.user_uuid, group_uuid=group_uuid, session=session)
    assert user_in_db.user_profile.country_uuid is not None

    session.query(GroupMemberFilter).filter(GroupMemberFilter.user_email == new_user_email5).delete()
    GroupManagement.remove_user_from_group(user_uuid=user_uuid,
                                           group_uuid=group_uuid, session=session)
    session.commit()


def test_create_user_with_dmd_npi_record(client, headers, load_db, user_email_with_dmd_npi_record):
    user1 = _random_string(16)
    session = load_db

    # Creating a new user with dmd npi record returns 200
    response = client.post('/pro/v1/user/create', headers=headers, json={
        'user_uid': f"test_{user1}",
        'first_name': f"test_{user1}_first_name",
        'last_name': f"test_{user1}_last_name",
        'email': user_email_with_dmd_npi_record,
    })

    assert response.status_code == 200

    user_in_db = session.query(User).filter(User.email == user_email_with_dmd_npi_record).one_or_none()
    assert user_in_db

    assert user_in_db.user_verification.npi.npi_number is not None
    assert user_in_db.user_verification.verification_status is VerificationStatus.VERIFIED
    assert user_in_db.user_verification.flagged_for_review is True


def test_link_anonymous_user_with_new_user_if_the_associated_user_is_none(client, headers, load_db,
                                                                          test_country, get_firestore_client,
                                                                          test_campaign, test_user):
    user1 = _random_string(16)
    user2 = _random_string(16)
    anon = AnonymousUser()
    anon.user_uid = f"test_{user2}"
    anon.user_uuid = uuid.uuid4()
    session = load_db
    fs = get_firestore_client
    session.add(anon)

    approved_case = _create_case(author_uuid=test_user.get('userUuid'),
                                 state=CaseState.SC_APPROVED,
                                 case_type=CaseType.CME,
                                 campaign_uuid=test_campaign.campaign_uuid,
                                 session=session)

    CaseProgress.create_or_update(user_uuid=anon.user_uuid,
                                  case_uuid=approved_case.case_uuid,
                                  session=session,
                                  is_complete=True)

    session.commit()

    response = client.post('/pro/v1/user/create',
                           headers=headers,
                           json={
                               'user_uid': f"test_{user1}",
                               'country_uuid': str(test_country.country_uuid),
                               'email': f"test_{user1}@figure1.com",
                               'anonymous_uid': anon.user_uid
                           })
    assert response.status_code == 200

    # testing CaseProgress created in db
    cp = session.query(CaseProgress).filter(CaseProgress.case_uuid == approved_case.case_uuid,
                                            CaseProgress.user_uuid == anon.user_uuid).all()
    assert cp is not None

    # testing firestore
    userdb_doc = _get_fs_doc(documents=[f"test_{user1}", str(approved_case.case_uuid)],
                             collections=['usersDB', 'stateDB'],
                             fs=fs)

    assert userdb_doc['case']['completedAt'] is not None


def test_link_anonymous_user_with_new_user_if_the_associated_user_exists(client, headers, load_db,
                                                                         test_country, get_firestore_client,
                                                                         test_campaign, test_user):
    user1 = _random_string(16)
    anon = AnonymousUser()
    anon.user_uid = f"test_{user1}"
    anon.user_uuid = test_user.get("userUuid")
    session = load_db
    session.add(anon)

    approved_case = _create_case(author_uuid=test_user.get('userUuid'),
                                 state=CaseState.SC_APPROVED,
                                 case_type=CaseType.CME,
                                 campaign_uuid=test_campaign.campaign_uuid,
                                 session=session)

    CaseProgress.create_or_update(user_uuid=anon.user_uuid,
                                  case_uuid=approved_case.case_uuid,
                                  session=session,
                                  is_complete=True)

    session.commit()

    response = client.post('/pro/v1/user/create',
                           headers=headers,
                           json={
                               'user_uid': f"test_{user1}",
                               'country_uuid': str(test_country.country_uuid),
                               'email': f"test_{user1}@figure1.com",
                               'anonymous_uid': anon.user_uid
                           })
    assert response.status_code == 200

    # the existing account is not overtaken
    new_user = User.get_user_by_uid_as_dict(f"test_{user1}", session=session)
    assert new_user.get('userUuid') != test_user.get('userUuid')

    # testing CaseProgress not created in db
    cp = session.query(CaseProgress).filter(CaseProgress.case_uuid == approved_case.case_uuid,
                                            CaseProgress.user_uuid == new_user.get('userUuid')).all()
    assert len(cp) is 0


def test_link_anonymous_user_with_existing_user(client, headers, load_db, get_firestore_client,
                                                test_campaign, test_user):
    session = load_db
    fs = get_firestore_client
    user1 = _random_string(16)

    # create an anonymous user
    anon = AnonymousUser()
    anon.user_uid = f"test_{user1}"
    anon.user_uuid = uuid.uuid4()
    session.add(anon)
    user2 = _create_user(session=session)

    approved_case = _create_case(author_uuid=test_user.get('userUuid'),
                                 state=CaseState.SC_APPROVED,
                                 case_type=CaseType.CME,
                                 campaign_uuid=test_campaign.campaign_uuid,
                                 session=session)

    CaseProgress.create_or_update(user_uuid=anon.user_uuid,
                                  case_uuid=approved_case.case_uuid,
                                  session=session,
                                  is_complete=True)
    session.commit()

    response = client.post('/pro/v1/user/ungated/anonymous_user/existing_user',
                           headers=headers,
                           json={
                               'user_uid': str(user2.user_uid),
                               'anonymous_uid': anon.user_uid,
                           })
    assert response.status_code == 200

    # testing CaseProgress created in db
    cp = session.query(CaseProgress).filter(CaseProgress.case_uuid == approved_case.case_uuid,
                                            CaseProgress.user_uuid == anon.user_uuid).all()
    assert cp is not None

    # testing FS
    userdb_doc = _get_fs_doc(documents=[str(user2.user_uid), str(approved_case.case_uuid)],
                             collections=['usersDB', 'stateDB'],
                             fs=fs)

    assert userdb_doc['case']['completedAt'] is not None


def test_update_user(load_db, get_firestore_client, user_specialty):
    session = load_db
    fs = get_firestore_client
    user = _random_string(16)
    user_uid = f'test_{user}'
    specialty = user_specialty
    mgmt = UserManagement(user_uid=user_uid, session=session, is_new_user=True)
    mgmt.add_user(first_name=f"test_{user}_first_name",
                  last_name=f"test_{user}_last_name",
                  email=f"test_{user}@figure1.com",
                  user_uuid=None,
                  legacy=False)
    session.commit()

    t = update_user_internal(user_uid=f"test_{user}", user_update=UpdateUserModel(
        first_name=' newFirstName ',
        last_name=' newLastName ',
        specialtyTreeUuids=[specialty.treeUuid],
        experience=[
            {
                "location": "Some Fake Hospital",
                "description": "Interesting stuff",
                "startYear": 2009,
                "endYear": 2012
            },
            {
                "location": "Some Fake Hospital",
                "description": "Interesting stuff",
                "startYear": 2012
            }],
        onboardingCompleted=True,
        onboardingInterestsCompleted=True
    )).pop('task')
    t.apply()
    assert mgmt.user.onboarding_completed is True
    experience = mgmt.get_user_experience()
    exp = list(experience)
    assert len(exp) == 2
    has_end_year = None
    for user_exp in exp:
        if user_exp.endYear is not None:
            has_end_year = user_exp
    assert has_end_year.endYear is not None
    assert has_end_year.isCurrent is False

    t = update_user_internal(user_uid=f"test_{user}", user_update=UpdateUserModel(
        experience=[
            {
                "experienceUuid": has_end_year.experienceUuid,
                "location": "Some Fake Hospital",
                "description": "Interesting stuff",
                "startYear": 2009
            }],
        onboardingCompleted=True,
        onboardingInterestsCompleted=True,
        graduation_date="2025-02-20"
    )).pop('task')
    t.apply()
    graduation_date = "2025-02-20"
    experience2 = list(mgmt.get_user_experience())
    assert len(experience2) == 2
    check_experience = None
    for e in experience2:
        if e.experienceUuid == has_end_year.experienceUuid:
            check_experience = e
    assert check_experience.endYear is None
    assert check_experience.isCurrent is True
    user_doc1 = _get_fs_doc(documents=[user_uid], collections=['usersDB'], fs=fs)
    assert 'onboardingCompleted' in user_doc1
    assert user_doc1['onboardingCompleted'] is True
    assert user_doc1['firstName'] == 'newFirstName'
    assert user_doc1['lastName'] == 'newLastName'
    assert user_doc1['displayName'] == 'newFirstName newLastName'
    assert user_doc1['graduationDate'] == graduation_date
    user_doc2 = _get_fs_doc(documents=[str(mgmt.user.user_uuid)], collections=['usersProfileDB'], fs=fs)
    assert user_doc2['graduationDate'] == graduation_date


def test_update_avatar(load_db, get_firestore_client):
    session = load_db
    fs = get_firestore_client
    mgmt = _create_user(session=session)
    session.commit()
    task = update_user_avatar_internal(user_uid=mgmt.user_uid, url='https://avatar.example.com')
    w = task.apply_async()
    user_local_doc = UserDocument.get_full_profile(user_uuid=mgmt.user_uuid, session=session)
    assert 'avatar' in user_local_doc
    w.get()
    user_doc = _get_fs_doc(documents=[mgmt.user_uid], collections=['usersDB'], fs=fs)
    assert 'avatar' in user_doc
    assert user_doc['avatar'] == 'https://avatar.example.com'
    assert user_local_doc['avatar'] == user_doc['avatar']


def test_update_non_primary_specialties(load_db, test_user, user_specialty):
    session = load_db
    user = _random_string(16)
    user_uid = f'test_{user}'
    specialty = user_specialty
    mgmt = UserManagement(user_uid=user_uid, session=session, is_new_user=True)
    mgmt.add_user(first_name=f"test_{user}_first_name",
                  last_name=f"test_{user}_last_name",
                  email=f"test_{user}@figure1.com",
                  user_uuid=None,
                  legacy=False)
    user = mgmt.user
    session.commit()

    # It should remove non primary specialties
    mgmt.set_specialties([specialty.treeUuid])
    assert session.query(UserSpecialtyTreeV2) \
        .filter(UserSpecialtyTreeV2.user_uuid == user.user_uuid,
                UserSpecialtyTreeV2.tree_uuid == specialty.treeUuid) \
        .one_or_none()

    mgmt.remove_non_primary_specialties()
    assert not session.query(UserSpecialtyTreeV2) \
        .filter(UserSpecialtyTreeV2.user_uuid == user.user_uuid,
                UserSpecialtyTreeV2.tree_uuid == specialty.treeUuid) \
        .one_or_none()

    # It should not remove primary specialties
    mgmt.set_primary_specialty(specialty.treeUuid)
    assert session.query(UserSpecialtyTreeV2) \
        .filter(UserSpecialtyTreeV2.user_uuid == user.user_uuid,
                UserSpecialtyTreeV2.tree_uuid == specialty.treeUuid) \
        .one_or_none()

    mgmt.remove_non_primary_specialties()
    assert session.query(UserSpecialtyTreeV2) \
        .filter(UserSpecialtyTreeV2.user_uuid == user.user_uuid,
                UserSpecialtyTreeV2.tree_uuid == specialty.treeUuid) \
        .one_or_none()


def test_validate_username(load_db, client, headers):
    user = _random_string(16)
    approved_usernames = ['cgarraan', 'stephania', 'dirka5', 'admiaus', 'amarioncm', 'pedrolona']
    unapproved_usernames = ['chink', 'garca', 'spic', 'anajoseph', 'jackass', 'pedo', 'fuckyoubro']
    # incorrect_usernames are usernames that don't follow the regex pattern
    incorrect_usernames = ['rich%arr#', 'richa$', '@richard', 'sas||sffs']
    correct_usernames = ['richard91', 'richar++_d', '123__ia', 'rich++1237473', 'r1c-', '++ric.ardo_']
    client.post('/pro/v1/user/create', headers=headers, json={
        'user_uid': f"test_{user}",
        'first_name': f"test_{user}_first_name",
        'last_name': f"test_{user}_last_name",
        'email': f"test_{user}@figure1.com",
    })
    client.post(f'/pro/v1/user/test_{user}', headers=headers, json={
        'username': f"test_{user}_username",
    })

    # Username already in use returns 409
    existing_username = f"test_{user}_username"
    response = client.get(f'/pro/v1/user/validate/username/{existing_username}', headers=headers)
    assert response.status_code == 409

    for u in approved_usernames:
        response = client.get(f'/pro/v1/user/validate/username/{u}', headers=headers)
        assert response.status_code == 200
    for u in unapproved_usernames:
        response = client.get(f'/pro/v1/user/validate/username/{u}', headers=headers)
        assert response.status_code == 422
    for u in incorrect_usernames:
        response = client.get(f'/pro/v1/user/validate/username/{u}', headers=headers)
        assert response.status_code == 422
    for u in correct_usernames:
        response = client.get(f'/pro/v1/user/validate/username/{u}', headers=headers)
        assert response.status_code == 200
    response = client.get(f'/pro/v1/user/validate/username/{existing_username.upper()}', headers=headers)
    assert response.status_code == 409


def test_validate_email(client, headers):
    user = _random_string(16)
    client.post('/pro/v1/user/create', headers=headers, json={
        'user_uid': f"test_{user}",
        'first_name': f"test_{user}_first_name",
        'last_name': f"test_{user}_last_name",
        'email': f"test_{user}@figure1.com",
    })
    client.post(f'/pro/v1/user/test_{user}', headers=headers, json={
        'username': f"test_{user}_username",
    })

    # Invalid email format returns 422
    response = client.get(f'/pro/v1/user/validate/email/invalid_format', headers=headers)
    assert response.status_code == 422
    response = client.get(f'/pro/v1/user/validate/email/figure1.com', headers=headers)
    assert response.status_code == 422
    response = client.get(f'/pro/v1/user/validate/email/invalid_format@figure1', headers=headers)
    assert response.status_code == 422
    response = client.get(f'/pro/v1/user/validate/email/invalidformat@@figure1.com', headers=headers)
    assert response.status_code == 422
    response = client.get(f'/pro/v1/user/validate/email/invalidformat@-figure1.com', headers=headers)
    assert response.status_code == 422
    response = client.get(f'/pro/v1/user/validate/email/invalidformat@.figure1.com', headers=headers)
    assert response.status_code == 422
    response = client.get(f'/pro/v1/user/validate/email/invalidformat@figure1 .com', headers=headers)
    assert response.status_code == 422
    response = client.get(f'/pro/v1/user/validate/email/invalidformat@.com', headers=headers)
    assert response.status_code == 422

    # Email already in use returns 409
    existing_email = f"test_{user}@figure1.com"
    response = client.get(f'/pro/v1/user/validate/email/{existing_email}', headers=headers)
    assert response.status_code == 409
    # Email check is case insensitive
    response = client.get(f'/pro/v1/user/validate/email/{existing_email.upper()}', headers=headers)
    assert response.status_code == 409
    response = client.get(f'/pro/v1/user/validate/email/test@figure1.com', headers=headers)
    assert response.status_code == 200
    response = client.get(f'/pro/v1/user/validate/email/test.test@figure1.com', headers=headers)
    assert response.status_code == 200
    response = client.get(f'/pro/v1/user/validate/email/test@figure1.co.uk', headers=headers)
    assert response.status_code == 200
    response = client.get(f'/pro/v1/user/validate/email/!#$%&amp;`*+/=?^`|~@figure1.com', headers=headers)
    assert response.status_code == 422
    response = client.get(f'/pro/v1/user/validate/email/test@figure-1.com', headers=headers)
    assert response.status_code == 200


def test_user_follow(load_db, client, headers, get_firestore_client):
    session = load_db
    fs = get_firestore_client
    u1 = _random_string(16)
    u2 = _random_string(16)
    res1 = client.post('/pro/v1/user/create', headers=headers, json={
        'user_uid': f"test_{u1}",
        'first_name': f"test_{u1}_first_name",
        'last_name': f"test_{u1}_last_name",
        'email': f"test_{u1}@figure1.com",
    })
    assert res1.status_code == 200
    user1 = session.query(User).filter(User.user_uid == f'test_{u1}').one_or_none()
    assert user1 is not None

    res2 = client.post('/pro/v1/user/create', headers=headers, json={
        'user_uid': f"test_{u2}",
        'first_name': f"test_{u2}_first_name",
        'last_name': f"test_{u2}_last_name",
        'email': f"test_{u2}@figure1.com",
    })
    assert res2.status_code == 200
    user2 = session.query(User).filter(User.user_uid == f'test_{u2}').one_or_none()
    assert user2 is not None

    # Test follow
    response = client.get(f'/pro/v1/user/{user1.user_uid}/follow/{user2.user_uuid}', headers=headers)
    assert response.status_code == 200
    follow = session.query(UserFollow).get((user2.user_uuid, user1.user_uuid))
    assert follow is not None
    assert follow.deleted_at is None

    follow_doc = _get_fs_doc(documents=[str(user2.user_uuid), str(user1.user_uuid)],
                             collections=['usersProfileDB', 'followers'],
                             fs=fs)
    assert follow_doc is not None
    following_doc = _get_fs_doc(documents=[str(user1.user_uuid), str(user2.user_uuid)],
                                collections=['usersProfileDB', 'following'],
                                fs=fs)
    assert following_doc is not None

    # Test unfollow
    response = client.get(f'/pro/v1/user/{user1.user_uid}/unfollow/{user2.user_uuid}', headers=headers)
    assert response.status_code == 200
    session.refresh(follow)
    assert follow is not None
    assert follow.deleted_at is not None


def test_mixpanel_parser(test_user, load_db):
    session = load_db
    test_inst_email_parse = False
    test_license_parse = False
    test_npi_parse = False
    for u in session.query(UserVerification).all():
        if u.license:
            assert u.verification_type == VerificationType.LICENSE
            if test_license_parse:
                continue
            user_detail = UserDocument.user_detail(user_uuid=u.user_uuid, session=session)
            user_detail.update({
                "subscribedChannels": ['EE'],
                "followingCount": 1,
                "followerCount": 2,
            })
            MixpanelUserData.parse_obj(user_detail).dict()
            test_license_parse = True
        elif u.npi:
            assert u.verification_type == VerificationType.NPI
            if test_npi_parse:
                continue
            n = u.npi.as_dict()
            user_detail = UserDocument.user_detail(user_uuid=u.user_uuid, session=session)
            user_detail.update({
                "subscribedChannels": ['EE'],
                "followingCount": 1,
                "followerCount": 2,
            })
            MixpanelUserData.parse_obj(user_detail).dict()
            test_npi_parse = True
        if u.verification_type == VerificationType.INSTITUTIONAL_EMAIL:
            if test_inst_email_parse:
                continue
            user_detail = UserDocument.user_detail(user_uuid=u.user_uuid, session=session)
            user_detail.update({
                "subscribedChannels": ['EE'],
                "followingCount": 1,
                "followerCount": 2,
            })
            MixpanelUserData.parse_obj(user_detail).dict()
            test_inst_email_parse = True


def test_user_delete(test_user, load_db, iterable_channels):
    """
    Ensure that a user deletion call returns the correct data to iterable
    """
    session = load_db
    it = IterableAPI()
    UserEvents.USER_DELETED(user_uuid=test_user.get('userUuid')).apply()
    it_prof = get_user_for_bulk_update(user_uuid=test_user.get('userUuid'), session=session)

    assert it_prof.email == f"{test_user.get('userUuid')}@figure1.com"
    iterable_update_user_object = generate_iterable_user_object(test_user.get('userUuid'), session)
    r = it.update_user(email=iterable_update_user_object.email, data_fields=iterable_update_user_object.dict())

    assert r['data']['email'] == f"{test_user.get('userUuid')}@figure1.com"

    u = User.q.get(test_user.get('userUuid'))
    assert u.deleted_at is not None
    assert u.user_state.deleted_at is not None

    c = get_user_comm_preference_for_bulk_update(user_uuid=u.user_uuid, session=session)
    assert c['unsubscribed_channel_types'] == [10, 20]
    assert c['unsubscribed_message_types'] == []
    assert c['subscribed_message_types'] == []


def test_onboarding_state_non_usa(client, headers, load_db, test_country):
    session = load_db
    user = _random_string(16)
    user_uid = 'test_' + user

    # User creation
    response = client.post('/pro/v1/user/create', headers=headers, json={
        'user_uid': user_uid,
        'email': f"test_{user}@figure1.com",
        'country_uuid': str(test_country.country_uuid)
    })
    assert response.json.get('onboardingState') == 'information'

    u = session.query(User).filter(User.user_uid == f"test_{user}").one()
    assert u
    assert u.user_state.onboarding_state == OnboardingState.INFORMATION

    # Transition out of INFORMATION
    specialty = session.query(SpecialtyTreeV2) \
        .filter(SpecialtyTreeV2.profession_uuid.isnot(None), SpecialtyTreeV2.specialty_v2_uuid.isnot(None)).first()
    response = client.post(f'/pro/v1/user/{user_uid}', headers=headers, json={
        "firstName": f"test_{user}_first_name",
        "lastName": f"test_{user}_last_name",
        "primarySpecialty": str(specialty.specialty_uuid)
    })
    assert response.json.get('onboardingState') == 'verification'
    session.refresh(u)
    assert u.user_state.onboarding_state == OnboardingState.VERIFICATION

    # Transition out of VERIFICATION
    response = client.post('/pro/v1/verification', headers=headers, json={
        'method': 'photo',
        'user_uid': user_uid,
        'photos': ['https://picsum.photos/100']
    })
    assert response.json.get('onboardingState') == 'username'
    session.refresh(u)
    assert u.user_state.onboarding_state == OnboardingState.USERNAME

    # Transition out of USERNAME
    response = client.post(f'/pro/v1/user/{user_uid}', headers=headers, json={
        "username": f"test_{user}",
    })

    assert response.json.get('onboardingState') == 'completed'
    session.refresh(u)
    assert u.user_state.onboarding_state == OnboardingState.COMPLETED


def test_onboarding_state_usa(client, headers, load_db, usa_country):
    session = load_db
    user = _random_string(16)
    user_uid = 'test_' + user

    # User creation
    response = client.post('/pro/v1/user/create', headers=headers, json={
        'user_uid': user_uid,
        'email': f"test_{user}@figure1.com",
        'country_uuid': str(usa_country.country_uuid)
    })
    assert response.json.get('onboardingState') == 'usa_information'

    u = session.query(User).filter(User.user_uid == f"test_{user}").one()
    assert u
    assert u.user_state.onboarding_state == OnboardingState.USA_INFORMATION

    # Only submitting npi number remains in CONFIRMATION
    response = client.post('/pro/v1/verification', headers=headers, json={
        'method': 'npi',
        'user_uid': user_uid,
        'npi_number': 1234567893,
    })
    assert response.json.get('onboardingState') == 'confirmation'
    session.refresh(u)
    assert u.user_state.onboarding_state == OnboardingState.CONFIRMATION

    # Transition out of CONFIRMATION
    specialty = session.query(SpecialtyTreeV2) \
        .filter(SpecialtyTreeV2.profession_uuid.isnot(None), SpecialtyTreeV2.specialty_v2_uuid.isnot(None)).first()
    response = client.post(f'/pro/v1/user/{user_uid}', headers=headers, json={
        "firstName": f"test_{user}_first_name",
        "lastName": f"test_{user}_last_name",
        "primarySpecialty": str(specialty.specialty_uuid)
    })
    assert response.json.get('onboardingState') == 'username'
    session.refresh(u)
    assert u.user_state.onboarding_state == OnboardingState.USERNAME

    # Transition out of USERNAME
    response = client.post(f'/pro/v1/user/{user_uid}', headers=headers, json={
        "username": f"test_{user}",
    })

    assert response.json.get('onboardingState') == 'completed'
    session.refresh(u)
    assert u.user_state.onboarding_state == OnboardingState.COMPLETED


def test_onboarding_state_old_reg_flow(client, headers, load_db, test_country, test_school):
    session = load_db
    user = _random_string(16)
    user_uid = 'test_' + user

    # User creation
    p = session.query(SpecialtyTreeV2).filter(SpecialtyTreeV2.specialty_v2_uuid.is_(None)).first()
    response = client.post('/pro/v1/user/create', headers=headers, json={
        'user_uid': user_uid,
        'email': f"test_{user}@figure1.com",
        'first_name': user,
        'last_name': user,
        'profession_uuid': p.specialty_uuid
    })
    assert response.json.get('onboardingState') == 'country'

    u = session.query(User).filter(User.user_uid == f"test_{user}").one()
    assert u
    assert u.user_state.onboarding_state == OnboardingState.COUNTRY

    # Verification
    response = client.post('/pro/v1/verification', headers=headers, json={
        'method': 'license',
        'user_uid': user_uid,
        'license_number': '1234',
        'license_school_code': str(test_school.school_uuid),
        'license_country_code': str(test_country.country_uuid),
        'graduation_year': 2020
    })
    assert response.json.get('onboardingState') == 'information'
    session.refresh(u)
    assert u.user_state.onboarding_state == OnboardingState.INFORMATION

    # Username / specialty
    specialty = session.query(SpecialtyTreeV2) \
        .filter(SpecialtyTreeV2.specialty_v2_uuid.isnot(None),
                SpecialtyTreeV2.profession_uuid == p.profession_uuid).first()
    response = client.post(f'/pro/v1/user/{user_uid}', headers=headers, json={
        "username": f"test_{user}",
        "primarySpecialty": str(specialty.specialty_uuid),
        "interests": [str(specialty.specialty_uuid)]
    })
    assert response.json.get('onboardingState') == 'completed'
    session.refresh(u)
    assert u.user_state.onboarding_state == OnboardingState.COMPLETED


def test_onboarding_state_usa_student(client, headers, load_db, usa_country):
    session = load_db
    user = _random_string(16)
    user_uid = 'test_' + user

    # User creation
    response = client.post('/pro/v1/user/create', headers=headers, json={
        'user_uid': user_uid,
        'email': f"test_{user}@figure1.com",
        'country_uuid': str(usa_country.country_uuid)
    })
    assert response.json.get('onboardingState') == 'usa_information'

    u = session.query(User).filter(User.user_uid == f"test_{user}").one()
    assert u
    assert u.user_state.onboarding_state == OnboardingState.USA_INFORMATION

    # Only submitting npi number remains in USA_INFORMATION
    response = client.post('/pro/v1/verification', headers=headers, json={
        'method': 'npi',
        'user_uid': user_uid,
        'npi_number': 1234567893,
    })
    assert response.json.get('onboardingState') == 'confirmation'
    session.refresh(u)
    assert u.user_state.onboarding_state == OnboardingState.CONFIRMATION

    # Transition out of USA_INFORMATION
    profession = session.query(ProfessionV2).filter(ProfessionV2.profession_category == 'Other Student').first()
    specialty = session.query(SpecialtyTreeV2) \
        .filter(SpecialtyTreeV2.profession_uuid.isnot(None),
                SpecialtyTreeV2.profession_uuid == profession.specialty_uuid).first()
    response = client.post(f'/pro/v1/user/{user_uid}', headers=headers, json={
        "firstName": f"test_{user}_first_name",
        "lastName": f"test_{user}_last_name",
        "primarySpecialty": str(specialty.specialty_uuid)
    })
    assert response.json.get('onboardingState') == 'grad_date'
    session.refresh(u)
    assert u.user_state.onboarding_state == OnboardingState.GRAD_DATE

    # Transition out of Grad Date
    response = client.post(f'/pro/v1/user/{user_uid}', headers=headers, json={
        "graduationDate": "2099-12-01"
    })
    assert response.json.get('onboardingState') == 'username'
    session.refresh(u)
    assert u.user_state.onboarding_state == OnboardingState.USERNAME

    # Transition out of USERNAME
    response = client.post(f'/pro/v1/user/{user_uid}', headers=headers, json={
        "username": f"test_{user}",
    })

    assert response.json.get('onboardingState') == 'completed'
    session.refresh(u)
    assert u.user_state.onboarding_state == OnboardingState.COMPLETED


def test_onboarding_state_non_usa_student(client, headers, load_db, test_country):
    session = load_db
    user = _random_string(16)
    user_uid = 'test_' + user

    # User creation
    response = client.post('/pro/v1/user/create', headers=headers, json={
        'user_uid': user_uid,
        'email': f"test_{user}@figure1.com",
        'country_uuid': str(test_country.country_uuid)
    })
    assert response.json.get('onboardingState') == 'information'

    u = session.query(User).filter(User.user_uid == f"test_{user}").one()
    assert u
    assert u.user_state.onboarding_state == OnboardingState.INFORMATION

    # Transition out of INFORMATION
    profession = session.query(ProfessionV2).filter(ProfessionV2.profession_category == 'Other Student').first()
    specialty = session.query(SpecialtyTreeV2) \
        .filter(SpecialtyTreeV2.profession_uuid.isnot(None),
                SpecialtyTreeV2.profession_uuid == profession.specialty_uuid).first()
    response = client.post(f'/pro/v1/user/{user_uid}', headers=headers, json={
        "firstName": f"test_{user}_first_name",
        "lastName": f"test_{user}_last_name",
        "primarySpecialty": str(specialty.specialty_uuid)
    })
    assert response.json.get('onboardingState') == 'grad_date'
    session.refresh(u)
    assert u.user_state.onboarding_state == OnboardingState.GRAD_DATE

    # Transition out of Grad Date
    response = client.post(f'/pro/v1/user/{user_uid}', headers=headers, json={
        "graduationDate": "2099-12-01"
    })
    assert response.json.get('onboardingState') == 'verification'
    session.refresh(u)
    assert u.user_state.onboarding_state == OnboardingState.VERIFICATION

    # Transition out of VERIFICATION
    response = client.post('/pro/v1/verification', headers=headers, json={
        'method': 'photo',
        'user_uid': user_uid,
        'photos': ['https://picsum.photos/100']
    })
    assert response.json.get('onboardingState') == 'username'
    session.refresh(u)
    assert u.user_state.onboarding_state == OnboardingState.USERNAME

    # Transition out of USERNAME
    response = client.post(f'/pro/v1/user/{user_uid}', headers=headers, json={
        "username": f"test_{user}",
    })

    assert response.json.get('onboardingState') == 'completed'
    session.refresh(u)
    assert u.user_state.onboarding_state == OnboardingState.COMPLETED


def test_get_user_potential_group(client, headers, create_group, load_db):
    session = load_db
    user_email = f"test{_random_string(6)}@test.com"
    group = create_group
    group_uuid = group.groupUuid
    session.commit()
    group_filter = _create_group_member_filter(session, email=user_email, group_uuid=group_uuid)

    # success
    response = client.get('/pro/v1/user/potential_group',
                          headers=headers,
                          query_string={'group_filter_uuid': group_filter.group_filter_uuid})

    assert response.status_code == 200
    assert response.json['userEmail'] == user_email
    assert response.json['potentialGroup']['groupUuid'] == group_uuid

    session.query(GroupMemberFilter).filter(GroupMemberFilter.user_email == user_email).delete()
    session.commit()

    # user is not invited.
    response = client.get('/pro/v1/user/potential_group',
                          headers=headers,
                          query_string={'user_uuid': user_email,
                                        'group_uuid': group_uuid})
    assert response.status_code == 400
