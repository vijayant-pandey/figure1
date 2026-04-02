import logging
from datetime import datetime
from datetime import timedelta
from datetime import timezone

from celery import group
from firebase_admin.auth import UserNotFoundError
from firebase_admin.auth import delete_user
from google.cloud.firestore_v1 import WriteBatch
from sqlalchemy import distinct
from sqlalchemy import or_
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import Session

from figure1.aggregation import generate_user_recommendations_task
from figure1.common.firebase.utils import delete_collection_batch
from figure1.common.iterable import bulk_update_users
from figure1.common.models.db import CaseAuthor
from figure1.common.models.db import Comment
from figure1.common.models.db import User
from figure1.common.models.db import UserFollow
from figure1.common.models.db import UserProfile
from figure1.common.models.db import UserState
from figure1.common.models.firebase import FirebaseUsersProfileDB
from figure1.common.types import FirebaseAction
from figure1.configuration import app_settings
from figure1.core import FirebaseTaskBase
from figure1.core import TaskBase
from figure1.core import celery_app
from figure1.core import managed_session
from figure1.events.user_events import fix_figure1_followers_task
from figure1.events.user_events import update_user_follow_following_collections
from figure1.store import IterableSyncQueue
from figure1.store import Recommended
from figure1.store import TaskLock
from figure1.store import TaskQueue

logger = logging.getLogger('figure1.tools.domain')


def _commit_batch(session: Session, batch: WriteBatch):
    try:
        session.commit()
    except DatabaseError as e:
        session.rollback()
        logging.error(f"Failed to commit: {e}")
        raise
    batch.commit()


def _get_users_with_case_or_comment(limit: int, session: Session):
    comment_authors = session.query(
        distinct(Comment.author_uuid).label('author_uuid')
    ).subquery()
    case_authors = session.query(
        distinct(CaseAuthor.author_uuid).label('author_uuid')
    ).subquery()

    return session.query(UserProfile.user_uuid) \
        .join(comment_authors, comment_authors.c.author_uuid == UserProfile.user_uuid, full=True) \
        .join(case_authors, case_authors.c.author_uuid == UserProfile.user_uuid, full=True) \
        .filter(or_(comment_authors.c.author_uuid.isnot(None), case_authors.c.author_uuid.isnot(None)),
                UserProfile.synced_at.is_(None)) \
        .order_by(UserProfile.user_uuid) \
        .limit(limit) \
        .all()


@managed_session
def sync_deleted_users(session: Session):
    for u in session.query(User) \
            .filter(User.deleted_at.isnot(None), User.user_uid.isnot(None)) \
            .all():
        _sync_deleted_user_task.delay(user_uid=u.user_uid)


@celery_app.task(bind=True,
                 base=FirebaseTaskBase,
                 name='figure1.backend.sync_deleted_user',
                 rate_limit='30/m')
def _sync_deleted_user_task(self: FirebaseTaskBase, user_uid: str):
    try:
        delete_user(uid=str(user_uid), app=self.fs_app)
        logging.info(f"Deleted auth record for user: {user_uid}")
    except UserNotFoundError:
        pass


@celery_app.task(bind=True,
                 base=FirebaseTaskBase,
                 name='figure1.backend.sync_unsynced_users_task')
def sync_unsynced_users_task(self: FirebaseTaskBase, limit: int = 1000) -> None:
    tl = TaskLock(self.request.task)
    tq = TaskQueue(self.request.task)
    if not tl.create_lock(self.request.id):
        logger.error("User sync task locked")
        return
    if not app_settings.user_sync_enabled:
        logging.info("user sync is disabled, nothing to do")
        return

    count = 0
    batch = self.fs_client.batch()

    if not tq.get_queue_len():
        items = set()
        for x in _get_users_with_case_or_comment(limit=limit, session=self.session):
            items.add(str(x.user_uuid))
        if len(list(items)):
            tq.write_queue(list(items))
        else:
            logger.info("No users to sync")
    while tq.get_queue_len() > 0:
        user_uuid = tq.get_item()
        if not user_uuid:
            continue
        for update in FirebaseUsersProfileDB.sync(firebase_db=self.fs_client,
                                                  user_uuid=user_uuid,
                                                  action=FirebaseAction.SET,
                                                  session=self.session):
            if update is None:
                continue

            if update.get('action') is FirebaseAction.SET:
                count += 1
                doc = self.fs_client.document(update.get('path'))
                batch.set(doc, update.get('data'), merge=True)
                self.session.commit()
            elif update.get('action') is FirebaseAction.DELETE_COLLECTION:
                collection_path = update.get('path')
                count = delete_collection_batch(collection_path=collection_path,
                                                batch=batch,
                                                starting_batch_count=count)
            if count >= 490:
                _commit_batch(batch=batch, session=self.session)
                count = 0

        if not tl.refresh_lock(self.request.id):
            logger.error("Failed to refresh lock")
            _commit_batch(batch=batch, session=self.session)
            return

    _commit_batch(batch=batch, session=self.session)


