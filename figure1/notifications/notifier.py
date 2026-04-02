import logging

from google.cloud.firestore_v1 import Client
from sqlalchemy.orm import Session

from figure1.common.models.db import User
from figure1.common.types import CaseDraftData
from figure1.common.iterable.api import IterableAPI
from .iterable import IterableEventWrapper
from .iterable import CaseEventData
from .iterable import IterableEvent
from .iterable.events import UserEventData
from .tasks import NotificationEvent
from .iterable.strategies import IterableSendEventStrategy


__all__ = ['IterableNotifier']

logger = logging.getLogger("figure1.notifications.notifier")


class IterableNotifier:
    """
    Given NotificationEvents, this class is responsible for composing and sending the appropriate
    events to iterable.
    """
    _iterable_client: IterableAPI = None

    @classmethod
    def get_iterable_client(cls):
        if cls._iterable_client is None:
            cls._iterable_client = IterableAPI()
        return cls._iterable_client

    def _track_event(self, event_wrapper: IterableEventWrapper):
        client = self.get_iterable_client()
        if client.iterable_api_disabled:
            logger.error("Iterable api is disabled")
            return None
        logger.debug("Sending iterable notification event %s for user %s",
                     event_wrapper.eventName,
                     event_wrapper.userId)
        return client.track_event(event_wrapper=event_wrapper)

    def send_event(self,
                   event: NotificationEvent,
                   session: Session,
                   fs_client: Client = None):
        if event.iterable_event.name not in IterableEvent.__members__:
            logger.error(f"Unhandled iterable event: {event.iterable_event.value}")
            return
        else:
            IterableSendEventStrategy[event.iterable_event.name].value().send(
                event=event, session=session, fs_client=fs_client
            )

    def send_case_draft_event(self,
                              user: User,
                              screen_name: str,
                              case_data: CaseDraftData):
        data = CaseEventData.from_orm(user)
        data.screenName = screen_name
        if case_data.title:
            data.caseTitle = case_data.title
        if case_data.caption:
            data.caseCaption = case_data.caption
        if case_data.caseUid:
            data.draftUid = case_data.caseUid

        return self._track_event(IterableEventWrapper(
            event=IterableEvent.CASE_POST_TRACKING,
            email=data.email,
            data_fields=data.dict(),
            user_uuid=user.user_uuid
        ))

    def send_registration_tracking_event(self,
                                         user: User,
                                         screen_name: str):
        data = UserEventData.from_orm(user)
        data.screenName = screen_name
        return self._track_event(IterableEventWrapper(
            event=IterableEvent.USER_REGISTRATION_TRACKING,
            email=data.email,
            data_fields=data.dict(),
            user_uuid=user.user_uuid
        ))

    def send_marketing_sign_up_event(self, user_uuid: str, session: Session):
        user = User.get_user_by_uuid(user_uuid=user_uuid, session=session, raise_exception=True)
        user_event_data = UserEventData.from_orm(user)
        data_fields = {
            "userUuid": user_event_data.userUuid,
            "email": user_event_data.email,
        }
        return self._track_event(IterableEventWrapper(
            event=IterableEvent.USER_MARKETING_SIGN_UP,
            email=user_event_data.email,
            data_fields=data_fields,
            user_uuid=user_event_data.userUuid,
        ))
