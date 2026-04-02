import os
import csv
import uuid

import pytest
from werkzeug.datastructures import FileStorage

from figure1.common.types import CaseState, Locale
from figure1.common.types.groups import GroupTypes, GroupUpdateModel
from figure1.exceptions.user import GroupInactive
from figure1.pro.groups.domain import invite_members_to_group, admin_update_group
from figure1.tests.functional.pro.test_user import _random_string
from figure1.exceptions import GroupException
from figure1.common.helpers import GroupManagement
from figure1.common.models.db import Case, User, GroupMemberFilter, SpecialtyTreeV2, GroupMember
from figure1.tests.utils.case import create_test_case
from figure1.tests.utils.user import create_test_user


def _file_storage(path, filename):
    return FileStorage(
        stream=open(path, "rb"),
        filename=filename
    )


def test_add_user_to_group(test_user, create_group, load_db):
    session = load_db
    g = create_group
    test_user_uuid = test_user.get('userUuid')
    GroupManagement.add_user_to_group(user_uuid=test_user_uuid, group_uuid=g.groupUuid, session=session)
    group_with_user = GroupManagement.get_group(group_uuid=g.groupUuid, session=session)
    # the group creator + the added member = 2
    assert len(group_with_user.groupMembers) == 2
    GroupManagement.remove_user_from_group(user_uuid=test_user_uuid, group_uuid=g.groupUuid, session=session)
    session.flush()


def test_delete_institutional_group(test_user, create_institutional_group, test_institutional_group_case, load_db):
    session = load_db
    g = create_institutional_group
    test_user_uuid = test_user.get('userUuid')

    # Deleting institutional group with a case raises exception
    with pytest.raises(GroupException):
        GroupManagement.delete_group(group_uuid=g.groupUuid, session=session)
    test_institutional_group_case.group_uuid = None
    session.add(test_institutional_group_case)
    session.flush()

    # Deleting institutional group with a member raises exception
    GroupManagement.add_user_to_group(user_uuid=test_user_uuid, group_uuid=g.groupUuid, session=session)
    with pytest.raises(GroupException):
        GroupManagement.delete_group(group_uuid=g.groupUuid, session=session)

    GroupManagement.remove_user_from_group(user_uuid=test_user_uuid, group_uuid=g.groupUuid, session=session)


def test_delete_user_group(test_user, load_db):
    session = load_db
    g = GroupManagement.create_group(group_name='test_group_delete',
                                     group_label='test_group_delete_label',
                                     group_type=GroupTypes.USER,
                                     session=session)
    case, _ = create_test_case(author_uuid=test_user.get('userUuid'),
                               is_paging_case=False,
                               language=Locale.EN_US.code,
                               title="Case Title",
                               caption="Case Caption",
                               state=CaseState.APPROVED,
                               group_uuid=g.groupUuid,
                               session=session)

    test_user_uuid = test_user.get('userUuid')
    GroupManagement.add_user_to_group(user_uuid=test_user_uuid, group_uuid=g.groupUuid, session=session)

    GroupManagement.delete_group(group_uuid=g.groupUuid, session=session)
    # Deleting user group with a member removes membership
    gm = session.query(GroupMember).filter(GroupMember.group_uuid == g.groupUuid,
                                           GroupMember.user_uuid == test_user_uuid).first()
    assert gm is None
    # Deleting user group with a case marks case as deleted
    c = session.query(Case).get(case.case_uuid)
    assert c.deleted_at is not None


def test_add_avatar_to_group(create_group, load_db):
    session = load_db
    g = create_group
    avatar_url = f'https://figure1-pro-dev.imgix.net/groups/{g.groupUuid}/avatar/filename.jpg'
    updated = GroupManagement.modify_group(group_uuid=g.groupUuid,
                                           session=session,
                                           group_avatar=avatar_url)
    assert updated.groupAvatar == avatar_url


