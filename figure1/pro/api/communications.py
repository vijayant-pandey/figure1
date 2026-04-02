import logging

from celery import Celery
from pydantic import validate_email
from sqlalchemy.orm import Session

from figure1.common.iterable import sync_anonymous_user_comm_preferences_task
from figure1.common.models.db import AnonymousEmailSubscriber
from figure1.common.models.db import CommunicationGroup
from figure1.common.models.db import CommunicationSettings
from figure1.common.models.db import User
from figure1.common.models.db import UserCommunicationPreferences
from figure1.core import managed_session
from figure1.events import UserEvents
from figure1.exceptions import CommunicationSettingNotFound

celery = Celery('figure1')
celery.config_from_object('celeryconfig')
logger = logging.getLogger('figure1.api.communications')


@managed_session
def get_differentials(session: Session):
    differential_uuid = CommunicationGroup.get_differential_uuid(session=session)
    for s in session.query(CommunicationSettings) \
            .filter(CommunicationSettings.communication_group_uuid == differential_uuid) \
            .all():
        yield {'uuid': s.communication_uuid,
               'name': s.communication_name}


@managed_session
def email_subscribe(email: str,
                    communication_uuids: [str],
                    session: Session):
    validate_email(email)
    for uuid in communication_uuids:
        cs = session.query(CommunicationSettings).get(uuid)
        if not cs:
            raise CommunicationSettingNotFound(communication_uuid=uuid,
                                               msg=f"Invalid uuid: {uuid}")

    u = User.get_user_by_email(email=email, session=session)
    if u:
        for uuid in communication_uuids:
            cs = session.query(CommunicationSettings).get(uuid)
            usc = UserCommunicationPreferences()
            usc.user_uuid = u.user_uuid
            usc.communication_uuid = cs.communication_uuid
            usc.communication_setting = True
            session.merge(usc)
        session.flush()
        UserEvents.USER_COMM_PREFS_UPDATED(user_uuid=u.user_uuid, session=session)

    else:
        u = AnonymousEmailSubscriber()
        u.email = email
        u = session.merge(u)
        session.flush()
        sync_anonymous_user_comm_preferences_task.delay(email=email,
                                                        user_uuid=str(u.user_uuid),
                                                        subscribed_uuids=communication_uuids)
