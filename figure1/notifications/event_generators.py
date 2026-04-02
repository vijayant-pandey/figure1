import logging
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from typing import Optional

from pydantic import BaseModel
from pydantic import validator
from sqlalchemy import distinct
from sqlalchemy import or_
from sqlalchemy.orm import Query
from sqlalchemy.orm import Session

from figure1.common.firebase import do_firebase_sync
from figure1.common.helpers import CommentSync
from figure1.common.helpers import GroupManagement
from figure1.common.models.db import ActivityReminder
from figure1.common.models.db import Case
from figure1.common.models.db import CaseAuthor
from figure1.common.models.db import CaseReaction
from figure1.common.models.db import Comment
from figure1.common.models.db import Content
from figure1.common.models.db import GroupMemberFilter
from figure1.common.models.db import SpecialtyTreeV2
from figure1.common.models.db import User
from figure1.common.models.db import UserFollow
from figure1.common.models.db import UserNotification
from figure1.common.models.db import UserSavedCase
from figure1.common.models.db import UserSpecialtyTreeV2
from figure1.common.models.db import UserVerification
from figure1.common.types import CaseState
from figure1.common.types import CaseClassification
from figure1.common.types import CommentModel
from figure1.common.types import Reaction
from figure1.common.types.notification import UserNotificationState
from figure1.common.types import UserNotificationType
from figure1.common.types import VerificationStatus
from figure1.common.types.field_validators import stringify_uuid
from figure1.common.utils.date_utils import utc_now

from .iterable.events import IterableEvent


logger = logging.getLogger("figure1.notifications.main")


__all__ = ['NotificationEvent']


def _check_if_a_case_is_post(case: Case):
    """
    It will check if the case is a Post
    """
    if case.case_classification is CaseClassification.NONMEDICAL:
        logger.info("The Case is a Post")
        return True

    return False


class NotificationEventCase(BaseModel):
    case_uuid: Optional[str]
    current_label: Optional[str]
    previous_label: Optional[str]
    is_diagnosis: Optional[str]
    completed_at: Optional[datetime]
    is_case_cme: Optional[bool]
    _stringify_uuid = validator('case_uuid',
                                allow_reuse=True, pre=True)(stringify_uuid)


class NotificationEvent(BaseModel):
    """
    Encapsulates data required to send a notification.
    The notification can include a user notification, iterable event, or both.
    """
    user_notification: Optional[UserNotificationType]
    iterable_event: Optional[IterableEvent]
    user_uuid: str
    source_uuid: Optional[str]
    case_uuid: Optional[str]
    case: Optional[NotificationEventCase]
    group_uuid: Optional[str]
    comment_uuid: Optional[str]
    only_notify_privately: bool = False
    _stringify_uuid = validator('user_uuid', 'source_uuid', 'case_uuid', 'comment_uuid',
                                allow_reuse=True, pre=True)(stringify_uuid)


def get_notifications_case_state_change(case_uuid: str,
                                        moderator_uid: Optional[str],
                                        suppress_user_notification: bool,
                                        session: Session):
    def _determine_notification_type_for_state(state):
        if state.value == CaseState.REJECTED.value:
            return UserNotificationType.REJECT
        elif state.value == CaseState.DELETED.value:
            return UserNotificationType.CASE_DELETE
        elif state.value == CaseState.APPROVED.value:
            return UserNotificationType.APPROVE
        else:
            return None

    case = Case.get_case(case_uuid=case_uuid, session=session, raise_exception=True)
    if moderator_uid:
        moderator_uuid = str(User.get_user_uuid_by_uid(user_uid=moderator_uid, session=session))
    else:
        moderator_uuid = None
    if suppress_user_notification:
        user_notification_type = None
    else:
        user_notification_type = _determine_notification_type_for_state(case.state)

    for a in case.authors:
        yield NotificationEvent(
            user_notification=user_notification_type,
            iterable_event=IterableEvent.CASE_STATE_CHANGED,
            case_uuid=case_uuid,
            user_uuid=str(a.user_uuid),
            source_uuid=moderator_uuid
        )


