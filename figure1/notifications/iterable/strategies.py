import logging
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from enum import Enum

from google.cloud.firestore_v1 import Client
from sqlalchemy.orm import Session

from figure1.common.helpers import CaseDetail
from figure1.common.helpers import UserDocument
from figure1.common.iterable.api import IterableAPI
from figure1.common.models.db import Case
from figure1.common.models.db import CaseCMEUserAnswer
from figure1.common.models.db import Comment
from figure1.common.models.db import GroupMemberFilter
from figure1.common.models.db import Groups
from figure1.common.models.db import SpecialtyV2
from figure1.common.models.db import User
from figure1.common.models.db import UserNotification
from figure1.common.models.firebase.user_drafts_db import FirebaseUserDraftsDB
from figure1.common.types import CaseState
from figure1.common.types import UserNotificationState
from figure1.common.types import VerificationStatus
from figure1.common.utils.date_utils import utc_now
from figure1.exceptions import DraftNotFound
from figure1.exceptions import UserNotFound
from .events import IterableCaseAcceptedAnswerEventDataFields
from .events import IterableCaseUpdateEventDataFields
from .events import IterableCommentOnYourCaseEventDataFields
from .events import IterableCommentReplyEventDataFields
from .events import IterableEvent
from .events import IterableEventWrapper
from .events import IterableNewCaseEventDataFields
from .events import IterableNewGroupCaseEventDataFields
from .events import IterablePagingEventDataFields
from .events import IterableUserCommentedOnCaseYouSavedEventDataFields
from .events import UserEventData
from ..event_generators import NotificationEvent

logger = logging.getLogger("figure1.notifications.iterable.strategies")


__all__ = []


def _get_media_url_from_case_details(case_details):
    if case_details.get('feedCardMedia'):
        return case_details.get('feedCardMedia').get('url')
    else:
        for each_content in case_details.get('contentItems', []):
            if each_content.get('isFeedCard'):
                for each_media in each_content.get('media', []):
                    if each_media.get('displayOrder') == 0:
                        return each_media.get('url')


class IterableSendEventStrategyBase:
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

    def update_unread_notifications_count(self, email: str, user_uuid: str, session: Session):
        unread_notifications_count = UserNotification \
            .get_unread_notifications_count(user_uuid=user_uuid, session=session)

        self._iterable_client.update_user(email=email, data_fields={"badgeCount": unread_notifications_count})

    def _get_data_fields(self, **kwargs):
        raise NotImplementedError

    def _generate_iterable_event_data(self,
                                      event: NotificationEvent,
                                      receiver: User,
                                      session: Session,
                                      fs_client: Client) -> IterableEventWrapper:
        raise NotImplementedError

    def _validate(self, event: NotificationEvent):
        return isinstance(event, NotificationEvent)

    def send(self, event: NotificationEvent, session: Session, fs_client: Client = None):
        if not self._validate(event):
            logger.error("notification_event is not an instance of NotificationEvent")
            return

        receiver_uuid = event.user_uuid
        receiver = User.get_user_by_uuid(user_uuid=receiver_uuid, session=session, raise_exception=True)

        self._track_event(self._generate_iterable_event_data(event, receiver, session, fs_client))
        self.update_unread_notifications_count(email=receiver.email, user_uuid=receiver_uuid, session=session)


class SendActivityReminderStrategy(IterableSendEventStrategyBase):
    def _get_data_fields(self, event: NotificationEvent, session: Session):
        receiver_uuid = event.user_uuid
        new_count = session.query(UserNotification) \
            .filter(UserNotification.user_uuid == receiver_uuid,
                    UserNotification.state == UserNotificationState.NEW) \
            .count()

        recent_time = utc_now(timezone=timezone.utc) - timedelta(days=1)
        new_count_24h = session.query(UserNotification) \
            .filter(UserNotification.user_uuid == receiver_uuid,
                    UserNotification.state == UserNotificationState.NEW,
                    UserNotification.updated_at > recent_time) \
            .count()

        data_fields = {
            "unreadNotificationsAll": new_count,
            "unreadNotificationsLast24Hours": new_count_24h
        }

        return data_fields

    def _generate_iterable_event_data(self,
                                      event: NotificationEvent,
                                      receiver: User,
                                      session: Session,
                                      fs_client: Client):
        data_fields = self._get_data_fields(event, session)
        return IterableEventWrapper(
            event=IterableEvent.ACTIVITY_REMINDER,
            email=receiver.email,
            data_fields=data_fields,
            user_uuid=receiver.user_uuid
        )


