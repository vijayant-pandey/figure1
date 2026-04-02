import pytest
from figure1.common.helpers import UserDocument, UserManagement
from figure1.common.types import ProfessionModel
from figure1.common.models.db import ProfessionV2, \
    SpecialtyV2, \
    SpecialtyTreeV2, \
    UserInterest, \
    User

from figure1.common.types import UserInterestV2Model, UpdateUserModel, SpecialtyTreeModel, UserTypes

from figure1.pro.users.domain import create_user_internal, update_user_internal


def create_user_profile(user_uid, session):
    prof_uuid = session.query(SpecialtyTreeV2).filter(SpecialtyTreeV2.specialty_v2_uuid.is_(None),
                                                      SpecialtyTreeV2.subspecialty_uuid.is_(None)).first()
    create_user_internal(user_uid=user_uid,
                         session=session,
                         profession_uuid=prof_uuid.specialty_uuid,
                         first_name='test',
                         last_name='user',
                         email=user_uid + '@figure1.com')
    user_mgmt = UserManagement(user_uid=user_uid, session=session)
    assert user_mgmt is not None
    return user_mgmt


def test_generate_profession_only_user_profile(load_db):
    """
    Create a user with only a profession, ensure that we can generate a sane object from it
    :param load_db:
    :return:
    """
    session = load_db
    user_mgmt = create_user_profile(user_uid='test_generate_user_doc_uid', session=session)
    ud = UserDocument.get_full_profile(user_uuid=user_mgmt.user.user_uuid, session=session)
    assert ud.get("professionUuid") is not None
    assert ud.get("professionName") is not None


def test_generate_user_specialties(load_db, user_specialty):
    """
    Given a user with only a profession set, the mfy specialties list should return an empty list. When adding a
    tree uuid, the list should contain the specialties in that tree
    :param load_db:
    :return:
    """
    session = load_db
    so = user_specialty

    assert isinstance(so, SpecialtyTreeModel)

    user_mgmt = create_user_profile(user_uid='test_generate_user_doc_uid', session=session)
    s_list = UserDocument.get_made_for_you_specialties(user_uuid=user_mgmt.user.user_uuid, session=session)

    # Only profession is set, so no specialties should be returned
    assert s_list == []

    user_mgmt.set_specialties(specialties=[so.treeUuid])
    session.flush()

    # Specialties have been set, now the specialty uuids in both the specialty and subspecialties should be returned
    s_list = UserDocument.get_made_for_you_specialties(user_uuid=user_mgmt.user.user_uuid, session=session)
    if so.specialty:
        assert so.specialty.specialtyUuid in s_list
    if so.subspecialty:
        assert so.subspecialty.specialtyUuid in s_list


def test_generate_user_interests(load_db, user_specialty):
    session = load_db
    specialty = session.query(SpecialtyV2).limit(10).all()
    st = user_specialty

    text_interest = []
    for i in specialty:
        text_interest.append(str(i.specialty_uuid))

    user_mgmt = create_user_profile(user_uid='test_generate_user_doc_uid', session=session)
    user_mgmt.set_specialties(specialties=[st.treeUuid])
    t = update_user_internal(user_uid='test_generate_user_doc_uid',
                             user_update=UpdateUserModel(interests=text_interest),
                             session=session).pop('task')
    t.apply()
    mfy_spec = UserDocument.get_made_for_you_specialties(user_uuid=user_mgmt.user.user_uuid, session=session)
    if st.specialty:
        assert st.specialty.specialtyUuid in mfy_spec

    if st.subspecialty:
        assert st.subspecialty.specialtyUuid in mfy_spec

    for i in text_interest:
        assert i in mfy_spec

    interest = UserInterest.get_user_entry(user_uuid=user_mgmt.user.user_uuid, session=session)
    for i in interest:
        assert isinstance(i, UserInterestV2Model)


def test_user_profile_generation(load_db):
    session = load_db
    user_mgmt = create_user_profile(user_uid='test_generate_user_doc_uid_pg', session=session)
    update_user = UpdateUserModel(userDisplayName='my_display_name',
                                  avatar='https://www.google.ca',
                                  profileDisplayName='MyProfileName',
                                  userCustomSchool='Kindergarten',
                                  userCustomSpecialty='Shark Studies')

    user_mgmt.update_user_profile(update_user)
    user_mgmt.set_custom_data(update_user)
    session.flush()
    user_doc = UserDocument.user_detail(user_uuid=str(user_mgmt.user.user_uuid), session=session)
    assert user_doc.get('displayName') == 'my_display_name'
    assert user_doc.get('avatar') == 'https://www.google.ca'

    # Manually change the user type to institutional and make sure the profile name changes
    u = session.query(User).filter(User.user_uuid == user_mgmt.user.user_uuid).one()
    u.user_type = UserTypes.FIGURE1_INSTITUTIONAL
    session.add(u)
    session.flush()
    user_doc = UserDocument.user_detail(user_uuid=str(user_mgmt.user.user_uuid), session=session)
    assert user_doc.get('displayName') == 'my_display_name'
    assert user_doc.get('avatar') == 'https://www.google.ca'
    assert user_doc.get('profileDisplayName') == 'MyProfileName'

    elastic_user_document = UserDocument.elasticsearch_user_detail(user_uuid=str(user_mgmt.user.user_uuid),
                                                                   session=session).to_dict()

    assert elastic_user_document.get('userCustomSchool') == 'Kindergarten'
    assert elastic_user_document.get('userCustomSpecialty') == 'Shark Studies'


def test_user_profile_null_avatar(load_db):
    """
    Users should always have a an avatar field, even if null
    :param load_db:
    :return:
    """
    session = load_db
    user_mgmt = create_user_profile(user_uid='test_generate_user_doc_uid_np', session=session)
    user_mgmt.update_user_profile(UpdateUserModel(userDisplayName='my_display_name'))
    session.flush()
    user_doc = UserDocument.user_detail(user_uuid=str(user_mgmt.user.user_uuid), session=session)
    assert user_doc.get('displayName') == 'my_display_name'
    assert 'avatar' in user_doc and user_doc['avatar'] is None
