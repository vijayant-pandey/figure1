import csv
import logging
import uuid

from sqlalchemy.orm import Session

from figure1.common.iterable.api import IterableAPI
from figure1.common.models.db import CommunicationChannel
from figure1.common.models.db import User
from figure1.common.models.db import UserChannelPreferences
from figure1.common.models.db import UserState
from figure1.core import managed_session
from figure1.exceptions import IterableUserNotFound

logger = logging.getLogger('figure1.iterable.command')


@managed_session
def sync_deleted_users(session=None):
    api = IterableAPI()
    if api.iterable_api_disabled:
        logger.error("Api disabled")
        return
    for user in session.query(User).filter(User.deleted_at.isnot(None),
                                           User.email.notlike("deleted-accounts%")).all():
        logger.error("Handling email %s", user.email)
        if user.email is not None:
            try:
                api.get_iterable_user_by_email(email=user.email)
            except IterableUserNotFound:
                logger.info("No user in iterable for deleted user %s", user.email)
                continue
            resp = api.unsubscribe_user_from_all_channels(email=user.email)
            if resp is not None:
                logger.error("User unsubscribed from all channels %s", resp.dict())


@managed_session
def add_channel(channel_id, channel_name, session):
    """
    Given a channel id, return a communication_channel_uuid.  If a channel does not exist for the id, creates it.
    :param channel_id:
    :param channel_name:
    :param session:
    :return:
    """
    c = session.query(CommunicationChannel.communication_channel_uuid) \
        .filter(CommunicationChannel.communication_channel_id == channel_id) \
        .one_or_none()

    if c:
        channel_uuid = c[0]
    else:
        channel_uuid = uuid.uuid4()
        channel = CommunicationChannel()
        channel.communication_channel_uuid = channel_uuid
        channel.communication_channel_name = channel_name
        channel.communication_channel_id = channel_id
        channel.communication_default_setting = True
        session.add(channel)

    return dict(channel_uuid=channel_uuid)


@managed_session
def channel_unsubscribe(data, session=None):
    """
    data is a list of dicts of the form
    {"email": <user_email>,
     "channel_uuid": communication_uuid,
      "channel_id": channel_id}

    One of channel_uuid or channel_id is required, if both are provided, channel_uuid will be tried first.

    :param data:
    :param session:
    :return:
    """
    valid_channel_uuids = list(CommunicationChannel.get_channel_uuids(session))
    channel_uuids_by_channel_id = {}

    no_user_with_email = []
    successful_updates = []
    invalid_communication_uuid = []
    invalid_channel_id = []

    for i in data:
        email = i.get("email", None)
        channel_uuid = i.get("channel_uuid", None)
        channel_id = i.get("channel_id", None)
        if not email:
            continue
        else:
            u = User.get_user_by_email(email=email, session=session, raise_exception=False)
            if not u:
                no_user_with_email.append(email)
                continue
        if channel_uuid and channel_uuid in valid_channel_uuids:
            _unsubscribe_user(channel_uuid=channel_uuid, user_uuid=u.user_uuid, session=session)
            successful_updates.append(email)
            continue

        elif channel_uuid and channel_uuid not in valid_channel_uuids:
            invalid_communication_uuid.append(email)

        if channel_id:
            if channel_id in channel_uuids_by_channel_id:
                channel_uuid = channel_uuids_by_channel_id.get(channel_id)

            else:
                channel_uuid = session.query(CommunicationChannel.communication_channel_uuid) \
                    .filter(CommunicationChannel.communication_channel_id == channel_id) \
                    .one_or_none()
                if channel_uuid:
                    channel_uuid = channel_uuid[0]
                    channel_uuids_by_channel_id.update({channel_id: channel_uuid})
                else:
                    invalid_channel_id.append(email)

            _unsubscribe_user(channel_uuid=channel_uuid, user_uuid=u.user_uuid, session=session)
            successful_updates.append(email)

    return dict(success=successful_updates,
                email_error=no_user_with_email,
                communication_uuid_error=invalid_communication_uuid,
                channel_id_error=invalid_channel_id)


def parse_csv(filename):
    with open(filename, mode='r') as open_file:
        c = csv.DictReader(f=open_file, fieldnames=["email", "channel_uuid", "channel_id"])
        return channel_unsubscribe(data=c)


def _unsubscribe_user(channel_uuid: str,
                      user_uuid: str,
                      session: Session):
    UserChannelPreferences.set_user_preference(user_uuid=user_uuid,
                                               channel_uuid=channel_uuid,
                                               channel_setting=False,
                                               session=session)
    us = UserState()
    us.user_uuid = user_uuid
    us.requires_iterable_sync = True
    session.merge(us)
    session.flush()