class SendCaseNewUpdateStrategy(IterableSendEventStrategyBase):
    def _get_data_fields(self, event: NotificationEvent, session: Session):
        case_uuid = event.case.case_uuid
        current_label = event.case.current_label
        previous_label = event.case.previous_label
        is_diagnosis = event.case.is_diagnosis
        case_details = CaseDetail.firestore_case_detail(case_uuid=case_uuid, session=session)
        is_case_anonymous = case_details.get('isAnonymous', False)
        group = Groups.get_group_by_uuid(group_uuid=case_details.get('groupUuid'), session=session)

        media_url = _get_media_url_from_case_details(case_details)

        data_fields = IterableCaseUpdateEventDataFields(
            caseTitle=case_details.get("title"),
            caseUuid=case_uuid,
            caseCurrentStatus=current_label,
            casePreviousStatus=previous_label,
            diagnosisUpdateAdded=is_diagnosis or False,
            authorUsername=case_details.get('author_username'),
            groupUuid=group.group_uuid if group else None,
            groupName=group.group_name if group else None,
            isAnonymous=is_case_anonymous,
            caseMediaUrl=media_url,
        ).dict()

        return data_fields

    def _generate_iterable_event_data(self,
                                      event: NotificationEvent,
                                      receiver: User,
                                      session: Session,
                                      fs_client: Client):
        data_fields = self._get_data_fields(event, session)
        return IterableEventWrapper(
            event=IterableEvent.CASE_NEW_UPDATE,
            email=receiver.email,
            data_fields=data_fields,
            user_uuid=receiver.user_uuid
        )


class SendCasePostedFollowedUserStrategy(IterableSendEventStrategyBase):
    def _get_data_fields(self, event: NotificationEvent, receiver: User, session: Session):
        author_uuid = event.source_uuid
        case_uuid = event.case_uuid
        author_details = UserDocument.user_detail(user_uuid=author_uuid, session=session)
        case_details = CaseDetail.firestore_case_detail(case_uuid=case_uuid, session=session)

        author_uuid = str(author_details.get('userUuid'))
        media_url = _get_media_url_from_case_details(case_details)

        data_fields = IterableNewCaseEventDataFields(
            caseCaption=case_details.get("caption"),
            caseTitle=case_details.get("title"),
            caseUuid=case_uuid,
            caseAuthorUsername=author_details.get("username"),
            caseAuthorFirstName=author_details.get("firstName"),
            caseAuthorLastName=author_details.get("lastName"),
            caseAuthorUuid=author_uuid,
            caseAuthorEmail=author_details.get("email"),
            receiverUuid=receiver.user_uuid,
            caseClassification=case_details.get("caseClassification"),
            caseMediaUrl=media_url,
        ).dict()

        return data_fields

    def _generate_iterable_event_data(self,
                                      event: NotificationEvent,
                                      receiver: User,
                                      session: Session,
                                      fs_client: Client):
        data_fields = self._get_data_fields(event, receiver, session)
        return IterableEventWrapper(
            event=event.iterable_event,
            email=receiver.email,
            data_fields=data_fields,
            user_uuid=receiver.user_uuid
        )


class SendCasePostedUserSavedCaseStrategy(IterableSendEventStrategyBase):
    def _get_data_fields(self, event: NotificationEvent, receiver: User, session: Session):
        author_uuid = event.source_uuid
        case_uuid = event.case_uuid

        author_details = UserDocument.user_detail(user_uuid=author_uuid, session=session)
        case_details = CaseDetail.firestore_case_detail(case_uuid=case_uuid, session=session)

        author_uuid = str(author_details.get('userUuid'))

        media_url = _get_media_url_from_case_details(case_details)

        data_fields = IterableNewCaseEventDataFields(
            caseCaption=case_details.get("caption"),
            caseTitle=case_details.get("title"),
            caseUuid=case_uuid,
            caseAuthorUsername=author_details.get("username"),
            caseAuthorFirstName=author_details.get("firstName"),
            caseAuthorLastName=author_details.get("lastName"),
            caseAuthorUuid=author_uuid,
            caseAuthorEmail=author_details.get("email"),
            receiverUuid=receiver.user_uuid,
            caseClassification=case_details.get("caseClassification"),
            caseMediaUrl=media_url,
        ).dict()

        return data_fields

    def _generate_iterable_event_data(self,
                                      event: NotificationEvent,
                                      receiver: User,
                                      session: Session,
                                      fs_client: Client):
        data_fields = self._get_data_fields(event, receiver, session)
        return IterableEventWrapper(
            event=event.iterable_event,
            email=receiver.email,
            data_fields=data_fields,
            user_uuid=receiver.user_uuid
        )


class SendCasePostedGroupStrategy(IterableSendEventStrategyBase):
    def _get_data_fields(self, event: NotificationEvent, session: Session):
        case_uuid = event.case_uuid
        group_uuid = event.group_uuid

        case_details = CaseDetail.firestore_case_detail(case_uuid=case_uuid, session=session)
        group = Groups.get_group_by_uuid(group_uuid=group_uuid, session=session)
        list_authors_usernames = []

        for case_author in case_details.get('authors', []):
            list_authors_usernames.append(case_author.get("username"))

        media_url = _get_media_url_from_case_details(case_details)

        data_fields = IterableNewGroupCaseEventDataFields(
            groupUuid=group.group_uuid,
            groupName=group.group_name,
            caseUuid=case_uuid,
            caseSubmissionDate=case_details.get("createdAt"),
            caseTitle=case_details.get("title"),
            authorUsername=list_authors_usernames,
            caseLabels=case_details.get("labels"),
            caseClassification=case_details.get("caseClassification"),
            caseMediaUrl=media_url,
            caseCaption=case_details.get("caption"),
        ).dict()

        return data_fields

    def _generate_iterable_event_data(self,
                                      event: NotificationEvent,
                                      receiver: User,
                                      session: Session,
                                      fs_client: Client):
        data_fields = self._get_data_fields(event, session)
        return IterableEventWrapper(
            event=event.iterable_event.value,
            email=receiver.email,
            data_fields=data_fields,
            user_uuid=receiver.user_uuid
        )

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

    def send_new_follower_event_to_target_user(self,
                                               receiver_uuid: str,
                                               follower_uuid: str,
                                               session: Session):
        receiver = User.get_user_by_uuid(user_uuid=receiver_uuid, session=session, raise_exception=True)
        follower = User.get_user_by_uuid(user_uuid=follower_uuid, session=session, raise_exception=True)


