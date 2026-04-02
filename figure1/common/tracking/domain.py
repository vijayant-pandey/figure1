import logging

from datetime import datetime, timezone
from figure1.core import managed_session
from figure1.events import UserEvents

logger = logging.getLogger("figure1.pro.tracking")


@managed_session
def set_last_seen(user_uuid, session=None):
    """
    Given a user_uid, set the last seen date to now. This only updates the date locally, a scheduled task runs every 12
    hours to update all last_seen events.
    This is updated when a feed is updated or generated, or if a comment is posted. It also has an endpoint that can
    be called from the app.
    :param user_uuid: Required, but only used if user_object either doesn't match what we need or isn't passed.
    :param session:
    :return:
    """
    UserEvents.USER_STATE_UPDATE(user_uuid=user_uuid, session=session, last_seen=datetime.now(tz=timezone.utc))