@managed_session
def trigger_iterable_bulk_user_import(chunk_size=100, session=None):
    try:
        chunk_size = int(chunk_size)
    except TypeError:
        chunk_size = 100
    email_list = []
    for state in session.query(UserState)\
            .filter(UserState.requires_iterable_sync.is_(True))\
            .limit(chunk_size)\
            .all():
        state.requires_iterable_sync = False
        session.add(state)
        email_list.append(state.user.email)
    logger.info("Writing emails %s", email_list)
    IterableSyncQueue.write(email_list)
    bulk_update_users.apply_async(kwargs={'chunk_size': chunk_size})


@managed_session
def update_user_followers(user_uuid=None, session=None):
    if not user_uuid:
        following = session.query(UserFollow.user_uuid) \
            .join(User, User.user_uuid == UserFollow.user_uuid) \
            .filter(UserFollow.deleted_at.is_(None)) \
            .group_by(UserFollow.user_uuid).all()

        followers = session.query(UserFollow.follower_uuid) \
            .join(User, User.user_uuid == UserFollow.follower_uuid) \
            .filter(UserFollow.deleted_at.is_(None)) \
            .group_by(UserFollow.follower_uuid).all()

        users = list(set([str(x[0]) for x in following + followers]))
        update_user_follow_following_collections.map(users).apply_async()

    else:
        logger.info("Updating collection for user %s", user_uuid)
        update_user_follow_following_collections.delay(user_uuid=user_uuid)


@managed_session
def fix_figure1_followers(user_uuid=None, session=None):
    if not user_uuid:
        following_figure1 = session.query(UserFollow.follower_uuid) \
            .join(User, User.user_uuid == UserFollow.user_uuid) \
            .filter(UserFollow.deleted_at.is_(None),
                    User.username == 'figure1') \
            .all()
        followed_by_figure1 = session.query(UserFollow.user_uuid) \
            .join(User, User.user_uuid == UserFollow.follower_uuid) \
            .filter(UserFollow.deleted_at.is_(None),
                    User.username == 'figure1') \
            .all()
        uuids = [str(x[0]) for x in following_figure1 if x not in followed_by_figure1]

        logging.info("Running fix_figure1_followers_task for " + str(len(uuids)) + " users")
        fix_figure1_followers_task.map(uuids).apply_async()

    else:
        fix_figure1_followers_task.delay(user_uuid=user_uuid)


def run_user_aggregate(max_users=100_000, skip_backfill=False):
    """
    If skip_backfill is true, then we just run the task.
    """
    task_group = group(generate_user_recommendations_task.si(),
                       generate_user_recommendations_task.si())

    if skip_backfill:
        task_group.apply_async()
    else:
        task = run_user_aggregate_task.si(max_users=max_users)
        task.link(task_group)
        task.apply_async()


@celery_app.task(bind=True, base=TaskBase, name='figure1.backend.tools.generate_aggregate_backfill')
def run_user_aggregate_task(self, max_users=100_000):
    user_count = _get_users_active_12_months(session=self.session, max_users=max_users)
    while True:
        uc = _get_users_active_12_months(session=self.session, start=user_count, max_users=max_users)
        if uc == 0:
            break
        user_count += uc


def _get_users_active_12_months(session, max_users=100_000, start=0):
    last_update_dt = datetime.now(tz=timezone.utc) - timedelta(days=365)
    q = session.query(User.user_uuid).filter(User.updated_at > last_update_dt)
    q = q.limit(max_users).offset(start)
    logger.info("Returning %s", q.count())
    for u in q.yield_per(1000).all():
        Recommended.regenerate_user(str(u[0]))
    return q.count()