class SendCaseReactionStrategy(IterableSendEventStrategyBase):
    def _get_data_fields(self, event: NotificationEvent, receiver: User, session: Session):
        receiver_uuid = event.user_uuid
        case_uuid = event.case_uuid

        case_details = CaseDetail.firestore_case_detail(case_uuid=case_uuid, session=session)
        data_fields = {
            "caseCaption": case_details.get("caption"),
            "caseTitle": case_details.get("title"),
            "caseUuid": str(case_uuid),
            "receiverUuid": str(receiver_uuid),
            "receiverUid": receiver.user_uid,
            "caseClassification": case_details.get("caseClassification"),
        }

        return data_fields

    def _generate_iterable_event_data(self,
                                      event: NotificationEvent,
                                      receiver: User,
                                      session: Session,
                                      fs_client: Client):
        data_fields = self._get_data_fields(event, receiver, session)
        return IterableEventWrapper(
            event=IterableEvent.CASE_REACTION,
            email=receiver.email,
            data_fields=data_fields,
            user_uuid=receiver.user_uuid
        )


class SendCaseStateChangedStrategy(IterableSendEventStrategyBase):
    def _get_data_fields(self, event: NotificationEvent, receiver: User, session: Session, fs_client: Client):
        receiver_uuid = event.user_uuid
        case_uuid = event.case_uuid

        case_details = CaseDetail.firestore_case_detail(case_uuid=case_uuid, session=session)
        case_specialty_names = CaseDetail.get_case_specialty_names(case_uuid, session=session)
        new_state = case_details.get('caseState')

        # Note: the receiver is the case author
        data_fields = {
            "caseCaption": case_details.get("caption"),
            "caseTitle": case_details.get("title"),
            "caseUuid": str(case_uuid),
            "changedCaseState": new_state.lower(),
            "receiverUuid": str(receiver_uuid),
            "receiverUid": receiver.user_uid,
            "caseClassification": case_details.get("caseClassification"),
            "authorUuid": str(receiver_uuid),
            "authorUsername": receiver.username,
            "caseSpecialties": case_specialty_names,
        }

        if new_state in [CaseState.REJECTED.name, CaseState.DELETED.name]:
            case = Case.get_case(case_uuid=case_uuid, session=session, raise_exception=True)
            data_fields["changedCaseReason"] = case.rejection_reason.name.lower()
            data_fields["changedCaseReasonMessage"] = case.rejection_reason.message
            if new_state == CaseState.REJECTED.name:
                try:
                    data_fields["draftUid"] = FirebaseUserDraftsDB.get_draft_uid(fs_client=fs_client,
                                                                                 user_uid=receiver.user_uid,
                                                                                 case_uuid=case.case_uuid)
                except DraftNotFound:
                    pass

        return data_fields

    def _generate_iterable_event_data(self,
                                      event: NotificationEvent,
                                      receiver: User,
                                      session: Session,
                                      fs_client: Client):
        data_fields = self._get_data_fields(event, receiver, session, fs_client)
        return IterableEventWrapper(
            event=IterableEvent.CASE_STATE_CHANGED,
            email=receiver.email,
            data_fields=data_fields,
            user_uuid=receiver.user_uuid
        )


class SendCmeCompletedStrategy(IterableSendEventStrategyBase):
    def _get_data_fields(self, event: NotificationEvent, session: Session):
        case_uuid = event.case.case_uuid
        user_uuid = event.user_uuid
        is_case_cme = event.case.is_case_cme
        completed_at = event.case.completed_at

        data_fileds = {
            "cmeUuid": str(case_uuid),
            "completedAt": completed_at.strftime('%Y-%m-%d %H:%M:%S'),
            "userUuid": str(user_uuid),
        }

        if is_case_cme:
            case_details = CaseDetail.firestore_case_detail(case_uuid=case_uuid, session=session)
            user = User.get_user_by_uuid(user_uuid=user_uuid, session=session, raise_exception=True)
            user_answers_to_compare = CaseCMEUserAnswer\
                .get_question_answers_text_by_display_order(case_uuid=case_uuid, user_uuid=user_uuid,
                                                            display_order=2, session=session)
            will_impact_practice = "It will not impact my practice" not in user_answers_to_compare \
                if user_answers_to_compare else False
            data_fileds.update({
                "caseUuid": case_details.get("caseUuid"),
                "caseTitle": case_details.get("title"),
                "caseCaption": case_details.get("caption"),
                "caseImage": case_details.get("media"),
                "username": user.username,
                "willImpactPractice": will_impact_practice,
                "cmeUuid": None,
            })

        return data_fileds

    def _generate_iterable_event_data(self,
                                      event: NotificationEvent,
                                      receiver: User,
                                      session: Session,
                                      fs_client: Client):
        data_fields = self._get_data_fields(event, session)
        return IterableEventWrapper(
            event=IterableEvent.CME_COMPLETED,
            email=receiver.email,
            data_fields=data_fields,
            user_uuid=receiver.user_uuid
        )


