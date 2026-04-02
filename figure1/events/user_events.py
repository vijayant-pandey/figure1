import logging
import string
from datetime import datetime
from datetime import timezone

from typing import Optional

from celery import chain
from celery import group
from celery import chord
from celery.canvas import Signature

from dogpile.cache.api import NO_VALUE

from firebase_admin import auth as fb_auth
from firebase_admin.exceptions import FirebaseError
from google.api_core.exceptions import Aborted

from pydantic import ValidationError

from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy import desc
from sqlalchemy import or_

from figure1.admin.campaign.case import sync_targeted_promo_cards_task
from figure1.admin.migrate.users import migrate_legacy_user
from figure1.cache_config import cache_region
from figure1.common.comms import initialize_user_communication_preferences_task
from figure1.common.comms import sync_user_communication_preferences_v2
from figure1.common.comms import sync_user_communication_preferences
from figure1.common.firebase import do_firebase_sync
from figure1.common.firebase import change_firebase_email
from figure1.common.helpers.user import OnboardingWorkflow
from figure1.common.helpers import UserManagement
from figure1.common.helpers import CaseDetail
from figure1.common.helpers import FeedCard
from figure1.common.helpers import UserDocument
from figure1.common.helpers import get_verification_record_by_uuid
from figure1.common.iterable import IterableAPI
from figure1.common.iterable import update_iterable_user
from figure1.common.iterable import update_iterable_user_comm_preferences
from figure1.common.iterable import delete_iterable_user_task
from figure1.common.iterable import import_anonymous_email_subscriber_preferences_task

from figure1.common.mixpanel import update_mixpanel_user
from figure1.common.mixpanel import update_mixpanel_user_legacy_data
from figure1.common.mixpanel import send_mixpanel_event

from figure1.common.models.db import CaseAuthor
from figure1.common.models.db import Comment
from figure1.common.models.db import Content
from figure1.common.models.db import User
from figure1.common.models.db import UserState
from figure1.common.models.db import UserSavedCase
from figure1.common.models.db import UserFollow
from figure1.common.models.db import AnonymousEmailSubscriber
from figure1.common.helpers.verification import get_user_verification_record
from figure1.common.models.firebase import FirestoreUserState

from figure1.common.slack_client import SlackClient
from figure1.common.slack_client import SlackColour
from figure1.common.slack_client import SlackIcon
from figure1.notifications import log_registration_activity_task
from figure1.notifications import log_user_status_changed_and_notify_user_task
from figure1.notifications import notify_profession_changed_approved_task
from figure1.notifications import send_marketing_sign_up_event_task

from figure1.common.types import FirebaseAction
from figure1.common.types import UpdateUserModel
from figure1.common.types import VerificationType
from figure1.common.types import VerificationStatus
from figure1.common.types import RegistrationSections
from figure1.common.types import MixpanelEvent
from figure1.common.types import UserTypes
from figure1.common.types import OnboardingState

from figure1.configuration import app_settings

from figure1.core import firebase_app
from figure1.core import FirebaseTaskBase
from figure1.core import celery_app
from figure1.core import managed_session
from figure1.core import TaskBase

from figure1.exceptions import UserNotFound
from figure1.common.activities.user_profile_activities import update_all_activities_task
from figure1.feeds import write_feed_metadata_task

from figure1.store import UserSponsoredContentStore

logger = logging.getLogger('figure1.userevents')


def _get_user_cases(user_uuid, session):
    for c in session.query(CaseAuthor).filter(CaseAuthor.author_uuid == user_uuid).all():
        yield c


def _get_user_comments(user_uuid, session):
    for c in session.query(Content).filter(Comment.author_uuid == user_uuid) \
            .join(Comment, Content.content_uuid == Comment.content_uuid) \
            .all():
        yield c


def _sync_user_profile(user_uuid) -> Signature:
    return group(do_firebase_sync.si(firebasemodel='FirebaseUsersDB', uuid=user_uuid),
                 do_firebase_sync.si(firebasemodel='FirebaseUsersProfileDB', uuid=user_uuid))


def sync_user_profile(user_uuid) -> Signature:
    return _sync_user_profile(user_uuid=user_uuid)


