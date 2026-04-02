import logging
from datetime import datetime
from datetime import timedelta
from typing import Optional

from google.cloud.firestore_v1 import Client
from pydantic import ValidationError
from sqlalchemy.orm import Session

from figure1.cache_config import cache_region
from figure1.common.models.db import Case
from figure1.common.models.db import User
from figure1.common.models.db import UserNotification
from figure1.common.models.db import ActivityReminder
from figure1.notifications.event_generators import NotificationEvent
from figure1.notifications.event_generators import get_notifications_accepted_answer_not_chosen
from figure1.notifications.event_generators import get_notifications_accepted_answer_deleted
from figure1.notifications.event_generators import get_notifications_paging_case
from figure1.notifications.event_generators import get_notifications_user_status_changed
from figure1.notifications.event_generators import get_notifications_comment_delete
from figure1.notifications.event_generators import get_notifications_new_comment
from figure1.notifications.event_generators import get_notifications_case_state_change
from figure1.notifications.event_generators import get_notifications_case_reaction
from figure1.notifications.event_generators import get_notifications_new_follower
from figure1.notifications.event_generators import get_notifications_case_update
from figure1.notifications.event_generators import get_notifications_cme_completed
from figure1.notifications.event_generators import get_notifications_new_case
from figure1.notifications.event_generators import get_notifications_activity_reminder
from figure1.notifications.event_generators import get_notifications_not_chosen_diagnosis_cases
from figure1.notifications.event_generators import get_notifications_profession_change_approved
from figure1.notifications.event_generators import get_notifications_group_invite
from figure1.notifications.event_generators import get_notifications_group_invite_accepted
from figure1.notifications.event_generators import get_notifications_new_accepted_answer
from figure1.notifications.notifier import IterableNotifier
from figure1.common.types import ScreenTrackingData
from figure1.common.types import RegistrationSections
from figure1.common.types import UNKNOWN_SCREEN
from figure1.common.types import CasePostingScreens
from figure1.notifications.iterable import NonPublicIterableEvents
from figure1.common.types.notification import NonPublicNotificationTypes
from figure1.core import TaskBase
from figure1.core import FirebaseTaskBase
from figure1.core import celery_app
from figure1.exceptions import CaseNotFound
from figure1.exceptions import UserNotFound
from figure1.exceptions import IterableAPIException
import time

logger = logging.getLogger("figure1.notifications.tasks")


__all__ = [
  'log_case_draft_task',
  'log_registration_activity_task',
  'log_case_state_changed_task',
  'notify_all_users_of_new_case_task',
  'log_case_update_task',
  'notify_user_of_new_follower_task',
  'log_reaction_and_notify_user_task',
  'send_event_cme_completed_to_user_task',
  'log_comment_and_notify_task',
  'notifies_users_of_new_accepted_answer_task',
  'notifies_users_of_accepted_answer_deleted_task',
  'notifies_users_of_accepted_answer_not_chosen_task',
  'log_comment_delete_and_notify_task',
  'log_user_status_changed_and_notify_user_task',
  'notify_specialty_users_of_paging_case_task',
  'notify_users_of_not_chosen_diagnosis_cases_task',
  'notify_users_activity_reminder_task',
  'notify_profession_changed_approved_task',
  'notify_user_of_group_invite_task',
  'notify_group_invite_accepted_task',
  'send_marketing_sign_up_event_task',
]


class NotifierTaskBase(TaskBase):
    _iterable = None

    @property
    def iterable(self):
        if self._iterable is None:
            self._iterable = IterableNotifier()
        return self._iterable


def _validate(notification_event: NotificationEvent, session):
    if not isinstance(notification_event, NotificationEvent):
        logger.info("notification_event is not an instance of NotificationEvent")
        return False

    case_uuid = notification_event.case_uuid
    iterable_event_type = notification_event.iterable_event
    user_notification_type = notification_event.user_notification
    if case_uuid:
        try:
            case = Case.get_case(case_uuid=case_uuid, session=session, raise_exception=True)
        except CaseNotFound:
            logger.info("Could not find the case: %s", case_uuid)
            return False

        if case.is_anonymous:
            if iterable_event_type in (each_event.value for each_event in NonPublicIterableEvents):
                return False
            if user_notification_type in (each_type.value for each_type in NonPublicNotificationTypes):
                return False

    return True