class SendCommentSavedCaseStrategy(IterableSendEventStrategyBase):
    def _get_data_fields(self, event: NotificationEvent, session: Session):
        receiver_uuid = event.user_uuid
        case_uuid = event.case_uuid
        comment_uuid = event.comment_uuid
        commenter_uuid = event.source_uuid
        list_of_authors = []
        list_authors_emails = []
        list_authors_usernames = []
        is_op = False

        case = Case.get_case(case_uuid=case_uuid, session=session, raise_exception=True)
        case_details = CaseDetail.firestore_case_detail(case_uuid=case_uuid, session=session)
        group = Groups.get_group_by_uuid(group_uuid=case_details.get('groupUuid'), session=session)
        comment = Comment.get_comment(comment_uuid=comment_uuid, session=session)

        for case_author in case.authors:
            author_user_uuid = str(case_author.user_uuid)
            author = UserDocument.user_detail(user_uuid=author_user_uuid, session=session)
            list_of_authors.append(author_user_uuid)
            list_authors_emails.append(author.get("email"))
            list_authors_usernames.append(author.get("username"))

        if commenter_uuid in [str(case_author.user_uuid) for case_author in case.authors]:
            is_op = True

        if receiver_uuid in list_of_authors:
            return
        if receiver_uuid == commenter_uuid:
            return

        media_url = _get_media_url_from_case_details(case_details)

        data_fields = IterableUserCommentedOnCaseYouSavedEventDataFields(
            caseCaption=case_details.get("caption"),
            caseTitle=case_details.get("title"),
            caseUuid=case.case_uuid,
            commentUuid=comment_uuid,
            is_OP=is_op,
            caseAuthorEmail=list_authors_emails,
            caseAuthorUsername=list_authors_usernames,
            caseAuthorsUUID=list_of_authors,
            commenterUUID=commenter_uuid,
            receiverUuid=receiver_uuid,
            groupUuid=group.group_uuid if group else None,
            groupName=group.group_name if group else None,
            isAnonymous=case.is_anonymous,
            caseClassification=case_details.get("caseClassification"),
            caseMediaUrl=media_url,
            commentText=comment.text,
        ).dict()

        return data_fields

    def _generate_iterable_event_data(self,
                                      event: NotificationEvent,
                                      receiver: User,
                                      session: Session,
                                      fs_client: Client):
        data_fields = self._get_data_fields(event, session)
        return IterableEventWrapper(
            event=IterableEvent.COMMENT_SAVED_CASE,
            email=receiver.email,
            data_fields=data_fields,
            user_uuid=receiver.user_uuid
        )


class SendCommentYourCaseStrategy(IterableSendEventStrategyBase):
    def _get_data_fields(self, event: NotificationEvent, receiver: User, session: Session):
        receiver_uuid = event.user_uuid
        case_uuid = event.case_uuid
        comment_uuid = event.comment_uuid

        comment = Comment.get_comment(comment_uuid=comment_uuid, session=session)
        case_details = CaseDetail.firestore_case_detail(case_uuid=case_uuid, session=session)
        group = Groups.get_group_by_uuid(group_uuid=case_details.get('groupUuid'), session=session)

        media_url = _get_media_url_from_case_details(case_details)

        data_fields = IterableCommentOnYourCaseEventDataFields(
            caseCaption=case_details.get("caption"),
            caseTitle=case_details.get("title"),
            caseUuid=case_uuid,
            commentUuid=comment_uuid,
            receiverUuid=receiver_uuid,
            receiverUid=receiver.user_uid,
            groupUuid=group.group_uuid if group else None,
            groupName=group.group_name if group else None,
            caseClassification=case_details.get("caseClassification"),
            commentText=comment.text,
            caseMediaUrl=media_url,
        ).dict()

        return data_fields

    def _generate_iterable_event_data(self,
                                      event: NotificationEvent,
                                      receiver: User,
                                      session: Session,
                                      fs_client: Client):
        data_fields = self._get_data_fields(event, receiver, session)
        return IterableEventWrapper(
            event=IterableEvent.COMMENT_YOUR_CASE,
            email=receiver.email,
            data_fields=data_fields,
            user_uuid=receiver.user_uuid
        )


class SendCommentDeletedStrategy(IterableSendEventStrategyBase):
    def _get_data_fields(self, event: NotificationEvent, session: Session):
        comment_uuid = event.comment_uuid
        receiver_uuid = event.user_uuid
        comment_author = User.get_user_by_uuid(user_uuid=receiver_uuid, session=session, raise_exception=True)

        comment = Comment.get_comment(comment_uuid=comment_uuid, session=session)
        content = comment.content
        case_details = CaseDetail.firestore_case_detail(case_uuid=str(content.case_uuid), session=session)
        reason = comment.rejection_reason

        data_fields = {
            "caseCaption": content.caption,
            "caseTitle": content.title,
            "caseUuid": str(content.case_uuid),
            "commentText": comment.text,
            "commenterUuid": str(comment_author.user_uuid),
            "commenterUsername": comment_author.username,
            "commenterEmail": comment_author.email,
            "caseClassification": case_details.get("caseClassification"),
        }

        if reason:
            data_fields['rejectionReason'] = reason.name.lower(),
            data_fields['rejectionReasonMessage'] = reason.message

        return data_fields

    def _generate_iterable_event_data(self,
                                      event: NotificationEvent,
                                      receiver: User,
                                      session: Session,
                                      fs_client: Client):
        comment_author = User.get_user_by_uuid(user_uuid=receiver.user_uuid, session=session, raise_exception=True)

        data_fields = self._get_data_fields(event, session)
        return IterableEventWrapper(
            event=IterableEvent.COMMENT_DELETED,
            email=comment_author.email,
            data_fields=data_fields,
            user_uuid=comment_author.user_uuid
        )