def update_user_authored_items(user_uuid, session):
    # Wiping the cache forces a regeneration on next access.
    sp = UserSponsoredContentStore(user_uuid=user_uuid)
    sp.wipe_cache_key(key=sp.sponsored_content_target_key)
    sp.wipe_cache_key(key=sp.compact_user_data_key)

    comment_task_group = []
    case_task_group = []
    for comment in _get_user_comments(user_uuid=user_uuid, session=session):
        comment_task_group.append(do_firebase_sync.si(firebasemodel='CommentV2', uuid=str(comment.case_uuid)))
    for case in _get_user_cases(user_uuid=user_uuid, session=session):
        case_task_group.append(do_firebase_sync.si(firebasemodel='CaseDetailV2', uuid=str(case.case_uuid)))
    task = chord((*comment_task_group, *case_task_group), update_all_activities_task.si(user_uuid=str(user_uuid)))
    task.apply_async(queue='backend')


@managed_session
def handle_user_delete(user_uuid, session):
    """
    To delete a user
    - Mark the user as deleted in the user table and ensure this is flushed
    - Find all authored cases, as well as all cases with comments and force those to resync
    - Run user sync, then user profile sync task
    :param user_uuid:
    :param session:
    :return:
    """

    mgmt = UserManagement(user_uuid=user_uuid, session=session, include_deleted=True)
    mgmt.delete_user()

    update_user_authored_items(user_uuid=user_uuid, session=session)

    task = do_firebase_sync.si(firebasemodel='FirebaseUsersDB',
                               uuid=user_uuid,
                               action=FirebaseAction.DELETE)

    task.link(update_user_follow_follower_profiles.si(user_uuid=str(user_uuid), delete=True))
    task.link(do_firebase_sync.si(firebasemodel='FirebaseUsersProfileDB',
                                  uuid=user_uuid,
                                  action=FirebaseAction.DELETE))
    task.link(delete_iterable_user_task.si(email=mgmt.user.email))
    return task


def _update_user(user: User,
                 sync_firebase: bool,
                 session: Session):
    session.refresh(user)

    task = None
    if sync_firebase:
        task = do_firebase_sync.si(firebasemodel='FirebaseUsersDB', uuid=user.user_uuid)
        task.link(do_firebase_sync.si(firebasemodel='FirebaseUsersProfileDB', uuid=user.user_uuid))

    external_update = group(update_iterable_user_comm_preferences.si(user_uid=user.user_uid),
                            update_mixpanel_user.si(user_uuid=user.user_uuid))
    if task:
        task.link(external_update)
    else:
        task = external_update

    task.apply_async()


def handle_update_internal_state(user_uuid: str, session, **kwargs):
    """
    :param user_uuid:
    :param session:
    :param kwargs: These options are passed to the user_state model for updating,
    valid keys are the keys in UserState()
    :return:
    """
    user_state = UserState()
    user_state.user_uuid = user_uuid
    for k in kwargs.keys():
        if hasattr(user_state, k):
            setattr(user_state, k, kwargs.get(k))
    state = session.merge(user_state)
    u = session.query(User).filter(User.user_uuid == user_uuid).one()
    us = FirestoreUserState.from_orm(state)
    us.user_uid = u.user_uid
    us.firestore_write()


def handle_update_external_state(user_uuid: str, phone_number=None, return_task=False):
    if phone_number:
        task = group(update_iterable_user.si(user_uuid=user_uuid, phone_number=phone_number),
                     update_mixpanel_user.si(user_uuid=user_uuid),
                     update_iterable_user_comm_preferences.si(user_uuid=user_uuid))
    else:
        task = group(update_iterable_user.si(user_uuid=user_uuid),
                     update_mixpanel_user.si(user_uuid=user_uuid),
                     update_iterable_user_comm_preferences.si(user_uuid=user_uuid))
    if return_task:
        return task

    task.apply_async()


