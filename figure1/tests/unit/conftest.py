import pytest
import uuid
from figure1.common.types import CommunicationTypes, CommunicationMethods
from figure1.common.models.db import User, \
    SpecialtyTreeV2, \
    CommunicationGroup, \
    CommunicationSettings, \
    SpecialtyCommunicationSettings
from figure1.common.helpers import UserManagement, UserDocument
from figure1.tests.utils.user import create_test_user


@pytest.fixture()
def test_user_invalid_email(load_db, test_user, initialize_data):
    session = load_db
    u = User()
    u.user_uuid = test_user.get("userUuid")
    u.email = 'jancardinale@aol.comji'
    return session.merge(u)


@pytest.fixture(scope="module")
def test_user(load_db, initialize_data):
    session = load_db
    diff = session.query(CommunicationSettings) \
        .join(CommunicationGroup, CommunicationGroup.communication_group_uuid ==
              CommunicationSettings.communication_group_uuid) \
        .filter(CommunicationSettings.communication_enabled.is_(True),
                CommunicationGroup.communication_group_type == CommunicationTypes.CONTENT,
                CommunicationGroup.communication_group_name == 'Your Differentials') \
        .first()

    u = create_test_user(session=session)
    specialty = session.query(SpecialtyTreeV2).filter(SpecialtyTreeV2.specialty_v2_uuid.isnot(None)).limit(5).all()

    mgmt = UserManagement(user_uid=u.user_uid, session=session)
    specialty_should_be = None
    for i, s in enumerate(specialty):
        if i == 0:
            mgmt.set_primary_specialty(specialty=s.specialty_uuid)
            session.commit()
        elif i == 2:
            mgmt.set_primary_specialty(specialty=s.specialty_uuid)
            specialty_should_be = s.as_object()
            session.commit()
        else:
            mgmt.set_specialties(specialties=[s.specialty_uuid])
            session.commit()
    user_doc = UserDocument.user_detail(user_uuid=str(mgmt.user.user_uuid), session=session)
    assert user_doc['primarySpecialty']['treeUuid'] == specialty_should_be.treeUuid
    specialty_comm_settings = SpecialtyCommunicationSettings()
    specialty_comm_settings.communication_default_setting = True
    specialty_comm_settings.communication_uuid = diff.communication_uuid
    specialty_comm_settings.tree_uuid = specialty_should_be.treeUuid
    session.merge(specialty_comm_settings)
    session.commit()

    return u.as_dict()


@pytest.fixture(scope="module")
def generate_default_preferences(load_db, initialize_data):
    session = load_db

    activity = CommunicationGroup()
    activity.communication_group_name = 'Test Activity'
    activity.communication_group_description = 'Test Activity Description'
    activity.communication_group_uuid = uuid.uuid4()
    activity.communication_group_type = CommunicationTypes.ACTIVITY
    activity.communication_group_display_order = 1
    session.add(activity)

    transaction = CommunicationGroup()
    transaction.communication_group_name = 'Test Transaction'
    transaction.communication_group_description = 'Test Transaction Description'
    transaction.communication_group_uuid = uuid.uuid4()
    transaction.communication_group_type = CommunicationTypes.TRANSACTIONAL
    transaction.communication_group_display_order = 1
    session.add(transaction)

    content = CommunicationGroup()
    content.communication_group_name = 'Test Content 1'
    content.communication_group_description = 'Test Content Description'
    content.communication_group_uuid = uuid.uuid4()
    content.communication_group_type = CommunicationTypes.CONTENT
    content.communication_group_display_order = 1
    session.add(content)
    session.flush()

    activity_setting = CommunicationSettings()
    activity_setting.communication_group_uuid = activity.communication_group_uuid
    activity_setting.communication_uuid = uuid.uuid4()
    activity_setting.communication_default_setting = True
    activity_setting.communication_name = 'email'
    activity_setting.communication_enabled = True
    activity_setting.communication_iterable_message_type = 14
    activity_setting.communication_display_order = 1
    activity_setting.communication_method = CommunicationMethods.EMAIL
    activity_setting.communication_description = 'Test activity setting'
    session.add(activity_setting)

    transaction_setting = CommunicationSettings()
    transaction_setting.communication_group_uuid = transaction.communication_group_uuid
    transaction_setting.communication_uuid = uuid.uuid4()
    transaction_setting.communication_default_setting = True
    transaction_setting.communication_name = 'email'
    transaction_setting.communication_enabled = True
    transaction_setting.communication_iterable_message_type = 10
    transaction_setting.communication_display_order = 1
    transaction_setting.communication_method = CommunicationMethods.EMAIL
    transaction_setting.communication_description = 'Test transaction setting'
    session.add(transaction_setting)

    content_setting = CommunicationSettings()
    content_setting.communication_group_uuid = content.communication_group_uuid = uuid.uuid4()
    content_setting.communication_uuid = uuid.uuid4()
    content_setting.communication_default_setting = True
    content_setting.communication_name = 'email'
    content_setting.communication_enabled = True
    content_setting.communication_iterable_message_type = 12
    content_setting.communication_display_order = 2
    content_setting.communication_method = CommunicationMethods.EMAIL
    content_setting.communication_description = 'Test content setting'
    session.add(content_setting)
    session.commit()