class SendCommentReplyStrategy(IterableSendEventStrategyBase):
    def _get_data_fields(self, event: NotificationEvent, session: Session):
        receiver_uuid = event.user_uuid
        case_uuid = event.case_uuid
        commenter_uuid = event.source_uuid
        comment_uuid = event.comment_uuid

        case_details = CaseDetail.elasticsearch_case_detail(case_uuid=case_uuid, session=session)
        comment = Comment.get_comment(comment_uuid=comment_uuid, session=session)
        is_op = commenter_uuid in [str(u['userUuid']) for u in case_details['authors']]
        is_case_anonymous = case_details.get('isAnonymous', False)
        group = Groups.get_group_by_uuid(group_uuid=case_details.get('groupUuid'), session=session)

        media_url = _get_media_url_from_case_details(case_details)

        data_fields = IterableCommentReplyEventDataFields(
            caseTitle=case_details.get("title"),
            caseUuid=case_uuid,
            commentUuid=comment_uuid,
            mainCommentAuthorUuid=receiver_uuid,
            receiverUuid=receiver_uuid,
            respondentUuid=commenter_uuid,
            is_op=is_op,
            groupUuid=group.group_uuid if group else None,
            groupName=group.group_name if group else None,
            isAnonymous=is_case_anonymous,
            caseClassification=case_details.get("caseClassification"),
            replyText=comment.text,
            caseMediaUrl=media_url,
            caseAuthorUsername=case_details.get('author_username'),
        ).dict()

        return data_fields

    def _generate_iterable_event_data(self,
                                      event: NotificationEvent,
                                      receiver: User,
                                      session: Session,
                                      fs_client: Client):
        receiver_uuid = event.user_uuid
        commenter_uuid = event.source_uuid
        if receiver_uuid == commenter_uuid:
            return
        get_user_info = User.get_user_by_uuid(user_uuid=str(receiver_uuid), session=session, raise_exception=True)

        data_fields = self._get_data_fields(event, session)
        return IterableEventWrapper(
            event=IterableEvent.COMMENT_REPLY,
            email=get_user_info.email,
            data_fields=data_fields,
            user_uuid=receiver_uuid
        )


class SendFollowerStrategy(IterableSendEventStrategyBase):
    def _get_data_fields(self, event: NotificationEvent, session: Session):
        follower_uuid = event.source_uuid
        follower = User.get_user_by_uuid(user_uuid=follower_uuid, session=session, raise_exception=True)

        data_fields = {
            "userNewFollowerUsername": follower.username,
            "userNewFollowerUuid": str(follower.user_uuid),
            "userNewFollowerProfileImage": follower.user_profile.avatar,
        }

        return data_fields

    def _generate_iterable_event_data(self,
                                      event: NotificationEvent,
                                      receiver: User,
                                      session: Session,
                                      fs_client: Client):
        data_fields = self._get_data_fields(event, session)
        return IterableEventWrapper(
            event=IterableEvent.FOLLOWER,
            email=receiver.email,
            data_fields=data_fields,
            user_uuid=receiver.user_uuid
        )


class SendPagingCasePostedSpecialtyUsersStrategy(IterableSendEventStrategyBase):
    def _get_data_fields(self, event: NotificationEvent, session: Session):
        case_uuid = event.case_uuid
        case_details = CaseDetail.firestore_case_detail(case_uuid=case_uuid, session=session)
        is_case_anonymous = case_details.get('isAnonymous', False)
        case_specialty_names = []
        authors_info = []

        for specialty in case_details.get('specialtyUuids'):
            sn = session.query(SpecialtyV2).filter(SpecialtyV2.specialty_uuid == specialty).one_or_none()
            if sn:
                case_specialty_names.append(sn.name)
        for author in case_details.get('authors'):
            if author.get('userUuid'):
                author_model = UserDocument.get_compact_user_data(user_uuid=author.get('userUuid'), session=session)
                authors_info.append(author_model)

        media_url = _get_media_url_from_case_details(case_details)

        data_fields = IterablePagingEventDataFields(
            caseCaption=case_details.get("caption"),
            caseTitle=case_details.get("title"),
            caseUuid=case_uuid,
            caseTimeApproval=datetime.fromisoformat(case_details.get('publishedAt')).strftime('%Y-%m-%d %H:%M:%S'),
            caseSpecialty=case_specialty_names,
            caseMediaUrl=media_url,
            authorsInfo=authors_info,
            isAnonymous=is_case_anonymous,
        ).dict()

        return data_fields

    def _generate_iterable_event_data(self,
                                      event: NotificationEvent,
                                      receiver: User,
                                      session: Session,
                                      fs_client: Client):
        data_fields = self._get_data_fields(event, session)
        return IterableEventWrapper(
            event=event.iterable_event,
            email=receiver.email,
            data_fields=data_fields,
            user_uuid=receiver.user_uuid
        )