def _handle_notification_event(notification_event: NotificationEvent,
                               session: Session,
                               iterable_notifier: IterableNotifier,
                               fs_client: Client = None):
    if not _validate(notification_event, session):
        return

    try:
        User.get_user_by_uuid(user_uuid=notification_event.user_uuid, session=session, raise_exception=True)
    except UserNotFound:
        return

    if notification_event.case_uuid and notification_event.only_notify_privately:
        try:
            case = Case.get_case(case_uuid=notification_event.case_uuid, session=session, raise_exception=True)
        except CaseNotFound:
            return
        if case.content[0] and case.content[0].features.public_notifications_enabled is False:
            return

    if notification_event.user_notification:
        UserNotification.create(notification_type=notification_event.user_notification,
                                user_uuid=notification_event.user_uuid,
                                source_uuid=notification_event.source_uuid,
                                case_uuid=notification_event.case_uuid,
                                comment_uuid=notification_event.comment_uuid,
                                group_uuid=notification_event.group_uuid,
                                session=session)
    if notification_event.iterable_event:
        try:
            iterable_notifier.send_event(event=notification_event,
                                         session=session,
                                         fs_client=fs_client)
        except IterableAPIException as ie:
            if ie.status == 'InvalidEmailAddressError':
                logger.info("Could not track iterable event for user %s due to invalid email: %s",
                            notification_event.user_uuid, ie)
        except ValidationError as ve:
            logger.info("Could not track iterable event for user %s due to validation error: %s",
                        notification_event.user_uuid, ve)


@celery_app.task(bind=True,
                 base=NotifierTaskBase,
                 name='figure1.backend.log_case_draft_task')
def log_case_draft_task(self: NotifierTaskBase,
                        user_uid: str,
                        data: ScreenTrackingData):
    """
    Sends iterable events related to case draft tracking
    """
    log_case_draft(user_uid=user_uid,
                   data=data,
                   session=self.session,
                   iterable=self.iterable)


def log_case_draft(user_uid: str,
                   data: ScreenTrackingData,
                   session: Session,
                   iterable: IterableNotifier):
    user = User.get_user_by_uid(user_uid=user_uid, session=session, raise_exception=True)
    if data.screenId in CasePostingScreens.draft_list():
        return iterable.send_case_draft_event(user=user, screen_name=data.screenId, case_data=data.caseDraftData)


@celery_app.task(bind=True,
                 base=NotifierTaskBase,
                 name='figure1.backend.log_registration_activity_task')
def log_registration_activity_task(self: NotifierTaskBase,
                                   user_uid: str,
                                   screen_id: str = UNKNOWN_SCREEN):
    """
    Sends iterable events related to registration activity tracking
    """
    log_registration_activity(user_uid=user_uid,
                              screen_id=screen_id,
                              session=self.session,
                              iterable=self.iterable)


def log_registration_activity(user_uid: str,
                              session: Session,
                              iterable: IterableNotifier,
                              screen_id: str = UNKNOWN_SCREEN):
    user = User.get_user_by_uid(user_uid=user_uid, session=session, raise_exception=True)
    if screen_id == 'registrationStarted':
        print('Delaying registrationStarted Iterable event for 60 seconds...')
        time.sleep(60)
    if screen_id in RegistrationSections.sync_only_list():
        return iterable.send_registration_tracking_event(user, screen_id)
    else:
        logger.error("Screen id %s not recognized", screen_id)


@celery_app.task(bind=True,
                 base=TaskBase,
                 max_retries=5,
                 name='figure1.backend.send_marketing_sign_up_event_task')
def send_marketing_sign_up_event_task(self, user_uuid: str):
    IterableNotifier().send_marketing_sign_up_event(user_uuid=user_uuid, session=self.session)


@celery_app.task(bind=True,
                 base=FirebaseTaskBase,
                 name='figure1.backend.log_case_state_changed_task')
