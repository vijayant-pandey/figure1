import logging
from typing import Optional
from uuid import UUID

from celery.canvas import Signature
from sqlalchemy.orm import Session

from figure1.common.elasticsearch import add_or_update_comment
from figure1.common.elasticsearch import update_case_fields
from figure1.common.firebase import do_firebase_sync
from figure1.common.helpers import CommentDetail
from figure1.common.helpers import CommentSync
from figure1.common.models.db import Case
from figure1.common.models.db import Comment
from figure1.common.models.db import CommentTranslations
from figure1.common.models.db import Content
from figure1.common.models.firebase import FirebaseCollectionManager
from figure1.common.models.firebase.anonymous_authors_db import sync_user_anonymous_comment_task
from figure1.common.types import CommentState
from figure1.common.types import PublicCommentStates
from figure1.common.types.comment import CommentModeratorReviewStatus
from figure1.notifications import log_comment_and_notify_task
from figure1.notifications import log_comment_delete_and_notify_task
from figure1.notifications import notifies_users_of_accepted_answer_deleted_task
from figure1.notifications import notifies_users_of_new_accepted_answer_task

fb = FirebaseCollectionManager()
logger = logging.getLogger(__name__)


def _update_content_comment_counts(content_uuid, session):
    content_comment_count = Comment.get_comment_count(content_uuid=content_uuid, include_anonymous=True)
    c = session.query(Content).get(content_uuid)
    for k, v in content_comment_count.items():
        setattr(c, k, v)
    session.add(c)
    session.flush()
    return content_comment_count


def _get_case_comment(user_uuid, comment_uuid, session=None):
    c = session.query(Comment, Content, Case) \
        .filter(Comment.author_uuid == user_uuid,
                Comment.comment_uuid == comment_uuid) \
        .join(Content, Content.content_uuid == Comment.content_uuid) \
        .join(Case, Case.case_uuid == Content.case_uuid).one_or_none()
    if c[2].group_uuid:
        return {}
    return {
        'createdAt': str(c[0].created_at),
        'updatedAt': str(c[0].updated_at),
        'type': 'comment',
        'commentUuid': str(c[0].comment_uuid),
        'text': c[0].text,
        'caseTitle': c[1].title,
        'caseCaption': c[1].caption,
        'caseUuid': str(c[1].case_uuid),
        'caseType': c[2].case_type.name.lower(),
        'isAnonymous': c[0].is_anonymous,
    } if c else {}


def _sync_comment_to_es(comment, session):
    comment_detail = CommentDetail.elasticsearch_comment(comment_uuid=str(comment.comment_uuid), session=session)
    add_or_update_comment(comment_uuid=str(comment.comment_uuid), comment_detail=comment_detail)


def _sync_partial_comment_to_es(comment_uuid: str, partial_comment_detail: dict):
    add_or_update_comment(comment_uuid=comment_uuid, comment_detail=partial_comment_detail)