class SendUserStatusChangedStrategy(IterableSendEventStrategyBase):
    def _get_data_fields(self, event: NotificationEvent, receiver: User, session: Session):
        moderator_uuid = event.source_uuid
        receiver_doc = UserDocument.user_detail(user_uuid=receiver.user_uuid, session=session)
        verification = receiver_doc.pop('verification')
        verification_type = verification.get("verificationType")
        if verification.get('verificationFlaggedForReview', False):
            verification.update({'verificationStatus': VerificationStatus.REVIEW_REQUIRED.value})
        verification_status = verification.get("verificationStatus")

        data_fields = {
            "userEmail": receiver_doc.get("email"),
            "userUid": receiver_doc.get("userUid"),
            "userUuid": receiver_doc.get("userUuid"),
            "userFirstName": receiver_doc.get("firstName"),
            "userLastName": receiver_doc.get("lastName"),
            "status": verification_status,
            "verificationType": verification_type,
        }
        if moderator_uuid:
            try:
                moderator = User.get_user_by_uuid(user_uuid=moderator_uuid, session=session, raise_exception=True)
            except UserNotFound:
                data_fields.update({
                    "moderatorUsername": "Not Found",
                    "moderatorFirstName": "Not Found",
                    "moderatorLastName": "Not Found",
                })
            else:
                data_fields.update({
                    "moderatorUsername": moderator.username,
                    "moderatorFirstName": moderator.first_name,
                    "moderatorLastName": moderator.last_name,
                })
        else:
            data_fields.update({
                "moderatorUsername": "Unknown",
                "moderatorFirstName": "Unknown",
                "moderatorLastName": "Unknown",
            })

        return data_fields

    def _generate_iterable_event_data(self,
                                      event: NotificationEvent,
                                      receiver: User,
                                      session: Session,
                                      fs_client: Client):
        data_fields = self._get_data_fields(event, receiver, session)
        return IterableEventWrapper(
            event=IterableEvent.USER_STATUS_CHANGED,
            email=receiver.email,
            data_fields=data_fields,
            user_uuid=receiver.user_uuid
        )


class SendDiagnosisNotChosenStrategy(IterableSendEventStrategyBase):
    def _get_data_fields(self, event: NotificationEvent, receiver: User, session: Session):
        case_uuid = event.case_uuid
        case_details = CaseDetail.firestore_case_detail(case_uuid=case_uuid, session=session)

        accepted_answer_set = False
        for each in case_details.get('contentItems'):
            if 'acceptedAnswer' in each and each.get('acceptedAnswer'):
                accepted_answer_set = True
                break

        media_url = _get_media_url_from_case_details(case_details)

        data_fields = {
            "caseUuid": str(case_uuid),
            "caseSubmissionDate": case_details.get("createdAt"),
            "caseTitle": case_details.get("title"),
            "authorUsername": receiver.username,
            "acceptedAnswerSet": accepted_answer_set,
            "numberOfComments": case_details.get("commentCount"),
            "diagnosisUpdateAdded": case_details.get("hasDiagnosis"),
            "caseMediaUrl": media_url,
        }

        return data_fields

    def _generate_iterable_event_data(self,
                                      event: NotificationEvent,
                                      receiver: User,
                                      session: Session,
                                      fs_client: Client):
        data_fields = self._get_data_fields(event, receiver, session)
        return IterableEventWrapper(
            event=event.iterable_event,
            email=receiver.email,
            data_fields=data_fields,
            user_uuid=receiver.user_uuid
        )


class SendProfessionChangeApprovedStrategy(IterableSendEventStrategyBase):
    def _get_data_fields(self, receiver: User):
        data_fields = {
            "professionName": receiver.primary_specialty.tree.case_comment_display_label
        }

        return data_fields

    def _generate_iterable_event_data(self,
                                      event: NotificationEvent,
                                      receiver: User,
                                      session: Session,
                                      fs_client: Client):
        data_fields = self._get_data_fields(receiver)
        return IterableEventWrapper(
            event=IterableEvent.PROFESSION_CHANGE_APPROVED,
            email=receiver.email,
            data_fields=data_fields,
            user_uuid=receiver.user_uuid
        )


class SendGroupInviteStrategy(IterableSendEventStrategyBase):
    def _get_data_fields(self, event: NotificationEvent, receiver: User, session: Session):
        inviter_uuid = event.source_uuid
        group_uuid = event.group_uuid
        inviter = User.get_user_by_uuid(user_uuid=inviter_uuid, session=session, raise_exception=True)
        group = Groups.get_group_by_uuid(group_uuid=group_uuid, session=session)

        data_fields = {
            "username": receiver.username,
            "userUuid": str(receiver.user_uuid),
            "email": receiver.email,
            "inviterUsername": inviter.username,
            "inviterUuid": str(inviter.user_uuid),
            "inviterEmail": inviter.email,
            "groupUuid": str(group.group_uuid),
            "groupName": group.group_name,
            "groupDescription": group.group_description,
        }

        if group.creator:
            data_fields.update({
                "groupCreatorUsername": group.creator.username,
                "groupCreatorUuid": str(group.creator.user_uuid),
                "groupCreatorEmail": group.creator.email
            })

        return data_fields

    def _generate_iterable_event_data(self,
                                      event: NotificationEvent,
                                      receiver: User,
                                      session: Session,
                                      fs_client: Client):
        data_fields = self._get_data_fields(event, receiver, session)
        return IterableEventWrapper(
            event=IterableEvent.GROUP_INVITE,
            email=receiver.email,
            data_fields=data_fields,
            user_uuid=receiver.user_uuid
        )


