import uuid

from figure1.common.models.db import CommunicationGroup,\
    CommunicationSettings,\
    UserCommunicationPreferences, \
    CommunicationChannel,\
    UserChannelPreferences
from figure1.common.types import CommunicationTypes, CommunicationMethods
from figure1.tools.communications import migrate_communication_channels


def test_migrate(test_user, load_db):
    session = load_db

    group_uuid = uuid.uuid4()
    cg = CommunicationGroup()
    cg.communication_group_uuid = group_uuid
    cg.communication_group_display_order = 1000
    cg.communication_group_type = CommunicationTypes.CHANNEL
    cg.communication_group_description = "Channel Group 1"
    cg.communication_group_name = "Channel Group 1"
    session.add(cg)
    session.flush()

    setting_uuid = uuid.uuid4()
    cs = CommunicationSettings()
    cs.communication_iterable_message_type = "12345"
    cs.communication_method = CommunicationMethods.CHANNEL
    cs.communication_default_setting = True
    cs.communication_uuid = setting_uuid
    cs.communication_group_uuid = group_uuid
    cs.communication_enabled = True
    cs.communication_name = f"Channel Setting 1"
    cs.communication_description = f"Channel Setting 1"
    cs.communication_display_order = 1000
    session.add(cs)
    session.flush()

    ucp = UserCommunicationPreferences()
    ucp.user_uuid = test_user.get('userUuid')
    ucp.communication_uuid = setting_uuid
    ucp.communication_setting = False
    session.add(ucp)
    session.commit()

    migrate_communication_channels()

    # Ensure new channel and pref is created
    channel = session.query(CommunicationChannel) \
        .filter(CommunicationChannel.communication_channel_id == "12345") \
        .one()
    assert channel.communication_default_setting is True
    assert channel.communication_channel_name == "Channel Setting 1"

    user_channel_pref = session.query(UserChannelPreferences) \
        .filter(UserChannelPreferences.communication_channel_uuid == channel.communication_channel_uuid) \
        .one()
    assert user_channel_pref.communication_setting is False

    # Ensure old channel types are removed
    groups = session.query(CommunicationGroup) \
        .filter(CommunicationGroup.communication_group_type == CommunicationTypes.CHANNEL) \
        .all()
    assert len(groups) == 0
    settings = session.query(CommunicationSettings) \
        .filter(CommunicationSettings.communication_method == CommunicationMethods.CHANNEL) \
        .all()
    assert len(settings) == 0
    user_prefs = session.query(UserCommunicationPreferences) \
        .filter(UserCommunicationPreferences.communication_uuid == setting_uuid) \
        .all()
    assert len(user_prefs) == 0
