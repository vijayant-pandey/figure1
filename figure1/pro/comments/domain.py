from uuid import UUID
from celery.canvas import Signature
from sqlalchemy.orm import Session
from typing import Optional
from typing import List

from figure1.notifications import notifies_users_of_accepted_answer_not_chosen_task
from figure1.events import CommentEvents
from figure1.events import AggregationEvents
from figure1.core import managed_session
from figure1.common.models.db import Comment
from figure1.common.models.db import UserNotification
from figure1.common.models.db import CommentReport
from figure1.common.models.db import User
from figure1.common.models.db import Content
from figure1.common.models.db import CommentTranslations
from figure1.common.models.db import CaseAuthor
from figure1.common.helpers import CommentSync
from figure1.common.types import ReportReason
from figure1.common.types import UserNotificationType
from figure1.common.types import CommentState

import logging

from figure1.events.comment_events import handle_accepted_answer_updated
from figure1.exceptions import CommentEditNotSupported
from figure1.exceptions import AcceptedAnswerError
from figure1.exceptions.user import InsufficientPermissions

logger = logging.getLogger(__name__)


def _should_prompt_for_accepted_answer(content: Content, case_authors: List[User], session: Session) -> bool:
    """
    Should prompt for accepted answer on the 3rd (non case author) comment
    :param content:
    :param case_authors:
    :param session:
    :return:
    """
    case_uuid = str(content.case_uuid)
    notification_sent = session.query(UserNotification) \
        .filter(UserNotification.notification_type == UserNotificationType.CASE_NOT_ACCEPTED_ANSWER_CHOSEN,
                UserNotification.case_uuid == case_uuid).one_or_none()

    if notification_sent:
        return False

    q = session.query(Comment).filter(Comment.content_uuid == content.content_uuid,
                                      Comment.author_uuid.notin_([each.author_uuid for each in case_authors]),
                                      Comment.state == CommentState.APPROVED)

    return not content.accepted_answer and q.count() == 3


def delete_reported_comment(comment_uuid, session):
    """
    This isn't ideal as it allows for someone to repost the same comment after deleting it, however at the moment
    we don't have a better approach here.
    :param comment_uuid:
    :param session:
    :return:
    """
    report = session.query(CommentReport).filter(CommentReport.comment_uuid == comment_uuid).one_or_none()
    if report:
        report.mark_deleted()
        session.merge(report)


@managed_session
def do_post_comment(user_uid, content_uuid, comment_text, parent_comment_uuid=None, session=None):
    # TODO - we should have a user flag to mark a problematic user. If this flag were set
    # TODO then comments made by this user would be set to PENDING_APPROVAL
    u = User.get_user_by_uid(user_uid=user_uid, session=session, raise_exception=True)

    c = Content.get_first_content_item(content_uuid=content_uuid, session=session)
    content_uuid = str(c.content_uuid)
    group_uuid = c.case.group_uuid
    if group_uuid and group_uuid not in (each.group_uuid for each in u.group_member):
        raise InsufficientPermissions(msg="Only group members are allowed to comment.")

    if c.features.comment_queue_enabled:
        state = CommentState.PENDING_APPROVAL
    else:
        state = CommentState.APPROVED

    authors = session.query(CaseAuthor).filter(CaseAuthor.case_uuid == c.case.case_uuid).all()
    is_anonymous = c.case.is_anonymous and u.user_uuid in (each.author_uuid for each in authors)
    cm = Comment.create(text=comment_text,
                        content_uuid=content_uuid,
                        author_uuid=u.user_uuid,
                        parent_uuid=parent_comment_uuid,
                        state=state,
                        session=session,
                        is_anonymous=is_anonymous)
    session.flush()
    logger.info("Comment created in database")
    task = CommentEvents.COMMENT_POSTED(comment=cm, user_uuid=str(u.user_uuid), session=session)
    if isinstance(task, Signature):
        task.link(AggregationEvents.ON_NEW_COMMENT_TASK.value.si(user_uuid=str(u.user_uuid)))
    else:
        task = AggregationEvents.ON_NEW_COMMENT_TASK.value.si(user_uuid=str(u.user_uuid))

    if not c.accepted_answer and _should_prompt_for_accepted_answer(content=c, case_authors=authors, session=session):
        task.link(notifies_users_of_accepted_answer_not_chosen_task.si(case_uuid=str(c.case_uuid)))
    if isinstance(task, Signature):
        task.apply_async()
    return {'success': 'Comment created', 'uuid': str(cm.comment_uuid)}


@managed_session
def do_translate_comment(comment_uuid, target_language, session):
    translation = CommentTranslations.translate(comment_uuid=comment_uuid, to_language=target_language)
    t = session.merge(translation)
    session.flush()
    CommentEvents.COMMENT_UPDATED(comment=t.comment, session=session)
    return {'success': 'comment translated'}