def handle_user_updated(user_uuid: str,
                        session: Session,
                        avatar_updated: bool = False,
                        force_author_update: bool = False,
                        user_update_model: UpdateUserModel = None,
                        return_task: bool = False) -> Signature:
    """
    Handles updates to a user
    :param user_uuid:  The uuid of user that was updated
    :param session:  The active session
    :param avatar_updated: If True, the avatar has been changed and all user-authored content must be updated
    :param user_update_model: This is an instance of UserUpdateModel which contains data that has been updated
    :return:  None
    """

    user = User.get_user_by_uuid(user_uuid=user_uuid, session=session, raise_exception=True)
    handle_update_internal_state(user_uuid=user_uuid, session=session, last_seen=datetime.now(tz=timezone.utc))
    OnboardingWorkflow.update_onboarding_state(user_uuid=user_uuid, session=session)
    task = _sync_user_profile(user_uuid=user_uuid)
    if user_update_model and isinstance(user_update_model, UpdateUserModel):
        if user_update_model.primarySpecialty:
            if user.onboarding_completed is True:
                force_author_update = True
        if user_update_model.screen_id:
            task.link(log_registration_activity_task.si(user_uid=user.user_uid, screen_id=user_update_model.screen_id))
        if user_update_model.onboardingCompleted:
            task.link(initialize_user_communication_preferences_task.si(user_uuid=user_uuid))
    if force_author_update or avatar_updated:
        update_user_authored_items(user_uuid=user_uuid, session=session)
        task.link(update_user_follow_follower_profiles.si(user_uuid=str(user_uuid)))
    handle_user_comm_prefs_updated(user_uuid=user_uuid, session=session)
    if return_task:
        return task
    else:
        task.apply_async(countdown=10)


def handle_user_topic_sub(user_uuid):
    """
    Handles a user subscribing from a given topic
    :param user_uuid:
    :return:
    """
    handle_update_external_state(user_uuid=user_uuid)


def handle_user_topic_unsub(user_uuid):
    """
    Handles a user unsubscribing from a given topic
    :param user_uuid:
    :return:
    """
    handle_update_external_state(user_uuid=user_uuid)


def handle_user_comm_prefs_updated(user_uuid, session, phone_number=None):
    """
    Handles updates to a user's communication preferences
    :param user_uuid:  The uid of user that was updated
    :param session:  The active session
    :param phone_number:  The phone number provided for communications.
    :return:  None
    """
    session.flush()
    user_uuid = str(user_uuid)
    sync_user_communication_preferences(user_uuid=user_uuid, session=session)
    sync_user_communication_preferences_v2(user_uuid=user_uuid, session=session)
    handle_update_external_state(user_uuid=user_uuid, phone_number=phone_number)


def handle_user_email_updated(user_uid, old_email, new_email):
    try:
        logger.info("Updating email for user %s in iterable", old_email)
        IterableAPI().update_email(old_email=old_email, new_email=new_email)
    except Exception as e:
        logger.error("Failed to update email of iterable user: %s", e)
        raise

    try:
        logger.info("Updating email for user %s in firebase", user_uid)
        fb_app = firebase_app()
        fb_auth.update_user(uid=user_uid, email=new_email, app=fb_app)
    except FirebaseError as fe:
        logger.error("Failed to update user %s firebase auth to %s.  Queuing task for retry: %s",
                     user_uid, new_email, fe)
        change_firebase_email.apply_async(countdown=30, kwargs={'user_uid': user_uid, 'email': new_email})
    except ValueError as ve:
        logger.error("Failed to update user %s firebase auth to %s: %s", user_uid, new_email, ve)
        raise


def handle_onboarding_started(user_uuid: str, session: Session):
    user = User.get_user_by_uuid(user_uuid=user_uuid, session=session, raise_exception=True)

    tasks = [
        log_registration_activity_task.si(user_uid=user.user_uid,
                                          screen_id=RegistrationSections.REGISTRATION_STARTED.value),
        send_mixpanel_event.si(user_uuid=user.user_uuid,
                               event_name=MixpanelEvent.ONBOARDING_STARTED.value,
                               properties={})
    ]

    anon = session.query(AnonymousEmailSubscriber).get(user.email)
    if anon:
        tasks.append(import_anonymous_email_subscriber_preferences_task.si(user_uuid=user.user_uuid,
                                                                           email=user.email))

    group(*tasks).apply_async()