def log_case_state_changed_task(self: FirebaseTaskBase,
                                case_uuid: str,
                                moderator_uid: Optional[str] = None,
                                suppress_user_notification: bool = True):
    """
    Handles notifying the case author on case state change.
    """
    log_case_state_changed(case_uuid=case_uuid,
                           moderator_uid=moderator_uid,
                           suppress_user_notification=suppress_user_notification,
                           session=self.session,
                           iterable=IterableNotifier(),
                           fs_client=self.fs_client)


def log_case_state_changed(case_uuid: str,
                           moderator_uid: Optional[str],
                           session: Session,
                           iterable: IterableNotifier,
                           fs_client: Client,
                           suppress_user_notification: bool = True):
    for n in get_notifications_case_state_change(case_uuid=case_uuid,
                                                 moderator_uid=moderator_uid,
                                                 suppress_user_notification=suppress_user_notification,
                                                 session=session):
        _handle_notification_event(notification_event=n,
                                   session=session,
                                   iterable_notifier=iterable,
                                   fs_client=fs_client)


@celery_app.task(bind=True,
                 base=NotifierTaskBase,
                 name='figure1.backend.notify_all_users_of_new_case_task')
def notify_all_users_of_new_case_task(self: NotifierTaskBase, case_uuid: str):
    """
    Handles notifications related to a new case approval:
      - Notifies followers of the case author
      - Notifiers users who saved another case from the case author
      - Notifies user who is a member of a Case Group
    """
    notify_all_users_of_new_case(case_uuid=case_uuid,
                                 session=self.session,
                                 iterable=self.iterable)


def notify_all_users_of_new_case(case_uuid: str,
                                 session: Session,
                                 iterable: IterableNotifier):
    for n in get_notifications_new_case(case_uuid=case_uuid, session=session):
        _handle_notification_event(notification_event=n, session=session, iterable_notifier=iterable)


@celery_app.task(bind=True,
                 base=NotifierTaskBase,
                 name='figure1.backend.log_case_update_task')
def log_case_update_task(self: NotifierTaskBase,
                         case_uuid: str,
                         previous_label: str,
                         current_label: str,
                         author_uuid: str,
                         is_diagnosis: bool):
    """
    Handles notifications for a new case update:
        - Notifies users who saved the case
    """
    log_case_update(case_uuid=case_uuid,
                    previous_label=previous_label,
                    current_label=current_label,
                    author_uuid=author_uuid,
                    is_diagnosis=is_diagnosis,
                    session=self.session,
                    iterable=self.iterable)


def log_case_update(case_uuid: str,
                    previous_label: str,
                    current_label: str,
                    author_uuid: str,
                    is_diagnosis: bool,
                    session: Session,
                    iterable: IterableNotifier):
    for n in get_notifications_case_update(case_uuid=case_uuid, author_uuid=author_uuid,
                                           is_diagnosis=is_diagnosis, previous_label=previous_label,
                                           current_label=current_label, session=session):
        _handle_notification_event(notification_event=n,
                                   session=session,
                                   iterable_notifier=iterable)


@celery_app.task(bind=True,
                 base=NotifierTaskBase,
                 name='figure1.backend.notify_user_of_new_follower_task')
def notify_user_of_new_follower_task(self: NotifierTaskBase,
                                     follower_uuid: str,
                                     target_user_uuid: str):
    """
    Handles notifying a user when another user has followed them
    """
    notify_user_of_new_follower(follower_uuid=follower_uuid,
                                target_user_uuid=target_user_uuid,
                                session=self.session,
                                iterable=self.iterable)


def notify_user_of_new_follower(follower_uuid: str,
                                target_user_uuid: str,
                                session: Session,
                                iterable: IterableNotifier):
    for n in get_notifications_new_follower(follower_uuid=follower_uuid, target_user_uuid=target_user_uuid):
        _handle_notification_event(notification_event=n, session=session, iterable_notifier=iterable)


@celery_app.task(bind=True,
                 base=NotifierTaskBase,
                 name='figure1.backend.log_reaction_and_notify_user_task')
def log_reaction_and_notify_user_task(self: NotifierTaskBase,
                                      user_uuid: str,
                                      case_uuid: str):
    """
    Handles notifications to the case author when another user has reacted to their case
    """
    log_reaction_and_notify_user(user_uuid=user_uuid,
                                 case_uuid=case_uuid,
                                 session=self.session,
                                 iterable=self.iterable)