def _update_comment(comment, session):
    """
    Update the comment count, then push the comment and branch to firestore and elasticsearch
    :param comment:
    :param session:
    :return:
    """
    session.refresh(comment)

    if comment.translations:
        CommentTranslations.update_translations(comment_uuid=comment.comment_uuid, session=session)

    content = session.query(Content).get(comment.content_uuid)
    session.refresh(content)
    content_comment_count = _update_content_comment_counts(content_uuid=comment.content_uuid, session=session)
    session.add(content)
    case_uuid = str(content.case_uuid)

    comment_count_total = 0
    fb.set_fs_client(documents=[case_uuid], collections=['casesDBv2'])
    logger.debug("Fetching case from firestore for updating")
    case_detail: dict = fb.get().to_dict()
    if case_detail:
        for i, c in enumerate(case_detail.get('contentItems', [])):
            if c.get("contentUuid") == str(comment.content_uuid):
                comment_count_total += content_comment_count.get('approved_comments_count', 0)
                case_detail['contentItems'][i]['commentCount'] = content_comment_count.get(
                    'approved_comments_count', 0)
            else:
                comment_count_total += case_detail['contentItems'][i]['commentCount']
        case_detail['commentCount'] = comment_count_total

        if comment.is_accepted_answer:
            if comment.state is CommentState.REPORTED:
                case_detail.update({"acceptedAnswer": {"isReported": True}})

            elif comment.state is not CommentState.APPROVED and case_detail.get('acceptedAnswer', {}):
                case_detail.pop("acceptedAnswer")

            else:
                accepted_answer = CommentSync.get_comment_dict_from_object(comment_object=comment.as_object(),
                                                                           session=session)
                case_detail.update({"acceptedAnswer": accepted_answer})
        logger.debug("Updating firestore with content counts")
        fb.set(case_detail, merge=True)
        logger.debug("Updating comment counts in elasticsearch")
        update_case_fields(case_uuid=case_uuid, case_field_name='commentCount', case_field_value=comment_count_total)
        has_approved_accepted_answer = comment.is_accepted_answer and comment.state is CommentState.APPROVED
        logger.debug("Updating case hasAcceptedAnswer in elasticsearch")
        update_case_fields(case_uuid=case_uuid,
                           case_field_name='hasAcceptedAnswer',
                           case_field_value=has_approved_accepted_answer)
    parent = str(UUID(comment.path[0].path))

    to_sync = CommentSync.generate_tree_branch(comment_uuid=comment.comment_uuid, session=session)
    fb.set_fs_client(documents=[case_uuid, to_sync[parent]['commentUuid']],
                     collections=['casesDBv2', str(comment.content_uuid)])
    logger.debug("Syncing comment tree to firestore")
    fb.set(to_sync[parent], merge=True)
    logger.debug("Finished syncing comment tree to firestore")
    logger.debug("Syncing comment to elasticsearch")
    _sync_comment_to_es(comment=comment, session=session)
    logger.debug("Finished syncing comment to elasticsearch")
    return to_sync[parent]


def handle_comment_posted(comment: Comment, user_uuid: str, session: Session) -> Signature:
    """
    :param comment: Comment object - bound to the passed in session
    :param user_uuid: user_uuid in string form - used for notifications
    :param session: Active session object
    :return None:
    """
    state = comment.state
    content_uuid = str(comment.content_uuid)
    if state == CommentState.PENDING_APPROVAL:
        _sync_comment_to_es(comment=comment, session=session)
    else:
        logger.debug("Updating user profile activity")

        logger.debug("Updating comment counts and tree in firestore")
        _update_comment(comment=comment, session=session)
        task = log_comment_and_notify_task.si(
            user_uuid=user_uuid,
            content_uuid=content_uuid,
            comment_uuid=comment.comment_uuid)
        if comment.is_anonymous:
            logger.debug("Syncing anonymous comment in firestore")
            task.link(sync_user_anonymous_comment_task.si(user_uuid=user_uuid, comment_uuid=str(comment.comment_uuid)))
        task.link(do_firebase_sync.si(firebasemodel='FirebaseUsersProfileDB', uuid=str(comment.author_uuid)))
        return task


def handle_comment_updated(comment: Comment, session: Session) -> None:
    """
    :param comment: Comment object - bound to the passed in session
    :param session: Active session object
    :return None:
    """
    if comment.state not in [x.value for x in PublicCommentStates]:
        _sync_comment_to_es(comment=comment, session=session)
    else:
        logger.debug("Updating comment counts and tree in firestore")
        _update_comment(comment=comment, session=session)
        logger.info("Sync users profile")
        do_firebase_sync.delay(firebasemodel='FirebaseUsersProfileDB', uuid=str(comment.author_uuid))


def handle_comment_reported(comment: Comment, session: Session) -> None:
    """
    :param comment: Comment object - bound to the passed in session
    :param session: Active session object
    :return None:
    """
    _update_comment(comment=comment, session=session)
    do_firebase_sync.delay(firebasemodel='FirebaseUsersProfileDB', uuid=str(comment.author_uuid))