def handle_onboarding_completed(user_uuid: str, session: Session, return_task: bool = False):
    user = User.get_user_by_uuid(user_uuid=user_uuid, session=session)
    trigger_user_saved_case_sync(user_uuid=user_uuid, session=session)
    uv = user.user_verification
    if not uv:
        pass
    elif uv.verification_type == VerificationType.LEGACY and uv.verification_status == VerificationStatus.VERIFIED:
        pass
    else:
        SlackClient().send_message(message="A new verification request has been created",
                                   colour=SlackColour.GREEN,
                                   icon=SlackIcon.HEALTH_WORKER,
                                   channel=app_settings.slack_channel_verification_notifications,
                                   entity=user)

    task = group(log_registration_activity_task.si(user_uid=user.user_uid,
                                                   screen_id=RegistrationSections.REGISTRATION_COMPLETED.value),
                 send_mixpanel_event.si(user_uuid=user.user_uuid,
                                        event_name=MixpanelEvent.ONBOARDING_COMPLETED.value,
                                        properties={}),
                 follow_figure1_official.si(user_uid=user.user_uid),
                 update_user_follow_following_collections.si(user_uuid=str(user_uuid)),
                 sync_targeted_promo_cards_task.si(user_uuid=str(user_uuid)))

    if return_task:
        return task
    else:
        task.apply_async()


@managed_session
def handle_profession_change_approved(verification_uuid, session=None):
    verification = get_verification_record_by_uuid(verification_uuid=verification_uuid, session=session)
    if not verification:
        raise ValueError("No verification record found")
    if not verification.profession_change_request:
        raise ValueError("No change request linked to this verification record ")
    user_uuid = str(verification.user_uuid)
    profession_target = verification.profession_change_request.requested_profession
    user_mgmt = UserManagement(session=session, user_uuid=user_uuid)
    user_mgmt.set_primary_specialty(specialty=profession_target, check_verify=False)
    session.flush()

    task = group(sync_targeted_promo_cards_task.si(user_uuid=str(user_uuid)),
                 chain(profession_change_approve_task.si(user_uuid=user_uuid),
                       notify_profession_changed_approved_task.si(user_uuid=user_uuid)))
    task.apply_async()


@managed_session
def handle_user_verification_state_change(user_uuid: str = None,
                                          verification_uuid=None,
                                          state=None,
                                          moderator_uid=None,
                                          previous_state=None,
                                          session=None):
    verification = get_verification_record_by_uuid(verification_uuid=verification_uuid, session=session)
    if verification is None:
        return
    user_uuid = str(verification.user_uuid)
    key = user_uuid + '.' + "verification_state_change"
    value = cache_region.get(key=key)
    task = None
    if value is NO_VALUE:
        if state and isinstance(state, VerificationStatus):
            cache_region.set(key=key, value=state.value)
            if state == VerificationStatus.VERIFIED:
                logger.info("User state set to verified, regenerating feeds")
                task = sync_targeted_promo_cards_task.si(user_uuid=str(user_uuid))
        else:
            cache_region.set(key=key, value='state_unknown')
        if task is not None:
            task.link(log_user_status_changed_and_notify_user_task.si(user_uuid=user_uuid, moderator_uid=moderator_uid))
        else:
            task = log_user_status_changed_and_notify_user_task.si(user_uuid=user_uuid, moderator_uid=moderator_uid)

    if task is not None:
        task.link(handle_update_external_state(user_uuid=str(user_uuid), return_task=True))
        task.apply_async(countdown=5)
    else:
        handle_update_external_state(user_uuid=str(user_uuid), return_task=True).apply_async(countdown=5)


def handle_user_uid_set(user_uuid: str,
                        user_uid: str,
                        session: Session,
                        wait: bool = False):
    """
    Handles updates to a user's uid
    :param user_uuid:  The uuid of user that was updated
    :param user_uid:  The new uid of the user
    :param session:  The active session
    :param wait:  If false, the user migration and firebase sync will happen asynchronously.  If true, the function will
    not return until everything has been completed.
    :return:  None
    """
    task = chain(migrate_legacy_user.si(user_uuid=user_uuid, force=True),
                 do_firebase_sync.si(firebasemodel='FirebaseUsersDB', uuid=user_uuid),
                 do_firebase_sync.si(firebasemodel='FirebaseUsersProfileDB', uuid=user_uuid))
    res = task.apply_async()

    trigger_user_saved_case_sync(user_uuid=user_uuid, session=session)
    update_tasks = group(update_all_activities_task.si(user_uuid=str(user_uuid)),
                         update_mixpanel_user_legacy_data.si(user_uuid=user_uuid),
                         update_user_follow_follower_profiles.si(user_uuid=str(user_uuid)),
                         update_user_follow_following_collections.si(user_uuid=str(user_uuid)),
                         log_registration_activity_task.si(user_uid=user_uid,
                                                           screen_id=RegistrationSections.REGISTRATION_STARTED.value),
                         send_mixpanel_event.si(user_uuid=user_uuid,
                                                event_name=MixpanelEvent.ONBOARDING_STARTED.value,
                                                properties={}))
    update_tasks.apply_async()
    if wait:
        res.get(timeout=120)