@managed_session
def do_edit_comment(user_uid, comment_uuid, comment_text, session):
    u = User.get_user_by_uid(user_uid=user_uid, session=session, raise_exception=True)
    cm = Comment.get_comment(comment_uuid=comment_uuid, session=session)

    if cm.is_accepted_answer:
        raise CommentEditNotSupported(msg="Editing of accepted answers is not allowed")

    cm.text = comment_text
    cm.edited = True
    session.add(cm)
    session.flush()

    group_uuid = cm.content.case.group_uuid
    if group_uuid and group_uuid not in (each.group_uuid for each in u.group_member):
        raise InsufficientPermissions(msg="Only group members are allowed to edit comment.")

    if cm.state is not CommentState.APPROVED:
        raise CommentEditNotSupported(msg="Cannot edit an unapproved comment")

    if cm.content.features.comment_queue_enabled:
        raise CommentEditNotSupported(msg="Cannot edit comment for case with comment queue enabled")

    if cm.author_uuid != u.user_uuid:
        raise CommentEditNotSupported(msg="Only the comment author can edit their own comment")

    CommentEvents.COMMENT_UPDATED(comment=cm, session=session)

    return {'success': 'Comment edited', 'uuid': comment_uuid}


@managed_session
def do_report_comment(reporting_user_uid: str,
                      report_reason: ReportReason,
                      text: Optional[str],
                      comment_uuid: UUID,
                      session: Session):
    u = User.get_user_by_uid(user_uid=reporting_user_uid, session=session, raise_exception=True)
    ret = CommentReport.create_report(user_uuid=str(u.user_uuid),
                                      comment_uuid=comment_uuid,
                                      text=text,
                                      report_reason=report_reason,
                                      session=session)

    comment: Comment = session.query(Comment).get(comment_uuid)

    group_uuid = comment.content.case.group_uuid
    if group_uuid and group_uuid not in (each.group_uuid for each in u.group_member):
        raise InsufficientPermissions(msg="Only group members are allowed to report comment.")

    if comment:
        comment.replyable = False
        comment.state = CommentState.REPORTED
        cm = session.merge(comment)
        CommentEvents.COMMENT_REPORTED(comment=cm, session=session)
        return {'success': 'comment reported'}
    else:
        return {'error': 'comment not found'}


@managed_session
def do_delete_comment(comment_uuid, session=None):
    delete_reported_comment(comment_uuid=comment_uuid, session=session)
    comment = session.query(Comment).filter(Comment.comment_uuid == comment_uuid).one_or_none()

    is_accepted_answer = False
    if comment:
        is_accepted_answer = comment.is_accepted_answer
        comment.mark_deleted()
        comment.replyable = False
        comment.comment_uuid = comment_uuid
        comment.state = CommentState.DELETED
        comment.is_accepted_answer = False
        deleted_comment = session.merge(comment)
        CommentEvents.COMMENT_DELETED(comment=deleted_comment,
                                      suppress_user_notification=True,
                                      session=session,
                                      is_accepted_answer=is_accepted_answer)
    else:
        return {'error': 'No comment found'}

    if is_accepted_answer:
        handle_accepted_answer_updated(comment=comment, session=session)
    return {'success': 'comment deleted'}


@managed_session
def get_one_comment(comment_uuid, session=None):
    c = CommentSync.get_comment(comment_uuid=comment_uuid, session=session)
    if not c:
        return {'error': 'Unable to find comment'}
    return c.as_dict()


@managed_session
def get_all_comments(content_uuid, tree=True, session=None):
    comment = CommentSync.get_all_comments(tree=tree, content_uuid=content_uuid, session=session)
    return comment


@managed_session
def add_or_remove_accepted_answer(is_accepted_answer: bool, comment_uuid: str, user_uid: str, session: Session):
    if not isinstance(is_accepted_answer, bool):
        raise AcceptedAnswerError(msg="The is_accepted_answer should be a boolean value")

    previous_accepted_answer = None
    source_user = User.get_user_by_uid(user_uid=user_uid, session=session, raise_exception=True)
    comment = Comment.get_comment(comment_uuid=comment_uuid, session=session)
    review_states = [CommentState.REPORTED, CommentState.FLAGGED]
    if is_accepted_answer:
        if comment.state is not CommentState.APPROVED:
            raise AcceptedAnswerError(msg='Only comments that are in the APPROVED state '
                                          'are selectable as accepted answers')

        content = comment.content
        if content.accepted_answer and content.accepted_answer.state is CommentState.FLAGGED:
            raise AcceptedAnswerError(msg='Can not select a new accepted answer while '
                                          'an existing accepted answer is waiting for moderation review')
        elif content.accepted_answer:
            content.accepted_answer.is_accepted_answer = False
            session.merge(content.accepted_answer)

            if content.accepted_answer.comment_uuid != comment_uuid:
                previous_accepted_answer = content.accepted_answer
    elif not is_accepted_answer and comment.is_accepted_answer and comment.state in review_states:
        raise AcceptedAnswerError(msg='The case author does not have the option to remove their selected comment/reply '
                                      'as the accepted answer while waiting for moderation review')

    comment.is_accepted_answer = is_accepted_answer
    session.merge(comment)

    session.flush()

    CommentEvents.ACCEPTED_ANSWER_UPDATED(comment=comment, session=session, source_user_uuid=str(source_user.user_uuid))
    if previous_accepted_answer:
        CommentEvents.PREVIOUS_ACCEPTED_ANSWER_REMOVED(comment=previous_accepted_answer)
    return {'success': 'accepted answer was updated'}