def test_create_delete_group(client, headers, test_user, load_db):
    group = _random_string(16)
    user = test_user
    session = load_db

    # test create group - missing group_creator_uuid
    response = client.post('/pro/v1/groups/create', headers=headers, json={
        'group_description': f"test_{group}_description",
        'group_name': f"test_{group}_name",
        'group_active': False,
        'group_label': f"test_{group}_label"
    })
    assert response.status_code == 400

    # test create group
    response = client.post('/pro/v1/groups/create', headers=headers, json={
        'group_description': f"test_{group}_description",
        'group_name': f"test_{group}_name",
        'group_active': False,
        'group_label': f"test_{group}_label",
        'group_creator_uuid': user.get('userUuid')
    })
    assert response.status_code == 200
    group_uuid = response.json.get('groupUuid')
    g = GroupManagement.get_group(group_uuid=group_uuid, session=session)
    assert g is not None
    assert g.groupType == GroupTypes.USER.value

    # test create group with duplicate name
    response = client.post('/pro/v1/groups/create', headers=headers, json={
        'group_description': f"test_{group}_description",
        'group_name': f"test_{group}_name",
        'group_active': False,
        'group_label': f"test_{group}_label",
        'group_creator_uuid': user.get('userUuid')
    })
    assert response.status_code == 409

    # test delete group
    GroupManagement.remove_user_from_group(user_uuid=user.get('userUuid'), group_uuid=group_uuid, session=session)
    session.commit()
    g = GroupManagement.delete_group(group_uuid=group_uuid, session=session)
    assert g is None


def test_update_group(client, headers, create_group, load_db):
    group = create_group
    session = load_db

    admin_update_group(group_uuid=str(group.groupUuid),
                       update=GroupUpdateModel(group_name="test_update_name",
                                               group_description='test_update_description'),
                       session=session)
    session.commit()
    updated_group = GroupManagement.get_group(group_uuid=group.groupUuid, session=session)
    assert updated_group.groupName == "test_update_name"
    assert updated_group.groupDescription == "test_update_description"


def test_create_institutional_and_user_group(client, headers, load_db, test_user):
    session = load_db
    user = test_user

    # test institutional group
    group = _random_string(16)
    response = client.post('/pro/v1/groups/create', headers=headers, json={
        'group_description': f"test_{group}_description",
        'group_name': f"test_{group}_name",
        'group_active': False,
        'group_label': f"test_{group}_label",
        'group_type': 'institutional',
        'group_creator_uuid': user.get('userUuid')
    })
    assert response.status_code == 200
    group_uuid = response.json.get('groupUuid')
    g = GroupManagement.get_group(group_uuid=group_uuid, session=session)
    assert g is not None
    assert g.groupType == GroupTypes.INSTITUTIONAL.value

    # test user(self-forming) group
    group = _random_string(16)
    response = client.post('/pro/v1/groups/create', headers=headers, json={
        'group_description': f"test_{group}_description",
        'group_name': f"test_{group}_name",
        'group_active': False,
        'group_label': f"test_{group}_label",
        'group_type': 'user',
        'group_creator_uuid': user.get('userUuid')
    })
    assert response.status_code == 200
    group_uuid = response.json.get('groupUuid')
    g = GroupManagement.get_group(group_uuid=group_uuid, session=session)
    assert g is not None
    assert g.groupType == GroupTypes.USER.value

    GroupManagement.remove_user_from_group(user_uuid=user.get('userUuid'), group_uuid=group_uuid, session=session)


def test_create_group_with_creator_uuid(client, test_user, headers, load_db):
    session = load_db
    user = test_user

    # test creator does not exist.
    group = _random_string(16)
    response = client.post('/pro/v1/groups/create', headers=headers, json={
        'group_description': f"test_{group}_description",
        'group_name': f"test_{group}_name",
        'group_active': False,
        'group_label': f"test_{group}_label",
        'group_type': 'user',
        'group_creator_uuid': str(uuid.uuid4())
    })
    assert response.status_code == 404

    # test creator exists
    group = _random_string(16)
    response = client.post('/pro/v1/groups/create', headers=headers, json={
        'group_description': f"test_{group}_description",
        'group_name': f"test_{group}_name",
        'group_active': False,
        'group_label': f"test_{group}_label",
        'group_type': 'user',
        'group_creator_uuid': user['userUuid']
    })
    assert response.status_code == 200
    group_uuid = response.json.get('groupUuid')
    g = GroupManagement.get_group(group_uuid=group_uuid, session=session)
    assert g is not None
    assert g.groupType == GroupTypes.USER.value
    assert g.groupMembers[0].isCreator
    assert g.groupCreatorUuid == user['userUuid']

    GroupManagement.remove_user_from_group(user_uuid=user['userUuid'], group_uuid=group_uuid, session=session)