def get_notifications_new_case(case_uuid: str,
                               session: Session):
    case = Case.get_case(case_uuid)
    all_authors = session.query(CaseAuthor).filter(CaseAuthor.case_uuid == case_uuid).all()
    if not case.group_uuid:
        for ca in all_authors:
            author_uuid = str(ca.author_uuid)
            followers = UserFollow.get_user_followers(session=session, user_uuid=author_uuid)
            for user_uuid in followers:
                yield NotificationEvent(
                    user_notification=UserNotificationType.NEW_CASE_FOLLOWED_USER,
                    iterable_event=IterableEvent.CASE_POSTED_FOLLOWED_USER,
                    user_uuid=user_uuid,
                    source_uuid=author_uuid,
                    case_uuid=case_uuid,
                    only_notify_privately=True,
                )

            users_saved_case = list(UserSavedCase.users_saved_case_non_followers(session=session,
                                                                                 author_uuid=author_uuid))
            for user_uuid in users_saved_case:
                if user_uuid != author_uuid:
                    yield NotificationEvent(
                        user_notification=UserNotificationType.NEW_CASE_USER_SAVED_CASE,
                        iterable_event=IterableEvent.CASE_POSTED_USER_SAVED_CASE,
                        user_uuid=user_uuid,
                        source_uuid=author_uuid,
                        case_uuid=case_uuid,
                        only_notify_privately=True,
                    )
    else:
        for m in case.group.members:
            if m.user_uuid not in (each.author_uuid for each in all_authors):
                yield NotificationEvent(
                    user_notification=UserNotificationType.NEW_CASE_GROUP,
                    iterable_event=IterableEvent.CASE_POSTED_GROUP,
                    case_uuid=case_uuid,
                    group_uuid=str(case.group_uuid),
                    user_uuid=str(m.user_uuid)
                )


def get_notifications_case_update(case_uuid: str,
                                  author_uuid: str,
                                  is_diagnosis: bool,
                                  previous_label: str,
                                  current_label: str,
                                  session: Session) -> [NotificationEvent]:
    case = Case.get_case(case_uuid)
    if _check_if_a_case_is_post(case=case):
        return StopIteration

    list_of_authors = []
    for case_author in case.authors:
        list_of_authors.append(str(case_author.user_uuid))

    users_saved_case = list(UserSavedCase.users_saved_case(session=session, case_uuid=case.case_uuid))
    users_liked_case = CaseReaction.get_case_reactions(case_uuid=case_uuid, session=session)[Reaction.AGREE.value]
    users_commented_case = []
    for each_content in case.content:
        users_commented_case.extend(Comment.get_content_commenters(each_content.content_uuid, session=session))

    notification_event_case = NotificationEventCase(case_uuid=case_uuid,
                                                    current_label=current_label,
                                                    previous_label=previous_label,
                                                    is_diagnosis=is_diagnosis)
    if not is_diagnosis:
        for user_uuid in users_saved_case:
            if user_uuid not in list_of_authors:
                yield NotificationEvent(
                    user_notification=UserNotificationType.SAVED_CASE_UPDATE,
                    iterable_event=IterableEvent.CASE_NEW_UPDATE,
                    user_uuid=user_uuid,
                    source_uuid=author_uuid,
                    case_uuid=case_uuid,
                    case=notification_event_case,
                )
    else:
        # Priority 1 - New diagnosis on a case you commented
        for user_uuid in users_commented_case:
            if user_uuid not in list_of_authors:
                yield NotificationEvent(
                    user_notification=UserNotificationType.COMMENTED_CASE_DIAGNOSIS,
                    iterable_event=IterableEvent.CASE_NEW_UPDATE,
                    user_uuid=user_uuid,
                    source_uuid=author_uuid,
                    case_uuid=case_uuid,
                    case=notification_event_case,
                )

        # Priority 2 - New diagnosis on a case you saved
        for user_uuid in set(users_saved_case) - set(users_commented_case):
            if user_uuid not in list_of_authors:
                yield NotificationEvent(
                    user_notification=UserNotificationType.SAVED_CASE_DIAGNOSIS,
                    iterable_event=IterableEvent.CASE_NEW_UPDATE,
                    user_uuid=user_uuid,
                    source_uuid=author_uuid,
                    case_uuid=case_uuid,
                    case=notification_event_case,
                )

        # Priority 3 - New diagnosis on a case you liked
        for user_uuid in set(users_liked_case) - set(users_saved_case + users_commented_case):
            if user_uuid not in list_of_authors:
                yield NotificationEvent(
                    user_notification=UserNotificationType.LIKED_CASE_DIAGNOSIS,
                    iterable_event=IterableEvent.CASE_NEW_UPDATE,
                    user_uuid=user_uuid,
                    source_uuid=author_uuid,
                    case_uuid=case_uuid,
                    case=notification_event_case,
                )