def handle_comment_deleted(comment: Comment,
                           suppress_user_notification: bool,
                           session: Session,
                           moderator_uuid: Optional[str] = None,
                           is_accepted_answer: Optional[bool] = False) -> None:
    """
    :param comment: Comment object - bound to the passed in session
    :param suppress_user_notification: True if a user notification should not be created, for example if the
    comment author deleted their own comment
    :param session: Active session object
    :param moderator_uuid:  The uuid of the moderator performing the action.
    :param is_accepted_answer:
    :return None:
    """
    _update_comment(comment=comment, session=session)

    task = do_firebase_sync.si(firebasemodel='FirebaseUsersProfileDB', uuid=str(comment.author_uuid))
    if not suppress_user_notification:
        task.link(log_comment_delete_and_notify_task.si(
            comment_uuid=comment.comment_uuid,
            author_uuid=comment.author_uuid,
            moderator_uuid=moderator_uuid))

    # should send deleted accepted answer notification to the case author.
    if is_accepted_answer:
        task.link(notifies_users_of_accepted_answer_deleted_task.si(source_user_uuid=moderator_uuid,
                                                                    comment_uuid=str(comment.comment_uuid),
                                                                    case_uuid=str(comment.content.case_uuid)))
    task.apply_async()


def handle_accepted_answer_updated(comment: Comment, session: Session, source_user_uuid: Optional[str] = None):
    """
    :param comment:  Comment object for accepted answer that was updated
    :param source_user_uuid: User uuid of the user making the update
    :param session: Active session object
    :return:
    """
    fb.set_fs_client(documents=[str(comment.content.case_uuid)], collections=['casesDBv2'])
    case_uuid = str(comment.content.case_uuid)
    if comment.is_accepted_answer and comment.state == CommentState.APPROVED:
        accepted_answer = CommentSync.get_comment_dict_from_object(comment_object=comment.as_object(), session=session)
        fb.set({"acceptedAnswer": accepted_answer}, merge=True)
        task = notifies_users_of_new_accepted_answer_task.si(source_user_uuid=source_user_uuid,
                                                             comment_uuid=str(comment.comment_uuid),
                                                             case_uuid=case_uuid)
        task.apply_async(countdown=300)
    else:
        fb.delete("acceptedAnswer")

    _update_comment(comment=comment, session=session)
    _sync_comment_to_es(comment=comment, session=session)


def handle_previous_accepted_answer_removed(comment: Comment):
    """
    :param comment:  Comment object for accepted answer that was updated
    :return:
    """
    case_uuid = str(comment.content.case_uuid)
    content_uuid = str(comment.content_uuid)
    comment_uuid = str(comment.comment_uuid)

    logger.debug("Syncing comment tree to firestore for removing previous accepted answer")
    parent_uuid = str(UUID(comment.path[0].path))
    fb.set_fs_client(documents=[case_uuid, parent_uuid],
                     collections=['casesDBv2', content_uuid])
    if parent_uuid == comment_uuid:
        fb.set({"isAcceptedAnswer": False}, merge=True)
    else:
        fb.set({"children": {comment_uuid: {"isAcceptedAnswer": False}}}, merge=True)
    logger.debug("Finished syncing comment tree to firestore for removing previous accepted answer")

    logger.debug("Syncing comment to elasticsearch for removing previous accepted answer")
    _sync_partial_comment_to_es(comment_uuid, {"isAcceptedAnswer": False})
    logger.debug("Finished syncing comment to elasticsearch for removing previous accepted answer")


def handle_accepted_answer_reviewed(comment_uuid: str):
    """
    :param comment_uuid: comment uuid for accepted answer that was updated
    :return:
    """
    _sync_partial_comment_to_es(comment_uuid, {"moderatorReviewed": True,
                                               "moderatorReviewStatus": CommentModeratorReviewStatus.REVIEWED.value})


def handle_accepted_answer_pending_review(comment_uuid: str):
    """
    :param comment_uuid: comment uuid for accepted answer that was updated
    :return:
    """
    _sync_partial_comment_to_es(comment_uuid,
                                {"moderatorReviewed": False,
                                 "moderatorReviewStatus": CommentModeratorReviewStatus.PENDING_REVIEW.value})