def test_case_upload_group(test_user, create_group, test_group_case, load_db):
    session = load_db
    g = create_group
    test_user_uuid = test_user.get('userUuid')
    case, _ = test_group_case

    # check case in db
    db_case = session.query(Case).filter(Case.case_uuid == case.case_uuid).one_or_none()
    assert db_case.group_uuid == case.group_uuid
    GroupManagement.remove_user_from_group(user_uuid=test_user_uuid, group_uuid=g.groupUuid, session=session)
    session.flush()


def test_get_groups_given_user(client, headers, load_db, test_user, create_group):
    session = load_db
    user = test_user
    group = create_group
    user_uuid = user.get('userUuid')
    group_uuid = group.groupUuid

    response = client.get(f'/pro/v1/admin/users/{user_uuid}/groups',
                          headers=headers)

    # more than 0 groups
    assert response.status_code == 200
    assert type(response.json) is list
    assert len(response.json) == 1

    GroupManagement.remove_user_from_group(user_uuid=user_uuid, group_uuid=group_uuid, session=session)
    session.commit()


def test_get_members_given_group(client, headers, load_db, create_group, test_user):
    session = load_db
    group = create_group
    user = test_user
    group_uuid = group.groupUuid

    user_uuid = user.get('userUuid')
    initial_members = len(group.groupMembers)
    GroupManagement.add_user_to_group(user_uuid=user_uuid, group_uuid=group_uuid, session=session)
    session.commit()

    # group dost not exist
    response = client.get(f'/pro/v1/admin/groups/{uuid.uuid4()}/members',
                          headers=headers)
    assert response.status_code == 404

    # group with members
    response = client.get(f'/pro/v1/admin/groups/{group_uuid}/members',
                          headers=headers)

    assert response.status_code == 200
    assert type(response.json) is list
    assert len(response.json) is initial_members + 1

    GroupManagement.remove_user_from_group(user_uuid=user_uuid, group_uuid=group_uuid, session=session)
    session.commit()


def test_get_all_groups(client, headers, create_group):
    response = client.get('/pro/v1/admin/groups', headers=headers)

    assert response.status_code == 200
    assert type(response.json) is list