def get_notifications_new_follower(target_user_uuid: str,
                                   follower_uuid: str) -> [NotificationEvent]:
    yield NotificationEvent(
        user_notification=UserNotificationType.NEW_FOLLOWER,
        iterable_event=IterableEvent.FOLLOWER,
        user_uuid=target_user_uuid,
        source_uuid=follower_uuid
    )


def get_notifications_case_reaction(case_uuid: str,
                                    user_uuid: str,
                                    session: Session):
    case = Case.get_case(case_uuid=case_uuid, session=session, raise_exception=True)

    for a in case.authors:
        if user_uuid != str(a.user_uuid):
            yield NotificationEvent(
                user_notification=UserNotificationType.REACT,
                iterable_event=IterableEvent.CASE_REACTION,
                case_uuid=case_uuid,
                user_uuid=str(a.user_uuid),
                source_uuid=user_uuid
            )


def get_notifications_cme_completed(case_uuid: str,
                                    user_uuid: str,
                                    completed_at: datetime,
                                    is_case_cme: bool):
    notification_event_case = NotificationEventCase(
        case_uuid=case_uuid,
        completed_at=completed_at,
        is_case_cme=is_case_cme
    )
    yield NotificationEvent(
        user_notification=None,
        iterable_event=IterableEvent.CME_COMPLETED,
        user_uuid=user_uuid,
        case_uuid=case_uuid,
        case=notification_event_case
    )


def get_notifications_new_comment(comment_uuid: str,
                                  content_uuid: str,
                                  commenter_uuid: str,
                                  session: Session):
    logger.info(f"Looking up receiver of Activity")

    content = Content.get_content(content_uuid=content_uuid, session=session)
    case = Case.get_case(content.case_uuid, session=session, raise_exception=True)
    authors = case.authors
    author_uuids = [str(u.user_uuid) for u in case.authors]
    case_uuid = str(case.case_uuid)
    do_firebase_sync.delay(firebasemodel='FirebaseUsersProfileDB', uuid=str(commenter_uuid))
    is_op = commenter_uuid in author_uuids

    c = CommentSync.get_comment(comment_uuid=comment_uuid, session=session)
    notified_uuids = []
    if c.parent:
        if comment_uuid != c.parent.comment_uuid:
            # c.parent.comment_uuid is the immediate ancestor of the comment.
            comment = session.query(Comment) \
                .filter(Comment.comment_uuid == c.parent.comment_uuid,
                        Comment.deleted_at.is_(None)) \
                .one_or_none()
            notification_type = UserNotificationType.COMMENT_REPLY_OP if is_op else UserNotificationType.COMMENT_REPLY
            yield NotificationEvent(user_notification=notification_type,
                                    iterable_event=IterableEvent.COMMENT_REPLY,
                                    user_uuid=str(comment.author_uuid),
                                    source_uuid=commenter_uuid,
                                    case_uuid=case_uuid,
                                    comment_uuid=comment_uuid)
            notified_uuids.append(str(comment.author_uuid))

    for author in authors:
        author_uuid = str(author.user_uuid)
        if author_uuid != commenter_uuid and author_uuid not in notified_uuids:
            yield NotificationEvent(user_notification=UserNotificationType.COMMENT,
                                    iterable_event=IterableEvent.COMMENT_YOUR_CASE,
                                    user_uuid=author_uuid,
                                    source_uuid=commenter_uuid,
                                    case_uuid=case_uuid,
                                    comment_uuid=comment_uuid)
            notified_uuids.append(author_uuid)
    # the event send_event_user_commented_on_case_you_saved() should not be inside the for loop, the func
    # must check if the author is OP or not
    users_saved_case = UserSavedCase.users_saved_case(session=session, case_uuid=case_uuid)
    saved_type = UserNotificationType.COMMENT_SAVED_CASE_OP if is_op else UserNotificationType.COMMENT_SAVED_CASE
    for user_uuid in users_saved_case:
        if user_uuid not in notified_uuids and user_uuid not in author_uuids and user_uuid != commenter_uuid:
            yield NotificationEvent(user_notification=saved_type,
                                    iterable_event=IterableEvent.COMMENT_SAVED_CASE,
                                    user_uuid=user_uuid,
                                    source_uuid=commenter_uuid,
                                    case_uuid=case_uuid,
                                    comment_uuid=comment_uuid)