def log_reaction_and_notify_user(user_uuid: str,
                                 case_uuid: str,
                                 session: Session,
                                 iterable: IterableNotifier):
    for n in get_notifications_case_reaction(case_uuid=case_uuid,
                                             user_uuid=user_uuid,
                                             session=session):
        _handle_notification_event(notification_event=n, session=session, iterable_notifier=iterable)


@celery_app.task(bind=True,
                 base=NotifierTaskBase,
                 name='figure1.backend.send_event_cme_completed_to_user_task')
def send_event_cme_completed_to_user_task(self: NotifierTaskBase,
                                          case_uuid: str,
                                          completed_at: datetime,
                                          user_uuid: str,
                                          is_case_cme: bool = False):
    """
    Sends an iterable event when a user has completed a CME activity.
    """
    send_event_cme_completed_to_user(case_uuid=case_uuid,
                                     completed_at=completed_at,
                                     user_uuid=user_uuid,
                                     session=self.session,
                                     iterable=self.iterable,
                                     is_case_cme=is_case_cme)


def send_event_cme_completed_to_user(case_uuid: str,
                                     completed_at: datetime,
                                     user_uuid: str,
                                     session: Session,
                                     iterable: IterableNotifier,
                                     is_case_cme: bool = False):
    for n in get_notifications_cme_completed(case_uuid=case_uuid, user_uuid=user_uuid,
                                             completed_at=completed_at, is_case_cme=is_case_cme):
        _handle_notification_event(notification_event=n,
                                   session=session,
                                   iterable_notifier=iterable)


@celery_app.task(bind=True,
                 base=NotifierTaskBase,
                 name='figure1.backend.log_comment_and_notify_task')
def log_comment_and_notify_task(self: NotifierTaskBase,
                                user_uuid: str,
                                content_uuid: str,
                                comment_uuid: str):
    """
    Handles notifications for a new comment:
        - Notifies the case author
        - Notifies users who saved the case
        - If the comment is a reply, notifies the author of the parent comment
    """
    log_comment_and_notify(user_uuid=user_uuid,
                           content_uuid=content_uuid,
                           comment_uuid=comment_uuid,
                           session=self.session,
                           iterable=self.iterable)


def log_comment_and_notify(user_uuid: str,
                           content_uuid: str,
                           comment_uuid: str,
                           session: Session,
                           iterable: IterableNotifier):
    for n in get_notifications_new_comment(commenter_uuid=str(user_uuid),
                                           content_uuid=content_uuid,
                                           comment_uuid=comment_uuid,
                                           session=session):
        _handle_notification_event(notification_event=n, session=session, iterable_notifier=iterable)


@celery_app.task(bind=True,
                 base=NotifierTaskBase,
                 name='figure1.backend.notifies_users_of_new_accepted_answer_task')
def notifies_users_of_new_accepted_answer_task(self: NotifierTaskBase,
                                               source_user_uuid: str,
                                               comment_uuid: str,
                                               case_uuid: str):
    """
    Handles notifications for a new accepted answer:
        - Notifies the accepted answer author
        - Notifies users who saved/liked/commented the case
    """
    notifies_users_of_new_accepted_answer(source_user_uuid=source_user_uuid,
                                          comment_uuid=comment_uuid,
                                          case_uuid=case_uuid,
                                          session=self.session,
                                          iterable=self.iterable)


def notifies_users_of_new_accepted_answer(source_user_uuid: str,
                                          comment_uuid: str,
                                          case_uuid: str,
                                          session: Session,
                                          iterable: IterableNotifier):
    for n in get_notifications_new_accepted_answer(source_user_uuid=source_user_uuid, comment_uuid=comment_uuid,
                                                   case_uuid=case_uuid, session=session):
        _handle_notification_event(notification_event=n, session=session, iterable_notifier=iterable)


@celery_app.task(bind=True,
                 base=NotifierTaskBase,
                 name='figure1.backend.notifies_users_of_accepted_answer_deleted_task')