def test_add_remove_case(client, headers, create_group, test_user, load_db):
    session = load_db
    group = create_group
    user = test_user
    group_uuid = group.groupUuid
    user_uuid = user.get('userUuid')

    case, _ = create_test_case(
        author_uuid=user_uuid,
        is_paging_case=False,
        language='EN_US',
        title="Case Title",
        caption="Case Caption",
        state=CaseState.APPROVED,
        session=session)

    case2, _ = create_test_case(
        author_uuid=user_uuid,
        is_paging_case=False,
        language='EN_US',
        title="Case Title 2",
        caption="Case Caption 2",
        state=CaseState.APPROVED,
        session=session)

    # group not found
    response = client.post(f'/pro/v1/admin/groups/modify_case',
                           headers=headers,
                           json={
                               "case_uuid": case.case_uuid,
                               "group_uuid": uuid.uuid4(),
                           },
                           query_string={"action": "add_case"})

    assert response.status_code == 404

    # invalid action
    response = client.post(f'/pro/v1/admin/groups/modify_case',
                           headers=headers,
                           json={
                               "case_uuid": case.case_uuid,
                               "group_uuid": group_uuid,
                           },
                           query_string={"action": "invalid_action"})

    assert response.status_code == 422

    # case not found
    response = client.post(f'/pro/v1/admin/groups/modify_case',
                           headers=headers,
                           json={
                               "case_uuid": uuid.uuid4(),
                               "group_uuid": group_uuid,
                           },
                           query_string={"action": "add_case"})

    assert response.status_code == 404

    # add one case
    response = client.post(f'/pro/v1/admin/groups/modify_case',
                           headers=headers,
                           json={
                               "case_uuid": case.case_uuid,
                               "group_uuid": group_uuid,
                           },
                           query_string={"action": "add_case"})

    assert response.status_code == 200

    group_cases = GroupManagement.get_cases_by_group_as_dict(group_uuid, session)
    assert len(group_cases) == 1

    case = group_cases[0]
    case_uuid, case_uuid2 = case['caseUuid'], case2.case_uuid

    # case2 is not belong to the group
    response = client.post(f'/pro/v1/admin/groups/modify_case',
                           headers=headers,
                           json={
                               "case_uuid": case_uuid2,
                               "group_uuid": group_uuid,
                           },
                           query_string={"action": "remove_case"})

    assert response.status_code == 406

    # group is not found
    response = client.post(f'/pro/v1/admin/groups/modify_case',
                           headers=headers,
                           json={
                               "case_uuid": case_uuid,
                               "group_uuid": uuid.uuid4(),
                           },
                           query_string={"action": "remove_case"})

    assert response.status_code == 404

    # case not found
    response = client.post(f'/pro/v1/admin/groups/modify_case',
                           headers=headers,
                           json={
                               "case_uuid": uuid.uuid4(),
                               "group_uuid": group_uuid,
                           },
                           query_string={"action": "remove_case"})

    assert response.status_code == 404

    # remove case from the group
    response = client.post(f'/pro/v1/admin/groups/modify_case',
                           headers=headers,
                           json={
                               "case_uuid": case_uuid,
                               "group_uuid": group_uuid,
                           },
                           query_string={"action": "remove_case"})

    assert response.status_code == 200
    session.commit()
    group_cases = GroupManagement.get_cases_by_group_as_dict(group_uuid, session)
    assert len(group_cases) == 0


def test_get_cases_given_group(client, headers, create_group, test_user, load_db):
    session = load_db
    group = create_group
    user = test_user
    group_uuid = group.groupUuid
    user_uuid = user.get('userUuid')

    case, _ = create_test_case(
        author_uuid=user_uuid,
        is_paging_case=False,
        language='EN_US',
        title="Case Title",
        caption="Case Caption",
        state=CaseState.APPROVED,
        session=session)

    response = client.post(f'/pro/v1/admin/groups/modify_case',
                           headers=headers,
                           json={
                               "case_uuid": case.case_uuid,
                               "group_uuid": group_uuid,
                           },
                           query_string={"action": "add_case"})

    assert response.status_code == 200

    # group not found
    response = client.get(f'/pro/v1/admin/groups/{uuid.uuid4()}/cases',
                          headers=headers)

    assert response.status_code == 404

    # get a list of cases given group
    response = client.get(f'/pro/v1/admin/groups/{group_uuid}/cases',
                          headers=headers)

    assert response.status_code == 200
    assert type(response.json) is list
    assert len(response.json) == 1