def get_notifications_comment_delete(comment_uuid: str,
                                     author_uuid: str,
                                     moderator_uuid: str,
                                     session: Session):
    comment = Comment.get_comment(comment_uuid=comment_uuid, session=session)
    yield NotificationEvent(
        user_notification=UserNotificationType.COMMENT_DELETE,
        iterable_event=IterableEvent.COMMENT_DELETED,
        user_uuid=author_uuid,
        source_uuid=moderator_uuid,
        comment_uuid=comment_uuid,
        case_uuid=str(comment.content.case_uuid)
    )


def get_notifications_user_status_changed(user_uuid: str,
                                          moderator_uid: str,
                                          session: Session):
    if moderator_uid:
        moderator_uuid = str(User.get_user_uuid_by_uid(user_uid=moderator_uid, session=session))
    else:
        moderator_uuid = None

    yield NotificationEvent(
        user_notification=None,
        iterable_event=IterableEvent.USER_STATUS_CHANGED,
        user_uuid=user_uuid,
        source_uuid=moderator_uuid
    )


def get_notifications_paging_case(case_uuid: str,
                                  session: Session) -> [NotificationEvent]:
    case = Case.get_case(case_uuid=case_uuid, session=session, raise_exception=True)
    if _check_if_a_case_is_post(case=case):
        return StopIteration

    case_specialty_uuids = [s.specialty_uuid for s in case.specialties]
    logger.info(f"PAGING DEBUG: Case {case_uuid} has specialty UUIDs: {case_specialty_uuids}")
    
    if not case_specialty_uuids:
        logging.info(f"No specialties found for the case %s, no paging events to send", case_uuid)
        return

    previously_notified = session.query(UserNotification) \
        .filter(UserNotification.notification_type == UserNotificationType.PAGING,
                UserNotification.case_uuid == case_uuid) \
        .all()
    notified_uuids = [str(each.user_uuid) for each in previously_notified]
    author_uuids = [a.user_uuid for a in case.authors]
    
    logger.info(f"PAGING DEBUG: Case {case_uuid} - Previously notified users: {len(notified_uuids)}, Authors: {len(author_uuids)}")

    base_query = Query([distinct(User.user_uuid)], session=session) \
        .join(UserSpecialtyTreeV2, User.user_uuid == UserSpecialtyTreeV2.user_uuid) \
        .join(SpecialtyTreeV2, SpecialtyTreeV2.specialty_uuid == UserSpecialtyTreeV2.tree_uuid) \
        .join(UserVerification, User.user_uuid == UserVerification.user_uuid) \
        .filter(UserSpecialtyTreeV2.is_primary.is_(True),
                User.deleted_at.is_(None), User.user_uid.isnot(None),
                UserVerification.verification_status.in_([VerificationStatus.VERIFIED,
                                                          VerificationStatus.CHANGE_REQUESTED,
                                                          VerificationStatus.ARCHIVED]))
    if author_uuids:
        base_query = base_query.filter(User.user_uuid.not_in(author_uuids))

    # Users matching specialty and subspecialty
    subspecialty_query = base_query.filter(SpecialtyTreeV2.subspecialty_uuid.in_(case_specialty_uuids),
                                           SpecialtyTreeV2.specialty_v2_uuid.in_(case_specialty_uuids))
    if notified_uuids:
        subspecialty_query = subspecialty_query.filter(UserSpecialtyTreeV2.user_uuid.not_in(notified_uuids))
    
    query1_count = 0
    for res in subspecialty_query.yield_per(100).all():
        user_uuid = str(res[0])
        query1_count += 1
        notified_uuids.append(user_uuid)
        yield NotificationEvent(
            user_notification=UserNotificationType.PAGING,
            iterable_event=IterableEvent.PAGING_CASE_POSTED_SPECIALTY_SUBSPECIALTY_USERS,
            # iterable_event=IterableEvent.PAGING_CASE_POSTED_SPECIALTY_USERS,
            user_uuid=user_uuid,
            case_uuid=case_uuid,
            source_uuid=author_uuids[0]
        )
    
    logger.info(f"PAGING DEBUG: Case {case_uuid} - Query 1 (specialty+subspecialty): Found {query1_count} users")

    # Users matching only specialty of case
    specialty_query = base_query.filter(SpecialtyTreeV2.specialty_v2_uuid.in_(case_specialty_uuids))
    if notified_uuids:
        specialty_query = specialty_query.filter(UserSpecialtyTreeV2.user_uuid.not_in(notified_uuids))
    
    query2_count = 0
    for res in specialty_query.yield_per(100).all():
        user_uuid = str(res[0])
        query2_count += 1
        notified_uuids.append(user_uuid)
        yield NotificationEvent(
            user_notification=UserNotificationType.PAGING,
            iterable_event=IterableEvent.PAGING_CASE_POSTED_SPECIALTY_USERS,
            user_uuid=user_uuid,
            case_uuid=case_uuid,
            source_uuid=author_uuids[0]
        )
    
    logger.info(f"PAGING DEBUG: Case {case_uuid} - Query 2 (specialty only): Found {query2_count} users")

    # Users matching only subspecialty of case
    subspecialty_query = base_query.filter(SpecialtyTreeV2.subspecialty_uuid.in_(case_specialty_uuids))
    if notified_uuids:
        subspecialty_query = subspecialty_query.filter(UserSpecialtyTreeV2.user_uuid.not_in(notified_uuids))
    
    query3_count = 0
    for res in subspecialty_query.yield_per(100).all():
        user_uuid = str(res[0])
        query3_count += 1
        yield NotificationEvent(
            user_notification=UserNotificationType.PAGING,
            iterable_event=IterableEvent.PAGING_CASE_POSTED_SUBSPECIALTY_USERS,
            # iterable_event=IterableEvent.PAGING_CASE_POSTED_SPECIALTY_USERS,
            user_uuid=user_uuid,
            case_uuid=case_uuid,
            source_uuid=author_uuids[0]
        )
    
    logger.info(f"PAGING DEBUG: Case {case_uuid} - Query 3 (subspecialty only): Found {query3_count} users")
    logger.info(f"PAGING DEBUG: Case {case_uuid} - Final notified_uuids count: {len(notified_uuids)}")


