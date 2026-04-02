import logging
from typing import Optional

from celery.canvas import Signature
from elasticsearch.exceptions import NotFoundError
from elasticsearch.exceptions import SerializationError
from google.api_core.exceptions import DeadlineExceeded
from google.api_core.exceptions import GoogleAPIError
from google.cloud.firestore_v1 import WriteBatch
from sqlalchemy import desc
from sqlalchemy import func
from sqlalchemy import or_

from figure1.common.elasticsearch import get_case
from figure1.common.firebase.utils import delete_deep_collection
from figure1.common.helpers import FeedCard
from figure1.common.models.db import Case
from figure1.common.models.db import CaseAuthor
from figure1.common.models.db import Comment
from figure1.common.models.db import User
from figure1.common.models.db import UserState
from figure1.common.models.firebase import FirebaseCollectionManager
from figure1.common.types import CaseState
from figure1.common.types import CaseType
from figure1.common.types import CommentState
from figure1.core import celery_app
from figure1.core import FirebaseTaskBase
from figure1.exceptions import UserNotFound

fb = FirebaseCollectionManager()
logger = logging.getLogger(__name__)


class HandleDeadlock(Exception):
    pass


class BatchManager:
    """
    Use this class to handle batches to avoid counting issues.
    """
    batch_: WriteBatch = None
    batch_count = 0

    @classmethod
    @property
    def batch(cls):
        if cls.batch_ is None:
            try:
                cls.batch_ = fb.fs_client.batch()
            except AttributeError:
                logger.error("Firebase not configured")
                return None
        return cls.batch_

    @classmethod
    def _increment_batch(cls):
        if not cls.batch_count % 500:
            cls.batch.commit()
        cls.batch_count += 1

    @classmethod
    def set(cls, client, doc, merge=True):
        cls._increment_batch()
        cls.batch.set(client, doc, merge=merge)

    @classmethod
    def delete(cls, client):
        cls._increment_batch()
        cls.batch.delete(client)

    @classmethod
    def commit(cls):
        """
        When this is called, the batch is commited and the count set to 0. This is only necessary to clean up at the
        end of an iteration.
        :return:
        """
        cls.batch.commit()
        cls.batch_count = 0


@celery_app.task(bind=True,
                 base=FirebaseTaskBase,
                 autoretry_for=(HandleDeadlock, DeadlineExceeded,),
                 name='figure1.backend.user_profile_case_update')
def update_profile_cases_task(self, offset=0, case_uuid=None):
    case_authors = self.session.query(CaseAuthor).filter(CaseAuthor.case_uuid == case_uuid)
    if case_uuid is not None:
        update_case_activity(case_uuid=case_uuid, session=self.session)
        for author in case_authors.all():
            update_profile_stats(session=self.session, user_uuid=str(author.author_uuid))
    else:
        update_all_cases(offset=offset, session=self.session)


@celery_app.task(bind=True,
                 base=FirebaseTaskBase,
                 autoretry_for=(HandleDeadlock, DeadlineExceeded,),
                 name='figure1.backend.user_profile_comments_update')
def update_profile_comments_task(self, offset=0):
    update_all_comments(session=self.session, offset=offset)


@celery_app.task(bind=True,
                 base=FirebaseTaskBase,
                 autoretry_for=(GoogleAPIError,),
                 name='figure1.backend.user_profile_stats_update')
def update_profile_stats_task(self, offset=0, user_uuid=None):
    logger.info("Starting profile stats update")
    next_task, user_count = update_profile_stats(session=self.session, offset=offset, user_uuid=user_uuid)
    if next_task is not None:
        next_task.apply_async()
    return f"Updated {user_count} users"


@celery_app.task(bind=True,
                 base=FirebaseTaskBase,
                 autoretry_for=(GoogleAPIError,),
                 name='figure1.backend.user_update_all_activities')
def update_all_activities_task(self, user_uuid):
    update_all_activities(user_uuid=user_uuid, session=self.session)


@celery_app.task(bind=True,
                 base=FirebaseTaskBase,
                 autoretry_for=(GoogleAPIError,),
                 name='figure1.backend.user_verify_activity_count')
def verify_user_activity_count_task(self, user_uuid):
    """
    If the count does not match,
    :param self:
    :param user_uuid:
    :return:
    """
    task = verify_profile_activity(user_uuid=user_uuid)
    if isinstance(task, Signature):
        task.apply_async()
        return "Activity count does not match - running update"
    else:
        return f"User count for user {user_uuid} matches"