def test_import_members_endpoint(client, headers, test_user, test_country, create_group, load_db):
    session = load_db
    group = create_group

    specialty_uuid = session.query(SpecialtyTreeV2.specialty_uuid) \
        .filter(SpecialtyTreeV2.specialty_v2_uuid.isnot(None)) \
        .first()[0]

    country_uuid = test_country.country_uuid

    with open("/tmp/test_import_members.csv", 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(
            ["1184067720", "first", "last", "aaa@aaw.com",
             "f308775b-e103-442a-8ecb-aede67385711", specialty_uuid, str(country_uuid)]
        )

    file = _file_storage("/tmp/test_import_members.csv", "test_import_members.csv")

    # group does not exist
    response = client.post(f'/pro/v1/groups/import_members',
                           data={
                               'group_members_list': file
                           },
                           content_type="multipart/form-data",
                           headers=headers)

    assert response.status_code == 200
    assert response.json['ImportErrorCount'] == 1
    assert len(response.json['ImportErrors']) == 1
    expect_error = 'Group f308775b-e103-442a-8ecb-aede67385711 is not found.'
    assert expect_error in response.json['ImportErrors']

    with open("/tmp/test_import_members.csv", 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["21312", "first", "last", "test@test.com",
                         group.groupUuid, specialty_uuid, str(country_uuid)])
    file = _file_storage("/tmp/test_import_members.csv", "test_import_members.csv")

    # invalid npi number
    response = client.post(f'/pro/v1/groups/import_members',
                           data={
                               'group_members_list': file
                           },
                           content_type="multipart/form-data",
                           headers=headers)
    assert response.status_code == 200
    assert response.json['ImportErrorCount'] == 2
    assert len(response.json['ImportErrors']) == 2
    expect_error = "Invalid npi number 21312."
    assert expect_error in response.json['ImportErrors']

    # valid entry
    with open("/tmp/test_import_members.csv", 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["1003006248", "first", "last", "test@test.com",
                         group.groupUuid, specialty_uuid, str(country_uuid)])
    file = _file_storage("/tmp/test_import_members.csv", "test_import_members.csv")

    response = client.post(f'/pro/v1/groups/import_members',
                           data={
                               'group_members_list': file
                           },
                           content_type="multipart/form-data",
                           headers=headers)

    user_filter = session.query(GroupMemberFilter).filter(GroupMemberFilter.user_email == "test@test.com",
                                                          GroupMemberFilter.group_uuid == group.groupUuid).one_or_none()

    assert response.status_code == 200
    assert response.json['ImportErrorCount'] == 2
    assert len(response.json['ImportErrors']) == 2
    assert response.json['ImportUpdatedCount'] == 1
    assert user_filter is not None
    assert user_filter.user_npi == 1003006248
    assert user_filter.user_first_name == 'first'
    assert user_filter.user_last_name == 'last'
    assert user_filter.tree_uuid == specialty_uuid
    assert user_filter.country_uuid == country_uuid

    # record already exists
    file = _file_storage("/tmp/test_import_members.csv", "test_import_members.csv")

    response = client.post(f'/pro/v1/groups/import_members',
                           data={
                               'group_members_list': file
                           },
                           content_type="multipart/form-data",
                           headers=headers)

    assert response.status_code == 200
    assert response.json['ImportErrorCount'] == 3
    assert len(response.json['ImportErrors']) == 3
    expect_error = f"The group member filter already exists for group_uuid {group.groupUuid} and email test@test.com."
    assert expect_error in response.json['ImportErrors']

    os.remove("/tmp/test_import_members.csv")
    session.query(GroupMemberFilter).filter(GroupMemberFilter.group_uuid == group.groupUuid).delete()


def test_invite_user_to_group(test_user, create_group, load_db):
    session = load_db
    g = create_group
    inviter = create_test_user(session=session)

    # Inviting to inactive group raises exception
    with pytest.raises(GroupInactive):
        invite_members_to_group(user_uid=inviter.user_uid,
                                group_uuid=g.groupUuid,
                                users_uuid=[test_user.get('userUuid')],
                                session=session)

    # Successful invite creates GroupMemberFilter but user is not yet added to the group
    GroupManagement.modify_group(group_uuid=g.groupUuid, group_active=True, session=session)
    res = invite_members_to_group(user_uid=inviter.user_uid,
                                  group_uuid=g.groupUuid,
                                  users_uuid=[test_user.get('userUuid')],
                                  session=session)
    print(res)
    task = res.pop('task')
    task.apply(timeout=10)

    gmf = session.query(GroupMemberFilter) \
        .filter(GroupMemberFilter.group_uuid == g.groupUuid,
                GroupMemberFilter.user_uuid == test_user.get('userUuid')) \
        .one()
    assert gmf
    assert gmf.inviter_uuid == inviter.user_uuid

    gm = session.query(GroupMember) \
        .filter(GroupMember.group_uuid == g.groupUuid,
                GroupMember.user_uuid == test_user.get('userUuid')) \
        .one_or_none()
    assert gm is None