def handle_approve_profession_change_request(user_uuid, session=None):
    verification = get_user_verification_record(user_uuid=user_uuid, session=session)
    if not verification:
        return
    prof = verification.profession_change_request.requested_profession
    u = UserManagement(user_uuid=user_uuid, session=session)
    u.set_primary_specialty(specialty=prof, check_verify=False)
    session.flush()
    update_user_authored_items(session=session, user_uuid=user_uuid)


@celery_app.task(bind=True, base=TaskBase, name='figure1.backend.profession_change_update')
def profession_change_approve_task(self, user_uuid):
    handle_approve_profession_change_request(user_uuid=user_uuid, session=self.session)


def trigger_user_saved_case_sync(user_uuid=None, session=None):
    if user_uuid:
        us = session.query(UserState).filter(UserState.user_uuid == user_uuid).one_or_none()
        if not us:
            return None
        if us.user.deleted_at is not None:
            return None
        if us.user.user_uid:
            logger.info("Starting sync task")
            v = cache_region.get(key=str(user_uuid) + '_saved_case_sync')
            if v == NO_VALUE:
                task = sync_user_saved_cases_task.delay(user_uid=us.user.user_uid, user_uuid=user_uuid)
                cache_region.set(key=str(user_uuid) + '_saved_case_sync', value=task.id)
            else:
                logger.info("Task is locked by task id %s", v)

    else:
        task = None
        count = 0

        q = session.query(func.count(UserSavedCase.user_uuid).label('user_count'),
                          UserSavedCase.user_uuid).join(User, UserSavedCase.user_uuid == User.user_uuid) \
            .group_by(UserSavedCase.user_uuid) \
            .order_by(desc('user_count')) \
            .filter(UserSavedCase.deleted_at.is_(None), User.deleted_at.is_(None), User.user_uid.isnot(None))
        logger.debug("Using query %s", q.statement)
        for i in q.all():
            u = User.get_user_by_uuid(user_uuid=i[1], session=session)
            if u.deleted_at is not None:
                continue
            if not u.user_uid:
                continue
            logger.info("Sync user %s with %s cases", i[1], i[0])
            if not task:
                logger.info("Creating task with userUid %s and user_uuid %s", u.user_uid, str(u.user_uuid))
                task = sync_user_saved_cases_task.si(user_uid=u.user_uid, user_uuid=str(u.user_uuid))
            else:
                logger.info("Creating task with userUid %s and user_uuid %s", u.user_uid, str(u.user_uuid))
                task.link(sync_user_saved_cases_task.si(user_uid=u.user_uid, user_uuid=str(u.user_uuid)))
            count += 1
            logger.info("Task (%s) Created", count)
            if not count % 20:
                task.apply_async()
                task = None
        if task:
            task.apply_async()


@celery_app.task(bind=True, base=FirebaseTaskBase, name='figure1.backend.sync_user_saved_cases')
def sync_user_saved_cases_task(self, user_uid, user_uuid):
    fs = self.fs_client
    batch = self.batch
    count = 0
    saved_case_count = 0
    deleted_case_count = 0
    for saved_case in self.session.query(UserSavedCase).filter(UserSavedCase.user_uuid == user_uuid).all():
        if saved_case.deleted_at is not None:
            deleted_case_count += 1
            continue
        case_uuid = str(saved_case.case_uuid)
        case_detail = CaseDetail.elasticsearch_case_detail(case_uuid=case_uuid, session=self.session)
        case_data = FeedCard.feed_card(feed_item={'_source': case_detail})
        saved_case_count += 1
        if case_data:
            logger.debug("Syncing case uuid %s", case_uuid)
            p = fs.collection('userSavedCasesDB').document(user_uid).collection('all').document(case_uuid)
            batch.set(p, case_data)
            count += 1
            if not count % 500:
                batch.commit()
    logger.debug("Synced %s cases", count)
    batch.commit()
    cache_region.delete(key=str(user_uuid) + '_saved_case_sync')
    return f"{saved_case_count} saved cases, {count} synced, {deleted_case_count} deleted for user {user_uuid}"