def get_notifications_not_chosen_diagnosis_cases(session: Session):
    def should_notify(case: Case):
        if case.has_diagnosis:
            return False
        if case.group_uuid:
            return False
        if case.case_classification is CaseClassification.NONMEDICAL:
            return False
        if any(label.kind == 'resolved' and label.deleted_at is None for label in case.labels):
            return False
        return True

    three_days_ago = datetime.now() - timedelta(hours=24 * 3)
    four_days_ago = datetime.now() - timedelta(hours=24 * 4)
    cases_approved_in_last_three_days = session.query(Case).filter(Case.state == CaseState.APPROVED,
                                                                   Case.published_at <= three_days_ago,
                                                                   Case.published_at >= four_days_ago).all()
    case_uuids = [str(each.case_uuid) for each in cases_approved_in_last_three_days if should_notify(each)]
    notified_cases = session.query(UserNotification) \
        .filter(UserNotification.case_uuid.in_(case_uuids),
                UserNotification.notification_type == UserNotificationType.CASE_NOT_DIAGNOSIS_CHOSEN) \
        .all()
    notified_cases_uuids = [str(each.case_uuid) for each in notified_cases]
    case_uuids_to_notify = set(case_uuids) - set(notified_cases_uuids)

    for author in session.query(CaseAuthor).filter(CaseAuthor.case_uuid.in_(case_uuids_to_notify)):
        yield NotificationEvent(
            user_notification=UserNotificationType.CASE_NOT_DIAGNOSIS_CHOSEN,
            iterable_event=IterableEvent.DIAGNOSIS_NOT_CHOSEN,
            user_uuid=author.author_uuid,
            case_uuid=author.case_uuid
        )