def verify_profile_activity(user_uuid) -> Optional[Signature]:
    logger.error("Checking user %s", user_uuid)
    fs_client = fb.fs_client.collection('usersProfileDB').document(user_uuid).collection('activity')
    activity_count = len(list(fs_client.list_documents()))
    user_doc_dict = fb.fs_client.collection('usersProfileDB').document(user_uuid).get().to_dict()
    batch = BatchManager().batch
    if user_doc_dict:
        recorded_activity_count = user_doc_dict.get('activityCount', 0)
        if activity_count != recorded_activity_count:
            logger.error(
                "User activity count for user %s does not match, %s documents exist, and %s is recorded as the count",
                user_uuid,
                activity_count,
                recorded_activity_count)
            delete_deep_collection(top_level_client=fs_client, batch_client=batch)
            batch.commit()
            logger.info("Started update all activities task for user %s", user_uuid)

            return update_all_activities_task.si(user_uuid=user_uuid)
        else:
            logger.info("Activity count matches the number of documents for user %s", user_uuid)
            return None
    else:
        logger.error("No user %s found in profile, regenerating", user_uuid)
        return update_all_activities_task.si(user_uuid=user_uuid)


def update_all_cases(session, offset=0):
    q = session.query(Case) \
        .filter(or_(Case.state == CaseState.APPROVED, Case.state == CaseState.SC_APPROVED),
                Case.group_uuid.is_(None),
                or_(Case.is_anonymous.is_(False), Case.is_anonymous.is_(None))) \
        .order_by(Case.published_at.desc())
    if offset:
        logger.info("Using offset %s for case profile update", offset)
        q = q.offset(offset)
    for i, case in enumerate(q.all()):
        update_case_activity(case_uuid=str(case.case_uuid), session=session)
        if not i % 100:
            logger.error("Case offset now at %s", offset + i)


def update_all_comments(session, offset=0):
    """

    :param session:
    :param offset: If passed, start from this result instead of the beginning
    :return:
    """
    q = session.query(Comment.author_uuid, func.count(Comment.comment_uuid).label("comment_count")) \
        .filter(Comment.state == CommentState.APPROVED).group_by(Comment.author_uuid).order_by(desc("comment_count"))
    if offset:
        logger.info("Using offset %s for comment profile update", offset)
        q = q.offset(offset)
    for i, u in enumerate(q.all()):
        user_uuid = str(u[0])
        logger.info("Updating comments for user %s who has %s comments", user_uuid, u[1])
        update_comment_activity(user_uuid=user_uuid, session=session)
        if not i % 100:
            logger.error("Comment offset now at %s", offset + i)


def update_profile_stats(session, offset=0, user_uuid=None, limit=10000):
    batch_manager = BatchManager()
    q = session.query(User).filter(User.deleted_at.is_(None)).order_by(User.updated_at.desc())

    if user_uuid is not None:
        q = q.filter(User.user_uuid == user_uuid)
    elif offset:
        logger.info("Using offset %s for user profile update", offset)
        q = q.offset(offset)
    for user in q.yield_per(1000).limit(10000).all():
        approved_case_count = 0
        if user.cases is not None:
            for case in user.cases:
                if case.state == CaseState.APPROVED or case.state == CaseState.SC_APPROVED:
                    approved_case_count += 1
        user.approved_case_count = approved_case_count
        comment_count = Comment.get_comment_count(user_uuid=str(user.user_uuid), include_anonymous=False)
        approved_comment_count = comment_count.get('approved_comment_count', 0)
        total = approved_comment_count + user.approved_case_count
        fb.set_fs_client(documents=[str(user.user_uuid)], collections=['usersProfileDB'])
        batch_manager.set(fb.fs, {'activityCount': total,
                                  'approvedCaseCount': user.approved_case_count,
                                  'approvedCommentCount': approved_comment_count,
                                  'userUuid': str(user.user_uuid)}, merge=True)
        session.add(user)
        session.flush()
    if user_uuid:
        batch_manager.commit()
        return None, 1
    logger.info("Processed %s users", q.limit(limit).count() + offset)
    if q.count() == 0:
        logger.info("All users up to date")
        return None, q.limit(limit).count() + offset
    batch_manager.commit()
    return update_profile_stats_task.si(offset=offset + q.limit(limit).count()), q.limit(limit).count() + offset


def reset_user_activity_sync_state(session):
    for u in session.query(User) \
            .filter(User.deleted_at.is_(None)) \
            .filter(User.user_uid.isnot(None)) \
            .all():
        if u.user_state:
            u.user_state.activity_sync_complete = False
        else:
            u.user_state = UserState()
            u.user_state.user_uuid = u.user_uuid
            u.user_state.activity_sync_complete = False
        session.add(u)
        session.flush()
    session.commit()


def _get_case_activity_data(case_uuid):
    try:
        case_detail = get_case(case_uuid)
    except (NotFoundError, SerializationError) as nfe:
        logger.exception("Case not in elasticsearch")
        return None
    if case_detail:
        logger.debug("Getting data for case %s", case_uuid)
        case_data = FeedCard.feed_card(feed_item=case_detail)
        if case_data:
            # Temporary fix to resolve CM/CME which may not have media in the location clients expect
            if not case_data.get('media') and case_data.get('feedCardMedia'):
                case_data['media'] = [case_data.get('feedCardMedia')]
            logger.debug("Updating case data")
            case_data.update({'type': 'case'})
            return case_data
        else:
            return None
    else:
        return None