@celery_app.task(bind=True, base=FirebaseTaskBase, name='figure1.backend.update_follow_profiles')
def update_user_follow_follower_profiles(self, user_uuid, delete=False):
    """
    This task handles updating follower/following profiles when there is a change.
    :param self:
    :param user_uuid:
    :param delete: This parameter indicates that this users profile should be deleted instead of updated
    :return:
    """
    user_uuid = str(user_uuid)
    updated_profile = UserDocument.get_compact_user_data(user_uuid=user_uuid, session=self.session)
    try:
        user_info = User.get_user_by_uuid(user_uuid=user_uuid, session=self.session, raise_exception=True)
    except UserNotFound:
        return
    except ValidationError:
        return

    fs = self.fs_client
    batch = self.batch
    count = 0
    if user_info.user_type != UserTypes.FIGURE1_OFFICIAL:

        for follower in self.session.query(UserFollow.follower_uuid, User.user_uuid) \
                .join(User, User.user_uuid == UserFollow.follower_uuid) \
                .filter(UserFollow.user_uuid == user_uuid, UserFollow.deleted_at.is_(None)).all():

            follower_uuid = follower[1]
            p = fs.collection('usersProfileDB') \
                .document(str(follower_uuid)) \
                .collection('followers') \
                .document(user_uuid)
            if delete:
                batch.delete(p)
            else:
                batch.set(p, updated_profile)
            count += 1
            if not count % 500:
                logger.info("Committing 500...")
                batch.commit()

        logger.info("Updated %s followers", count)
        for following in self.session.query(UserFollow.user_uuid, User.user_uuid) \
                .join(User, User.user_uuid == UserFollow.user_uuid) \
                .filter(UserFollow.follower_uuid == user_uuid, UserFollow.deleted_at.is_(None)).all():
            following_uuid = following[1]
            p = fs.collection('usersProfileDB') \
                .document(str(following_uuid)) \
                .collection('following').document(user_uuid)
            if delete:
                batch.delete(p)
            else:
                batch.set(p, updated_profile)
            count += 1
            if not count % 500:
                logger.info("Committing 500...")
                batch.commit()
        batch.commit()

        if delete:
            self.session.query(UserFollow) \
                .filter(or_(UserFollow.user_uuid == user_uuid, UserFollow.follower_uuid == user_uuid)) \
                .delete()
            self.session.flush()
        logger.info("Total updated %s", count)


@celery_app.task(bind=True,
                 base=FirebaseTaskBase,
                 name='figure1.backend.follow_official_accounts')
def follow_figure1_official(self, user_uid):
    """
    This auto follows figure1 official accounts.

    :param self:
    :param user_uid:
    :return:
    """
    try:
        requester_user = User.get_user_by_uid(user_uid=user_uid, session=self.session, raise_exception=True)
    except UserNotFound:
        return
    fs = self.fs_client
    batch = self.batch
    count = 0
    for f1_user in self.session.query(User).filter(User.user_type == UserTypes.FIGURE1_OFFICIAL,
                                                   User.deleted_at.is_(None)).all():
        UserFollow.follow_user(session=self.session,
                               user_uuid=f1_user.user_uuid,
                               follower_user_uuid=requester_user.user_uuid)

        target_profile = UserDocument.get_compact_user_data(user_uuid=f1_user.user_uuid,
                                                            session=self.session)
        follows = fs.collection('usersProfileDB') \
            .document(str(requester_user.user_uuid)) \
            .collection('following') \
            .document(str(f1_user.user_uuid))
        batch.set(follows, target_profile)
        count += 1
        if not count % 500:
            batch.commit()
    batch.commit()


@celery_app.task(bind=True,
                 base=FirebaseTaskBase,
                 autoretry_for=(Aborted,),
                 name='figure1.backend.update_follow_following_collections')