def get_notifications_activity_reminder(session: Session,
                                        timeframe: timedelta) -> [NotificationEvent]:
    if not isinstance(timeframe, timedelta):
        raise ValueError("timeframe must be timedelta type")

    check_time = utc_now(timezone=timezone.utc) - timeframe
    for uuid in session.query(distinct(UserNotification.user_uuid)) \
            .outerjoin(ActivityReminder, ActivityReminder.user_uuid == UserNotification.user_uuid) \
            .filter(UserNotification.state == UserNotificationState.NEW,
                    or_(ActivityReminder.last_sent.is_(None), ActivityReminder.last_sent < check_time)) \
            .all():
        yield NotificationEvent(
            user_notification=None,
            iterable_event=IterableEvent.ACTIVITY_REMINDER,
            user_uuid=str(uuid[0])
        )


def get_notifications_profession_change_approved(user_uuid: str):
    yield NotificationEvent(
        user_notification=UserNotificationType.PROFESSION_CHANGE_APPROVED,
        iterable_event=IterableEvent.PROFESSION_CHANGE_APPROVED,
        user_uuid=user_uuid
    )


def get_notifications_group_invite(group_filter_uuid: str,
                                   session: Session):
    gmf = GroupMemberFilter.get_by_uuid(session=session, uuid=group_filter_uuid)
    yield NotificationEvent(
        iterable_event=IterableEvent.GROUP_INVITE,
        user_uuid=str(gmf.user_uuid),
        source_uuid=str(gmf.inviter_uuid),
        group_uuid=str(gmf.group_uuid)
    )


def get_notifications_group_invite_accepted(group_uuid: str,
                                            user_uuid: str,
                                            session: Session):
    users_to_notify = set()

    # Notify user who sent the invite
    gmf = GroupMemberFilter.get_by_group_and_user_uuid(group_uuid=group_uuid,
                                                       user_uuid=user_uuid,
                                                       session=session)
    if gmf:
        users_to_notify.add(str(gmf.inviter_uuid))

    # Notify group creator
    g = GroupManagement.get_group(group_uuid=group_uuid, session=session)
    if g.groupCreatorUuid:
        users_to_notify.add(g.groupCreatorUuid)

    for receiver_uuid in users_to_notify:
        yield NotificationEvent(
            user_notification=UserNotificationType.GROUP_INVITE_ACCEPTED,
            iterable_event=IterableEvent.GROUP_INVITE_ACCEPTED,
            user_uuid=receiver_uuid,
            source_uuid=user_uuid,
            group_uuid=group_uuid
        )


