import logging
import uuid

from figure1.common.models.db import UserChannelPreferences, \
    CommunicationSettings, \
    UserCommunicationPreferences,\
    CommunicationGroup,\
    CommunicationChannel
from figure1.common.types import CommunicationMethods, CommunicationTypes
from figure1.core import managed_session

logger = logging.getLogger('figure1.communications')


@managed_session
def migrate_communication_channels(session):
    """
    For each CommunicationSettings with a group matching the CHANNEL type:
        - create a row in r_communication_channels
        - migrate any matching user preferences
        - delete old values
    """

    for cg in session.query(CommunicationGroup) \
            .filter(CommunicationGroup.communication_group_type == CommunicationTypes.CHANNEL) \
            .all():

        for cs in session.query(CommunicationSettings) \
                .filter(CommunicationSettings.communication_group_uuid == cg.communication_group_uuid) \
                .all():

            channel = session.query(CommunicationChannel) \
                .filter(CommunicationChannel.communication_channel_id == cs.communication_iterable_message_type) \
                .one_or_none()
            if channel:
                continue

            channel_uuid = uuid.uuid4()
            channel = CommunicationChannel()
            channel.communication_channel_uuid = channel_uuid
            channel.communication_channel_name = cs.communication_name
            channel.communication_channel_id = cs.communication_iterable_message_type
            channel.communication_default_setting = cs.communication_default_setting
            session.add(channel)
            session.flush()

            for ucp in session.query(UserCommunicationPreferences) \
                    .filter(UserCommunicationPreferences.communication_uuid == cs.communication_uuid) \
                    .all():
                channel_pref = UserChannelPreferences()
                channel_pref.user_uuid = ucp.user_uuid
                channel_pref.communication_channel_uuid = channel.communication_channel_uuid
                channel_pref.communication_setting = ucp.communication_setting
                session.add(channel_pref)

            session.query(UserCommunicationPreferences) \
                   .filter(UserCommunicationPreferences.communication_uuid == cs.communication_uuid) \
                   .delete()

        session.query(CommunicationSettings) \
            .filter(CommunicationSettings.communication_group_uuid == cg.communication_group_uuid) \
            .delete()

    session.query(CommunicationGroup) \
        .filter(CommunicationGroup.communication_group_type == CommunicationTypes.CHANNEL) \
        .delete()