def update_user_follow_following_collections(self, user_uuid: string):
    """
    This updates all following and follower entries in the given users collection.

    :param self:
    :param user_uuid:
    :return:
    """
    fs = self.fs_client
    batch = self.batch
    count = 0
    try:
        public_profile = UserDocument.get_public_profile(user_uuid=user_uuid, session=self.session)
    except UserNotFound:
        logger.exception("User not found")
        return
    except ValidationError:
        logging.exception("User validation failed")
        return
    if public_profile.get('userType') != 'Figure1Official':
        # Users following this user
        following_query = self.session.query(UserFollow) \
            .filter(UserFollow.user_uuid == user_uuid, UserFollow.deleted_at.is_(None))
        following_count = following_query.count()
        public_profile.update({'followerCount': following_count})
        for following in following_query.all():
            try:
                follower_profile = UserDocument.get_compact_user_data(user_uuid=following.follower_uuid,
                                                                      session=self.session)
            except (ValidationError, UserNotFound):
                continue

            p = fs.collection('usersProfileDB').document(user_uuid) \
                .collection('followers').document(str(following.follower_uuid))
            batch.set(p, follower_profile)
            count += 1
            if not count % 500:
                logger.info("Committing 500...")
                batch.commit()

        # Users this user is following
        follower_query = self.session.query(UserFollow) \
            .filter(UserFollow.follower_uuid == user_uuid, UserFollow.deleted_at.is_(None))
        follower_count = follower_query.count()
        public_profile.update({'followingCount': follower_count})
        for follow in follower_query.all():
            try:
                following_profile = UserDocument.get_compact_user_data(user_uuid=follow.user_uuid, session=self.session)
            except (ValidationError, UserNotFound):
                continue
            p = fs.collection('usersProfileDB').document(user_uuid) \
                .collection('following').document(str(follow.user_uuid))
            batch.set(p, following_profile)
            count += 1
            if not count % 500:
                logger.info("Committing 500...")
                batch.commit()
        logger.debug("Following count %s, follower count %s", follower_count, following_count)
        pf = fs.collection('usersProfileDB').document(user_uuid)
        batch.set(pf, public_profile)
        batch.commit()


@celery_app.task(bind=True,
                 base=FirebaseTaskBase,
                 autoretry_for=(Aborted,),
                 name='figure1.backend.fix_figure1_followers_task')
def fix_figure1_followers_task(self, user_uuid: string):
    """
    Fixes invalid followers state of the figure 1 account.  Finds all firestore profiles where `figure1` is listed
    as a follower, and move the doc to the following subcollection instead.

    Returns true if a match is made, otherwise False.
    :param self:
    :param user_uuid:
    :return:
    """
    fs = self.fs_client
    batch = self.batch

    official_uuid = self.session.query(User.user_uuid).filter(User.username == 'figure1').scalar()
    official_uuid = str(official_uuid)

    path = fs.collection('usersProfileDB').document(user_uuid) \
        .collection('followers').document(official_uuid)
    doc = path.get()
    if doc.exists:
        new_doc = fs.collection('usersProfileDB').document(user_uuid) \
            .collection('following').document(official_uuid)
        batch.set(new_doc, doc.to_dict())
        batch.delete(path)
        batch.commit()
        return True

    return False


@celery_app.task(bind=True,
                 base=TaskBase,
                 name='figure1.frontend.onboarding_state_change_events')
def on_onboarding_state_change(self: TaskBase,
                               user_uuid: str,
                               from_state: Optional[OnboardingState],
                               to_state: OnboardingState):
    task = None

    if from_state in (OnboardingState.INFORMATION, OnboardingState.USA_INFORMATION):
        task = initialize_user_communication_preferences_task.si(user_uuid=user_uuid)

    if to_state is OnboardingState.COMPLETED:
        if task:
            task.link(handle_onboarding_completed(user_uuid=user_uuid, session=self.session, return_task=True))
        else:
            task = handle_onboarding_completed(user_uuid=user_uuid, session=self.session, return_task=True)

    if to_state is OnboardingState.CONFIRMATION:
        user = User.get_user_by_uuid(user_uuid=user_uuid, session=self.session, raise_exception=True)
        if user.user_verification.npi.npi_number:
            if task:
                task.link(send_marketing_sign_up_event_task.si(user_uuid=user_uuid))
            else:
                task = send_marketing_sign_up_event_task.si(user_uuid=user_uuid)

    if isinstance(task, Signature):
        task.apply_async(countdown=10)