def get_notifications_new_accepted_answer(source_user_uuid: str, comment_uuid: str, case_uuid: str, session: Session):
    """
    Find out if there are notifications to be created
    :param source_user_uuid:
    :param comment_uuid:
    :param case_uuid:
    :param session:
    :return:
    """
    case = Case.get_case(case_uuid=case_uuid, session=session)
    if _check_if_a_case_is_post(case=case):
        return StopIteration

    comment = Comment.get_comment(comment_uuid=comment_uuid, session=session)

    if not comment.is_accepted_answer:
        logger.error("Comment: %s is not an accepted answer.", comment_uuid)
        return

    list_of_authors = []
    for case_author in case.authors:
        list_of_authors.append(str(case_author.user_uuid))
    users_saved_case = list(UserSavedCase.users_saved_case(session=session, case_uuid=case.case_uuid))
    users_liked_case = CaseReaction.get_case_reactions(case_uuid=case_uuid, session=session)[Reaction.AGREE.value]
    users_commented_case = []
    for each_content in case.content:
        users_commented_case.extend(Comment.get_content_commenters(each_content.content_uuid, session=session))

    # remove the accepted answer comment author and case authors.
    users_saved_case = set(users_saved_case) - set(list_of_authors) - {str(comment.author_uuid)}
    users_liked_case = set(users_liked_case) - set(list_of_authors) - {str(comment.author_uuid)}
    users_commented_case = set(users_commented_case) - set(list_of_authors) - {str(comment.author_uuid)}

    comment_model = CommentModel.from_orm(comment)
    # Priority 1 - Your comment was chosen as the accepted answer.
    if comment_model.authorUuid not in list_of_authors:
        yield NotificationEvent(user_notification=UserNotificationType.NEW_ACCEPTED_ANSWER_SELECTED,
                                iterable_event=IterableEvent.CASE_NEW_ACCEPTED_ANSWER_SELECTED,
                                user_uuid=str(comment.author_uuid),
                                source_uuid=source_user_uuid,
                                case_uuid=case_uuid,
                                comment_uuid=comment_uuid)

    # Priority 2 - New accepted answer on a case you commented
    for user_uuid in users_commented_case:
        yield NotificationEvent(
            user_notification=UserNotificationType.NEW_ACCEPTED_ANSWER_COMMENTED_CASE,
            iterable_event=IterableEvent.CASE_NEW_ACCEPTED_ANSWER,
            user_uuid=user_uuid,
            source_uuid=source_user_uuid,
            case_uuid=case_uuid,
            comment_uuid=comment_uuid,
        )

    # Priority 3 - New accepted answer on a case you liked
    for user_uuid in users_liked_case - users_commented_case:
        yield NotificationEvent(
            user_notification=UserNotificationType.NEW_ACCEPTED_ANSWER_LIKED_CASE,
            iterable_event=IterableEvent.CASE_NEW_ACCEPTED_ANSWER,
            user_uuid=user_uuid,
            source_uuid=source_user_uuid,
            case_uuid=case_uuid,
            comment_uuid=comment_uuid,
        )

    # Priority 4 - New accepted answer on a case you saved
    for user_uuid in users_saved_case - users_commented_case - users_liked_case:
        yield NotificationEvent(
            user_notification=UserNotificationType.NEW_ACCEPTED_ANSWER_SAVED_CASE,
            iterable_event=IterableEvent.CASE_NEW_ACCEPTED_ANSWER,
            user_uuid=user_uuid,
            source_uuid=source_user_uuid,
            case_uuid=case_uuid,
            comment_uuid=comment_uuid,
        )


def get_notifications_accepted_answer_deleted(source_user_uuid: str, comment_uuid: str,
                                              case_uuid: str, session: Session):
    """
    Find out if there are notifications to be created
    :param source_user_uuid:
    :param comment_uuid:
    :param case_uuid:
    :param session:
    :return:
    """
    case = Case.get_case(case_uuid=case_uuid, session=session)
    if _check_if_a_case_is_post(case=case):
        return StopIteration

    for case_author in case.authors:
        yield NotificationEvent(user_notification=UserNotificationType.ACCEPTED_ANSWER_DELETED,
                                iterable_event=IterableEvent.CASE_ACCEPTED_ANSWER_DELETED,
                                user_uuid=str(case_author.user_uuid),
                                source_uuid=source_user_uuid,
                                case_uuid=case_uuid,
                                comment_uuid=comment_uuid)


def get_notifications_accepted_answer_not_chosen(case_uuid: str, session: Session):
    """
    :param case_uuid:
    :param session:
    :return:
    """
    case = Case.get_case(case_uuid=case_uuid, session=session)
    if _check_if_a_case_is_post(case=case):
        return StopIteration

    for case_author in case.authors:
        yield NotificationEvent(user_notification=UserNotificationType.CASE_NOT_ACCEPTED_ANSWER_CHOSEN,
                                iterable_event=IterableEvent.CASE_ACCEPTED_ANSWER_NOT_CHOSEN,
                                user_uuid=str(case_author.user_uuid),
                                case_uuid=case_uuid)