class SendGroupInviteAcceptedStrategy(IterableSendEventStrategyBase):
    def _get_data_fields(self, event: NotificationEvent, session: Session):
        accepting_user_uuid = event.source_uuid
        group_uuid = event.group_uuid
        accepting_user = User.get_user_by_uuid(user_uuid=accepting_user_uuid, session=session, raise_exception=True)
        gmf = GroupMemberFilter.get_by_group_and_user_uuid(group_uuid=group_uuid,
                                                           user_uuid=accepting_user_uuid,
                                                           session=session)
        g = Groups.get_group_by_uuid(group_uuid=group_uuid, session=session)
        if not g:
            logging.error("Could not find group group=%s", group_uuid)
            return

        data_fields = {
            "acceptingUserUsername": accepting_user.username,
            "acceptingUserUuid": str(accepting_user.user_uuid),
            "acceptingUserEmail": accepting_user.email,
            "groupName": g.group_name,
            "groupDescription": g.group_description,
        }

        if g.creator:
            data_fields.update({
                "groupCreatorUsername": g.creator.username,
                "groupCreatorUuid": str(g.creator.user_uuid),
                "groupCreatorEmail": g.creator.email
            })

        if gmf and gmf.inviter:
            data_fields.update({
                "inviterUsername": gmf.inviter.username,
                "inviterUuid": str(gmf.inviter.user_uuid),
                "inviterEmail": gmf.inviter.email
            })

        return data_fields

    def _generate_iterable_event_data(self,
                                      event: NotificationEvent,
                                      receiver: User,
                                      session: Session,
                                      fs_client: Client):
        data_fields = self._get_data_fields(event, session)
        return IterableEventWrapper(
            event=IterableEvent.GROUP_INVITE_ACCEPTED,
            email=receiver.email,
            data_fields=data_fields,
            user_uuid=receiver.user_uuid
        )


class SendCaseAcceptedAnswerStrategy(IterableSendEventStrategyBase):
    def get_data_fields(self, event, session):
        case_uuid = event.case_uuid
        comment_uuid = event.comment_uuid
        case_details = CaseDetail.firestore_case_detail(case_uuid=case_uuid, session=session)
        is_case_anonymous = case_details.get('isAnonymous', False)

        media_url = _get_media_url_from_case_details(case_details)

        data_fields = IterableCaseAcceptedAnswerEventDataFields(
            caseTitle=case_details.get("title"),
            caseCaption=case_details.get('caption'),
            caseMediaUrl=media_url,
            caseUuid=case_uuid,
            commentUuid=comment_uuid,
            authorUsername=case_details.get('author_username'),
            isAnonymous=is_case_anonymous,
        ).dict(exclude={"acceptedAnswerSet", "numberOfComments", "diagnosisUpdateAdded", "caseSubmissionDate"})

        return data_fields

    def _generate_iterable_event_data(self,
                                      event: NotificationEvent,
                                      receiver: User,
                                      session: Session,
                                      fs_client: Client):
        data_fields = self.get_data_fields(event, session)
        return IterableEventWrapper(
            event=event.iterable_event,
            email=receiver.email,
            data_fields=data_fields,
            user_uuid=receiver.user_uuid,
        )


class SendCaseAcceptedAnswerSelectedStrategy(IterableSendEventStrategyBase):
    def _get_data_fields(self, event: NotificationEvent, session: Session):
        case_uuid = event.case_uuid
        comment_uuid = event.comment_uuid
        case_details = CaseDetail.firestore_case_detail(case_uuid=case_uuid, session=session)
        is_case_anonymous = case_details.get('isAnonymous', False)

        media_url = _get_media_url_from_case_details(case_details)

        data_fields = IterableCaseAcceptedAnswerEventDataFields(
            caseTitle=case_details.get("title"),
            caseUuid=case_uuid,
            commentUuid=comment_uuid,
            authorUsername=case_details.get("author_username"),
            isAnonymous=is_case_anonymous,
            caseCaption=case_details.get("caption"),
            caseMediaUrl=media_url,
        ).dict(exclude={"acceptedAnswerSet", "numberOfComments", "diagnosisUpdateAdded", "caseSubmissionDate"})

        return data_fields

    def _generate_iterable_event_data(self,
                                      event: NotificationEvent,
                                      receiver: User,
                                      session: Session,
                                      fs_client: Client):
        data_fields = self._get_data_fields(event, session)

        return IterableEventWrapper(
            event=event.iterable_event,
            email=receiver.email,
            data_fields=data_fields,
            user_uuid=receiver.user_uuid,
        )