def update_case_activity(session, user_uuid=None, case_uuid=None):
    """
    Updates all cases for a given user
    :param user_uuid: Optional - If passed, updates all cases for this user
    :param session:
    :param case_uuid: Optional - if passed, only update this case
    :param batch: Firestore batch, if passed, use this batch.
    :return:
    """

    def _update_case(case, batch_manager):
        c_case_uuid = str(case.case_uuid)
        authors = session.query(CaseAuthor).filter(CaseAuthor.case_uuid == c_case_uuid)
        logger.debug("Updating case %s", c_case_uuid)
        if case.group_uuid:
            return
        if case.is_anonymous:
            return
        if case.case_type == CaseType.PROMO_CARD:
            return

        if case.state == CaseState.APPROVED or case.state == CaseState.SC_APPROVED:
            case_data = _get_case_activity_data(c_case_uuid)
            for author in authors.all():
                logger.debug("Updating author %s", author.author_uuid)
                fb.set_fs_client(documents=[str(author.author_uuid), c_case_uuid],
                                 collections=['usersProfileDB', 'activity'])
                if case_data:
                    batch_manager.set(fb.fs, case_data)
        else:
            for author in authors.all():
                fb.set_fs_client(documents=[str(author.author_uuid), c_case_uuid],
                                 collections=['usersProfileDB', 'activity'])
                logger.error("Deleting case uuid %s in profile %s", c_case_uuid, author.author_uuid)
                batch_manager.delete(fb.fs)

    batch_manager = BatchManager()

    if case_uuid is not None:
        c = Case.get_case(case_uuid=case_uuid, session=session)
        _update_case(c, batch_manager=batch_manager)

    elif user_uuid is not None:
        user = User.get_user_by_uuid(user_uuid=user_uuid, session=session, raise_exception=True)
        for i, c in enumerate(user.cases):
            _update_case(c, batch_manager=batch_manager)

    else:
        raise ValueError("Either a case_uuid or a user_uuid is required")

    batch_manager.commit()


def update_comment_activity(session, user_uuid=None, comment_uuid=None):
    def _update_comment_profile(comment: Comment, batch_manager):
        fb.set_fs_client(documents=[user_uuid, str(comment.comment_uuid)], collections=['usersProfileDB', 'activity'])
        if comment.state != CommentState.APPROVED:
            logger.error("Deleting comment")
            fb.fs.delete()
            return
        if comment.content and comment.content.case:
            if comment.content.case.group_uuid:
                return
            if comment.is_anonymous:
                return

            case_type = comment.content.case.case_type
            case_uuid = comment.content.case.case_uuid
        else:
            case_type = None
            case_uuid = None
        fs = {
            'createdAt': str(comment.created_at),
            'type': 'comment',
            'commentUuid': str(comment.comment_uuid),
            'text': comment.text,
            'caseTitle': comment.content.title,
            'caseCaption': comment.content.caption,
            'caseUuid': str(case_uuid),
            'caseType': None,
        }
        if case_type is not None:
            fs.update({'caseType': case_type.name.lower()})
        batch_manager.set(fb.fs, fs)

    batch_manager = BatchManager()

    if comment_uuid is not None:
        comment = Comment.get_comment(comment_uuid=comment_uuid, session=session)
        _update_comment_profile(comment, batch_manager=batch_manager)
    else:
        all_comments = session.query(Comment).filter(Comment.author_uuid == user_uuid,
                                                     Comment.state == 'APPROVED',
                                                     Comment.deleted_at.is_(None))
        for i, c in enumerate(all_comments.yield_per(100).all()):
            logger.debug("Updating comment %s for user %s", c.comment_uuid, user_uuid)
            _update_comment_profile(comment=c, batch_manager=batch_manager)
    batch_manager.commit()
    return


def update_all_activities(user_uuid, session):
    """
    Updates both cases and comments and updates the total stats for each
    :param user_uuid:
    :param session:
    :return:
    """
    logger.debug("Handling user %s", user_uuid)
    try:
        u = User.get_user_by_uuid(user_uuid=user_uuid, session=session, raise_exception=True)
    except UserNotFound:
        logger.error("No user found")
        return None
    session.refresh(u)

    logger.debug("Updating case activity for user %s", user_uuid)
    update_case_activity(user_uuid=user_uuid, session=session)
    logger.debug("Updating comment activity for user %s", user_uuid)
    update_comment_activity(user_uuid=user_uuid, session=session)
    logger.debug("Updating stats for user %s", user_uuid)
    update_profile_stats(session=session, user_uuid=user_uuid)
    logger.info("Update complete for user %s", user_uuid)