def notifies_users_of_accepted_answer_deleted_task(self: NotifierTaskBase,
                                                   source_user_uuid: str,
                                                   comment_uuid: str,
                                                   case_uuid: str):
    """
    Handles notifications for a deleted accepted answer:
        - Notifies the accepted answer author
    """
    notifies_users_of_accepted_answer_deleted(source_user_uuid=source_user_uuid,
                                              comment_uuid=comment_uuid,
                                              case_uuid=case_uuid,
                                              session=self.session,
                                              iterable=self.iterable)


@celery_app.task(bind=True,
                 base=NotifierTaskBase,
                 name='figure1.backend.notifies_users_of_accepted_answer_not_chosen_task')
def notifies_users_of_accepted_answer_not_chosen_task(self: NotifierTaskBase, case_uuid: str):
    """
    Handles prompt for accepted answer notification:
        - Notifies the case author
    """
    notifies_users_of_accepted_answer_not_chosen(case_uuid=case_uuid,
                                                 session=self.session,
                                                 iterable=self.iterable)


def notifies_users_of_accepted_answer_deleted(source_user_uuid: str,
                                              comment_uuid: str,
                                              case_uuid: str,
                                              session: Session,
                                              iterable: IterableNotifier):
    for n in get_notifications_accepted_answer_deleted(source_user_uuid=source_user_uuid, comment_uuid=comment_uuid,
                                                       case_uuid=case_uuid, session=session):
        _handle_notification_event(notification_event=n, session=session, iterable_notifier=iterable)


def notifies_users_of_accepted_answer_not_chosen(case_uuid: str,
                                                 session: Session,
                                                 iterable: IterableNotifier):
    for n in get_notifications_accepted_answer_not_chosen(case_uuid=case_uuid, session=session):
        _handle_notification_event(notification_event=n, session=session, iterable_notifier=iterable)


@celery_app.task(bind=True,
                 base=NotifierTaskBase,
                 name='figure1.backend.log_comment_delete_and_notify_task')
def log_comment_delete_and_notify_task(self: NotifierTaskBase,
                                       comment_uuid: str,
                                       author_uuid: str,
                                       moderator_uuid: str):
    """
    Handles notifying the comment author for a deleted comment
    """
    log_comment_delete_and_notify(comment_uuid=comment_uuid,
                                  author_uuid=author_uuid,
                                  moderator_uuid=moderator_uuid,
                                  session=self.session,
                                  iterable=self.iterable)


def log_comment_delete_and_notify(comment_uuid: str,
                                  author_uuid: str,
                                  moderator_uuid: str,
                                  iterable: IterableNotifier,
                                  session: Session):
    for n in get_notifications_comment_delete(comment_uuid=comment_uuid,
                                              author_uuid=author_uuid,
                                              moderator_uuid=moderator_uuid,
                                              session=session):
        _handle_notification_event(notification_event=n, session=session, iterable_notifier=iterable)


@celery_app.task(bind=True,
                 base=NotifierTaskBase,
                 name='figure1.backend.log_user_status_changed_and_notify_user_task')
def log_user_status_changed_and_notify_user_task(self: NotifierTaskBase, user_uuid: str, moderator_uid: str):
    """
    Sends an iterable event for a verification state change
    """
    log_user_status_changed_and_notify_user(user_uuid=user_uuid,
                                            moderator_uid=moderator_uid,
                                            session=self.session,
                                            iterable=self.iterable)


def log_user_status_changed_and_notify_user(user_uuid: str,
                                            session: Session,
                                            iterable: IterableNotifier,
                                            moderator_uid: str = None):
    key = str(user_uuid) + '.' + "verification_state_change"
    cache_region.delete(key=key)
    for n in get_notifications_user_status_changed(user_uuid=user_uuid,
                                                   moderator_uid=moderator_uid,
                                                   session=session):
        _handle_notification_event(notification_event=n, session=session, iterable_notifier=iterable)


@celery_app.task(bind=True,
                 base=NotifierTaskBase,
                 name='figure1.backend.notify_specialty_users_of_paging_case_task')
def notify_specialty_users_of_paging_case_task(self: NotifierTaskBase, case_uuid: str):
    """
    Handles notifications for a paging case approval:
     - Notifies users who match the paging case's specialty and subspecialty
     - Notifies users who math the paging case's specialty only
    """
    notify_specialty_users_of_paging_case(case_uuid=case_uuid, session=self.session, iterable=self.iterable)