class SendCaseAcceptedAnswerNotChosenStrategy(IterableSendEventStrategyBase):
    def _get_data_fields(self, event: NotificationEvent, session: Session):
        case_uuid = event.case_uuid
        case_details = CaseDetail.firestore_case_detail(case_uuid=case_uuid, session=session)
        accepted_answer_set = False
        for each in case_details.get('contentItems'):
            if 'acceptedAnswer' in each and each.get('acceptedAnswer'):
                accepted_answer_set = True
                break

        media_url = _get_media_url_from_case_details(case_details)

        data_fields = IterableCaseAcceptedAnswerEventDataFields(
            caseUuid=str(case_uuid),
            caseSubmissionDate=datetime.fromisoformat(case_details.get('createdAt')).strftime('%Y-%m-%d %H:%M:%S'),
            caseTitle=case_details.get("title"),
            authorUsername=case_details.get('author_username'),
            acceptedAnswerSet=accepted_answer_set,
            numberOfComments=case_details.get("commentCount"),
            diagnosisUpdateAdded=case_details.get("hasDiagnosis"),
            caseCaption=case_details.get("caption"),
            caseMediaUrl=media_url,
        ).dict(exclude={"deletionReason", "commentUuid"})

        return data_fields

    def _generate_iterable_event_data(self,
                                      event: NotificationEvent,
                                      receiver: User,
                                      session: Session,
                                      fs_client: Client):
        data_fields = self._get_data_fields(event, session)
        return IterableEventWrapper(
            event=event.iterable_event,
            email=receiver.email,
            data_fields=data_fields,
            user_uuid=receiver.user_uuid,
        )


class SendCaseAcceptedAnswerDeletedStrategy(IterableSendEventStrategyBase):
    def _get_data_fields(self, event: NotificationEvent, session: Session):
        case_uuid = event.case_uuid
        comment_uuid = event.comment_uuid
        case_details = CaseDetail.firestore_case_detail(case_uuid=case_uuid, session=session)
        comment = Comment.get_comment(comment_uuid=comment_uuid, session=session)
        reason = ''
        if comment.rejection_reason:
            reason = comment.rejection_reason.name.lower()

        data_fields = IterableCaseAcceptedAnswerEventDataFields(
            caseTitle=case_details.get("title"),
            caseUuid=case_uuid,
            authorUsername=case_details.get('author_username'),
            deletionReason=reason,
        ).dict(exclude={"acceptedAnswerSet", "numberOfComments",
                        "diagnosisUpdateAdded", "caseSubmissionDate",
                        "caseMediaUrl", "caseCaption", "commentUuid"})

        return data_fields

    def _generate_iterable_event_data(self,
                                      event: NotificationEvent,
                                      receiver: User,
                                      session: Session,
                                      fs_client: Client):
        data_fields = self._get_data_fields(event, session)
        return IterableEventWrapper(
            event=event.iterable_event,
            email=receiver.email,
            data_fields=data_fields,
            user_uuid=receiver.user_uuid,
        )


class IterableSendEventStrategy(Enum):
    ACTIVITY_REMINDER = SendActivityReminderStrategy
    CASE_NEW_UPDATE = SendCaseNewUpdateStrategy
    CASE_POSTED_FOLLOWED_USER = SendCasePostedFollowedUserStrategy
    CASE_POSTED_GROUP = SendCasePostedGroupStrategy
    CASE_POSTED_USER_SAVED_CASE = SendCasePostedUserSavedCaseStrategy
    CASE_REACTION = SendCaseReactionStrategy
    CASE_STATE_CHANGED = SendCaseStateChangedStrategy
    CME_COMPLETED = SendCmeCompletedStrategy
    COMMENT_DELETED = SendCommentDeletedStrategy
    COMMENT_REPLY = SendCommentReplyStrategy
    COMMENT_SAVED_CASE = SendCommentSavedCaseStrategy
    COMMENT_YOUR_CASE = SendCommentYourCaseStrategy
    CASE_NEW_ACCEPTED_ANSWER = SendCaseAcceptedAnswerStrategy
    CASE_NEW_ACCEPTED_ANSWER_SELECTED = SendCaseAcceptedAnswerSelectedStrategy
    CASE_ACCEPTED_ANSWER_NOT_CHOSEN = SendCaseAcceptedAnswerNotChosenStrategy
    CASE_ACCEPTED_ANSWER_DELETED = SendCaseAcceptedAnswerDeletedStrategy
    DIAGNOSIS_NOT_CHOSEN = SendDiagnosisNotChosenStrategy
    FOLLOWER = SendFollowerStrategy
    GROUP_INVITE = SendGroupInviteStrategy
    GROUP_INVITE_ACCEPTED = SendGroupInviteAcceptedStrategy
    PAGING_CASE_POSTED_SPECIALTY_SUBSPECIALTY_USERS = SendPagingCasePostedSpecialtyUsersStrategy
    PAGING_CASE_POSTED_SPECIALTY_USERS = SendPagingCasePostedSpecialtyUsersStrategy
    PAGING_CASE_POSTED_SUBSPECIALTY_USERS = SendPagingCasePostedSpecialtyUsersStrategy
    PROFESSION_CHANGE_APPROVED = SendProfessionChangeApprovedStrategy
    USER_STATUS_CHANGED = SendUserStatusChangedStrategy
    # USER_REGISTRATION_TRACKING = SendUserRegistrationTrackingStrategy
    # CASE_POST_TRACKING = SendCasePostTrackingStrategy