def notify_specialty_users_of_paging_case(case_uuid: str, session: Session, iterable: IterableNotifier):
    for n in get_notifications_paging_case(case_uuid=case_uuid, session=session):
        _handle_notification_event(notification_event=n,
                                   session=session,
                                   iterable_notifier=iterable)


@celery_app.task(bind=True,
                 base=NotifierTaskBase,
                 name='figure1.backend.notify_users_of_not_chosen_diagnosis_cases_task')
def notify_users_of_not_chosen_diagnosis_cases_task(self: NotifierTaskBase):
    """
    Send notification to reminder case authors to submit a diagnosis for their case.
    """
    notify_users_of_not_chosen_diagnosis_cases(session=self.session, iterable=self.iterable)


def notify_users_of_not_chosen_diagnosis_cases(session: Session, iterable: IterableNotifier):
    for n in get_notifications_not_chosen_diagnosis_cases(session=session):
        _handle_notification_event(notification_event=n,
                                   session=session,
                                   iterable_notifier=iterable)


@celery_app.task(bind=True,
                 base=NotifierTaskBase,
                 name='figure1.backend.activity_reminder_notification')
def notify_users_activity_reminder_task(self: NotifierTaskBase):
    """
    Send a notification to any user who has unread user notifications.
    """
    notify_users_activity_reminder(session=self.session, iterable=self.iterable)


def notify_users_activity_reminder(session: Session, iterable: IterableNotifier):
    for n in get_notifications_activity_reminder(timeframe=timedelta(days=2), session=session):
        _handle_notification_event(notification_event=n, session=session, iterable_notifier=iterable)
        ActivityReminder.update_last_sent(session=session, user_uuid=n.user_uuid)


@celery_app.task(bind=True,
                 base=NotifierTaskBase,
                 name='figure1.backend.notify_profession_changed_approved')
def notify_profession_changed_approved_task(self: NotifierTaskBase,
                                            user_uuid: str):
    notify_profession_changed_approved(user_uuid=user_uuid,
                                       session=self.session,
                                       iterable=self.iterable)


def notify_profession_changed_approved(user_uuid: str,
                                       session: Session,
                                       iterable: IterableNotifier):
    for n in get_notifications_profession_change_approved(user_uuid=user_uuid):
        _handle_notification_event(notification_event=n,
                                   session=session,
                                   iterable_notifier=iterable)


@celery_app.task(bind=True,
                 base=NotifierTaskBase,
                 name='figure1.backend.notify_group_invite')
def notify_user_of_group_invite_task(self: NotifierTaskBase,
                                     group_filter_uuid: str):
    """
    Sends a notification to a user who was invited to a group
    """
    notify_user_of_group_invite(group_filter_uuid=group_filter_uuid,
                                session=self.session,
                                iterable=self.iterable)


def notify_user_of_group_invite(group_filter_uuid: str,
                                session: Session,
                                iterable: IterableNotifier):
    for n in get_notifications_group_invite(group_filter_uuid=group_filter_uuid, session=session):
        _handle_notification_event(notification_event=n, session=session, iterable_notifier=iterable)


@celery_app.task(bind=True,
                 base=NotifierTaskBase,
                 name='figure1.backend.notify_group_invite_accepted')
def notify_group_invite_accepted_task(self: NotifierTaskBase,
                                      group_uuid: str,
                                      user_uuid: str):
    """
    Sends a notification to the inviter and group creator when a user accepts an invite to join a group
    """
    notify_group_invite_accepted(group_uuid=group_uuid,
                                 user_uuid=user_uuid,
                                 session=self.session,
                                 iterable=self.iterable)


def notify_group_invite_accepted(group_uuid: str,
                                 user_uuid: str,
                                 session: Session,
                                 iterable: IterableNotifier):
    for n in get_notifications_group_invite_accepted(group_uuid=group_uuid,
                                                     user_uuid=user_uuid,
                                                     session=session):
        _handle_notification_event(notification_event=n, session=session, iterable_notifier=iterable)
