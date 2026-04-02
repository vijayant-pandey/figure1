import logging
import signal

import uuid

from datetime import datetime

from pydantic import ValidationError
from sqlalchemy import or_
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import MultipleResultsFound
from typing import Dict, Any, List

from figure1.admin.migrate.users.prequel_model import UsersPrequelModel, LegacyGroup
from figure1.admin.reference_data.model_methods import get_country_from_alpha_3, get_legacy_specialty
from figure1.common.elasticsearch import add_or_update_user
from figure1.core import TaskBase, celery_app
from figure1.common.helpers import UserManagement, UserDocument, OnboardingWorkflow
from figure1.common.models.db import LegacyUser, LegacySpecialty, TaskLock, LegacyUserQueue, \
    SpecialtyTreeV2, UserVerification, UserNPI, LegacyCase, UserSavedCase, Case, \
    CommunicationSettings, UserCommunicationPreferences, UserFollow, User, Topic, UserFeedSubscription, \
    CommunicationGroup, UserState
from figure1.common.types import VerificationType, VerificationStatus, UpdateUserModel, UserTypes, \
    CommunicationMethods, UserNPIVerificationDocument
from figure1.configuration import app_settings
from figure1.exceptions import TaskLockedException, TaskUnlockException

logger = logging.getLogger("figure1.migrate.users.tasks")


def _migrate_legacy_user(q: LegacyUserQueue,
                         prequel_model: UsersPrequelModel,
                         session: Session,
                         force: bool):
    user_dict = prequel_model.get_user(user_id=q.legacy_user_id)
    if not user_dict:
        logger.error(f"No user found or validation failed {str(q.legacy_user_id)}")
        q.propagated_at = datetime.utcnow()
        session.add(q)
        return

    legacy_user = _upsert_legacy_user(user_dict=user_dict, session=session)
    pro_user = _upsert_pro_user(user_dict=user_dict,
                                legacy_user=legacy_user,
                                prequel_model=prequel_model,
                                session=session,
                                force=force)
    if pro_user:
        q.user_uuid = pro_user.user_uuid
        q.propagated_at = datetime.utcnow()


def _get_user_management(legacy_user, session) -> UserManagement:
    """
    Finds a u_user corresponding to a given u_legacy_user and returns the management object
    If a user cannot be found (does not exist yet), the user is created
    """
    mgmt = UserManagement(user_uuid=legacy_user.user_uuid,
                          session=session,
                          is_admin_created=True,
                          include_deleted=True)
    if mgmt.user:
        return mgmt

    mgmt.add_legacy_user(email=legacy_user.decrypted_email,
                         user_uuid=legacy_user.user_uuid,
                         created_at=legacy_user.created_at)
    return mgmt


def _upsert_legacy_user(user_dict, session):
    lu = session.query(LegacyUser) \
        .filter(LegacyUser.legacy_id == user_dict.get('_id')) \
        .one_or_none()
    if not lu:
        lu = LegacyUser()
        lu.user_uuid = uuid.uuid4()
        lu.legacy_id = user_dict.get('_id')
    lu.username = user_dict.get('username')
    lu.email = user_dict.get('email')
    lu.verified = user_dict.get('verified')
    lu.targetable_country_uuid = _get_targetable_country(user=user_dict, session=session)
    lu.specialty_uuid = _get_specialty_uuid(user_dict=user_dict, session=session)
    lu.created_at = user_dict.get('created', None)
    lu.deleted_at = user_dict.get('modifiedAt') or lu.created_at if user_dict.get('isDeletedAccount') else None
    if user_dict.get('modifiedAt'):
        lu.updated_at = user_dict.get('modifiedAt')

    session.add(lu)
    session.flush()
    return lu


def _upsert_pro_user(user_dict: Dict[str, Any],
                     legacy_user: LegacyUser,
                     prequel_model: UsersPrequelModel,
                     session: Session,
                     force: bool):
    if not legacy_user.decrypted_email:
        logger.error(f"Missing email for legacy user {legacy_user.legacy_id}")
        return None

    legacy_user_id = user_dict.get('_id')

    mgmt = _get_user_management(legacy_user=legacy_user, session=session)

    # If user has already migrated to pro or is marked as blocked, do not update with legacy data
    if mgmt.user.user_uid and not force:
        return mgmt.user
    elif mgmt.user.user_state and mgmt.user.user_state.block_legacy_migration:
        return mgmt.user

    legacy_verification = prequel_model.get_verification(user_id=legacy_user_id)
    followed_cases = list(prequel_model.get_followed_cases(user_id=legacy_user_id))
    saved_cases = list(prequel_model.get_saved_cases(user_id=legacy_user_id))
    followed_users = list(prequel_model.get_followed_users(user_id=legacy_user_id))
    group_memberships = list(prequel_model.get_group_memberships(user_id=legacy_user_id))
    s = session.query(SpecialtyTreeV2) \
        .filter(LegacySpecialty.specialty_uuid == legacy_user.specialty_uuid) \
        .join(LegacySpecialty, LegacySpecialty.pro_tree_uuid == SpecialtyTreeV2.specialty_uuid) \
        .one_or_none()

    mgmt.user.deleted_at = legacy_user.deleted_at
    mgmt.user.updated_at = legacy_user.updated_at
    mgmt.user.last_seen = user_dict.get('lastAccessed')

    first_name = legacy_verification.get('firstName') if legacy_verification else None
    last_name = legacy_verification.get('lastName') if legacy_verification else None
    if user_dict.get('fullName'):
        display_name = user_dict.get('fullName')
    elif first_name and last_name:
        display_name = f'{first_name} {last_name}'
    else:
        display_name = None

    try:
        update = UpdateUserModel(username=legacy_user.username,
                                 user_bio=user_dict.get('bio'),
                                 practice_hospital=user_dict.get('institution'),
                                 primarySpecialty=str(s.specialty_uuid) if s else None,
                                 first_name=first_name,
                                 last_name=last_name,
                                 display_name=display_name,
                                 country_uuid=_get_targetable_country(user=user_dict, session=session),
                                 avatar=_get_avatar_url(user_dict=user_dict))
        mgmt.update_user_profile(profile_update=update)
    except ValidationError as e:
        logger.error(f"User update failed validation: {e}")
        return None

    try:
        link_update = UpdateUserModel(profile_link=user_dict.get('link'),
                                      profile_link_text=user_dict.get('link'))
        mgmt.update_user_profile(profile_update=link_update)
    except ValidationError as e:
        logger.info(f"User update profile link failed validation: {e}")

    mgmt.update_username(username=update.username)
    mgmt.update_first_name(first_name=update.first_name)
    mgmt.update_last_name(last_name=update.last_name)
    mgmt.update_user_profile(profile_update=update)
    _update_specialties(mgmt=mgmt, tree_uuid=update.primarySpecialty, session=session)

    # User State
    if mgmt.user.user_state:
        us = mgmt.user.user_state
    else:
        us = UserState()
        us.user_uuid = mgmt.user.user_uuid
        session.add(us)
    us.unconfirmed_email = user_dict.get('isEmailVerified') is False
    us.iterable_unsubscribed = user_dict.get('emailPreferences', {}).get('unsubscribedFromAll')
    session.add(us)

    # Verification
    if user_dict.get('verified'):
        v = session.query(UserVerification).filter(UserVerification.user_uuid == mgmt.user.user_uuid).one_or_none()
        if not v:
            v = UserVerification()
            v.user_uuid = mgmt.user.user_uuid
            v.verification_uuid = uuid.uuid4()
        v.verification_type = VerificationType.LEGACY
        v.verification_status = VerificationStatus.VERIFIED
        session.add(v)
        if legacy_verification and legacy_verification.get('npi'):
            _update_npi_number(mgmt=mgmt, legacy_verification=legacy_verification, session=session)

    # User Type
    if user_dict.get('admin'):
        mgmt.set_user_type(user_type=UserTypes.FIGURE1_INTERNAL)
    elif user_dict.get('isInstitutionalAccount'):
        mgmt.set_user_type(user_type=UserTypes.FIGURE1_INSTITUTIONAL)
    else:
        mgmt.set_user_type(user_type=UserTypes.USER)

    # Saved Cases
    for c in set(followed_cases + saved_cases):
        if not isinstance(c, str):
            continue
        lc = session.query(LegacyCase) \
            .filter(LegacyCase.legacy_id == c) \
            .join(Case, Case.case_uuid == LegacyCase.case_uuid) \
            .first()
        if lc:
            UserSavedCase.create(case_uuid=lc.case_uuid, user_uuid=mgmt.user.user_uuid, session=session)

    # Followed Users
    for u in followed_users:
        lu = session.query(LegacyUser) \
            .join(User, User.user_uuid == LegacyUser.user_uuid) \
            .filter(LegacyUser.legacy_id == u,
                    User.user_type != UserTypes.FIGURE1_OFFICIAL) \
            .first()
        if lu:
            UserFollow.follow_user(session=session,
                                   user_uuid=lu.user_uuid,
                                   follower_user_uuid=mgmt.user.user_uuid)

    _update_communication_preferences(user_uuid=mgmt.user.user_uuid,
                                      user_dict=user_dict,
                                      user_state=us,
                                      session=session)
    _update_topic_subscriptions(mgmt=mgmt,
                                group_memberships=group_memberships,
                                session=session)
    _set_iterable_status(user=mgmt.user,
                         user_state=us,
                         session=session)
    OnboardingWorkflow.update_onboarding_state(user_uuid=mgmt.user.user_uuid, session=session)

    return mgmt.user


def _get_targetable_country(user, session):
    uuid = None
    try:
        targetable_country = get_country_from_alpha_3(alpha_3=user.get('targetableCountry'), session=session)
        if not targetable_country:
            logger.warning(
                f"Unable to find matching targetableCountry for user"
                f" {user.get('_id')}.  Looked for '{user.get('targetableCountry')}'")
        else:
            uuid = targetable_country.country_uuid
    except MultipleResultsFound as e:
        logger.error(f"Error getting targetableCountry for user {user.get('_id')}: {e}")

    return uuid


def _get_specialty_uuid(user_dict, session):
    try:
        specialty = get_legacy_specialty(profession_name=user_dict.get('specialtyProfession'),
                                         type_name=user_dict.get("specialtyType"),
                                         session=session)
        if not specialty:
            logger.warning(f"Unable to find matching specialty for user {user_dict.get('_id')}.  Looked for "
                           f"profession='{user_dict.get('specialtyProfession')}', "
                           f"type='{user_dict.get('specialtyType')}'")
            return None
    except MultipleResultsFound as e:
        logger.error(f"Error getting specialty for user {user_dict.get('_id')}: {e}")
        return None

    return specialty.specialty_uuid


def _get_avatar_url(user_dict):
    if not user_dict.get('avatarFilename'):
        return None

    return app_settings.figure1_imgix_url + 'users/avatar/legacy/' + user_dict.get('avatarFilename')


def _update_specialties(mgmt: UserManagement,
                        tree_uuid: str,
                        session: Session):
    if not tree_uuid:
        return

    tree = session.query(SpecialtyTreeV2).get((tree_uuid, 'tree'))
    if not tree:
        logger.error(f"tree_uuid not found: {tree_uuid}")
        return
    mgmt.set_primary_specialty(specialty=tree_uuid, check_verify=False)


def _update_npi_number(mgmt: UserManagement,
                       legacy_verification: Dict[str, Any],
                       session: Session):
    try:
        doc = UserNPIVerificationDocument.parse_obj(legacy_verification)
    except ValidationError as e:
        logger.info(f"Invalid npi number for user {mgmt.user.user_uuid}: {e}")
        return

    npi = session.query(UserNPI).filter(UserNPI.user_uuid == mgmt.user.user_uuid).one_or_none()
    if not npi:
        npi = UserNPI()
        npi.npi_uuid = uuid.uuid4()
        npi.user_uuid = mgmt.user.user_uuid
    npi.npi_number = doc.npiNumber
    session.add(npi)


def _update_communication_preferences(user_uuid: str,
                                      user_dict: Dict[str, Any],
                                      user_state: UserState,
                                      session: Session):
    unsubscribed_ids = user_dict.get('emailPreferences', {}).get('unsubscribedPreferenceIDs', [])
    differential_uuid = CommunicationGroup.get_differential_uuid(session=session)

    UserCommunicationPreferences.initialize_user_communication_preferences(user_uuid=user_uuid,
                                                                           session=session)
    prefs = []
    for s in session.query(CommunicationSettings) \
            .filter(CommunicationSettings.communication_method != CommunicationMethods.SMS) \
            .all():
        # If unsubscribed from all in legacy, user should be unsubscribed from all differential communications
        if user_state.iterable_unsubscribed and s.communication_group_uuid == differential_uuid:
            value = False
        else:
            value = s.legacy_id not in unsubscribed_ids

        if value != s.communication_default_setting:
            p = session.query(UserCommunicationPreferences).get((user_uuid, s.communication_uuid))
            if not p:
                p = UserCommunicationPreferences()
                p.user_uuid = user_uuid
                p.communication_uuid = s.communication_uuid
            p.communication_setting = value
            prefs.append(p)
    session.bulk_save_objects(prefs)


def _update_topic_subscriptions(mgmt: UserManagement,
                                group_memberships: List[LegacyGroup],
                                session: Session):
    if LegacyGroup.ORTHOPEDICS_SUBCOMMUNITY in group_memberships:
        t = session.query(Topic).filter(Topic.label == 'orthopedicsurgery').one_or_none()
        if t:
            UserFeedSubscription.create(user_uuid=mgmt.user.user_uuid,
                                        feed_type_uuid=t.feed_type_uuid,
                                        session=session)


def _set_iterable_status(user: User,
                         user_state: UserState,
                         session: Session):
    if user_state.iterable_unsubscribed \
            or user_state.unconfirmed_email \
            or user.deleted_at:
        return

    user_state.requires_iterable_sync = True
    session.add(user_state)


@celery_app.task(bind=True, base=TaskBase, name='figure1.backend.populate_user_queue')
def populate_user_queue(self, all_users=False):
    tl = TaskLock()
    lc = LegacyUserSync()

    def unlock_on_exception():
        logger.error(f"Caught unexpected error or exception, attempting to unlock")
        tl.unlock(scheduled_task_name=self.request.task, scheduled_task_id=self.request.id, session=self.session)

    try:
        tl.lock(scheduled_task_name=self.request.task, scheduled_task_id=self.request.id, session=self.session)
        lc.populate_legacy_user_queue(all_users=all_users, session=self.session)
        tl.unlock(scheduled_task_name=self.request.task, scheduled_task_id=self.request.id, session=self.session)
        return
    except TaskLockedException as task_locked:
        logger.error(f"Task {self.request.task} is locked by task id {self.request.id}")
        return
    except TaskUnlockException as unlock_err:
        logger.fatal(f"Task failed to unlock {unlock_err}")
        return

    except Exception as e:
        unlock_on_exception()
        raise e


@celery_app.task(bind=True, base=TaskBase, name='figure1.backend.propagate_user_updates')
def propagate_user_updates(self, all_users=False):
    tl = TaskLock()
    lc = LegacyUserSync()

    def unlock_on_exception():
        logger.error(f"Caught unexpected error or exception, attempting to unlock")
        tl.unlock(scheduled_task_name=self.request.task, scheduled_task_id=self.request.id, session=self.session)

    try:
        tl.lock(scheduled_task_name=self.request.task, scheduled_task_id=self.request.id, session=self.session)
        lc.propagate_user_updates(session=self.session)
        tl.unlock(scheduled_task_name=self.request.task, scheduled_task_id=self.request.id, session=self.session)
        return
    except TaskLockedException as task_locked:
        logger.error(f"Task {self.request.task} is locked by task id {self.request.id}")
        return
    except TaskUnlockException as unlock_err:
        logger.fatal(f"Task failed to unlock {unlock_err}")
        return

    except Exception as e:
        unlock_on_exception()
        raise e


@celery_app.task(bind=True, base=TaskBase, name='figure1.frontend.migrate_user')
def migrate_legacy_user(self, legacy_id=None, user_uuid=None, force=False):
    if user_uuid:
        User.get_user_by_uuid(user_uuid=user_uuid,
                              session=self.session,
                              raise_exception=True,
                              include_deleted=True)
        q = self.session.query(LegacyUserQueue) \
            .join(LegacyUser, LegacyUserQueue.legacy_user_id == LegacyUser.legacy_id) \
            .filter(LegacyUser.user_uuid == user_uuid) \
            .one_or_none()
    elif legacy_id:
        q = self.session.query(LegacyUserQueue) \
            .filter(LegacyUserQueue.legacy_user_id == legacy_id) \
            .one_or_none()
    else:
        logger.info("Either a legacy_id or a user_uuid must be provided")
        return "Either a legacy_id or a user_uuid must be provided"

    if not q:
        logger.info("Couldn't find a user matching user_uuid=%s or legacy_id=%s", user_uuid, legacy_id)
        return f"Couldn't find a user matching user_uuid={user_uuid} or legacy_id={legacy_id}"

    _migrate_legacy_user(q=q,
                         session=self.session,
                         prequel_model=UsersPrequelModel(),
                         force=force)
    elasticsearch_user_detail = UserDocument.elasticsearch_user_detail(user_uuid=q.user_uuid, session=self.session)
    add_or_update_user(user_uuid=q.user_uuid, user_detail=elasticsearch_user_detail)


@celery_app.task(bind=True, base=TaskBase, name='figure1.backend.migrate_communication_preferences')
def migrate_communication_preferences(self, chunk_size=5000):
    prequel_model = UsersPrequelModel()
    count = 0
    for res in self.session.query(LegacyUserQueue, User, UserState) \
            .join(User, User.user_uuid == LegacyUserQueue.user_uuid) \
            .join(UserState, UserState.user_uuid == LegacyUserQueue.user_uuid) \
            .filter(LegacyUserQueue.comm_prefs_propagated_at.is_(None),
                    User.user_uid.is_(None)) \
            .limit(chunk_size) \
            .all():
        count += 1
        q = res[0]
        user = res[1]
        user_state = res[2]
        user_dict = prequel_model.get_user(user_id=q.legacy_user_id)
        if not user_dict:
            logging.error("Failed to get user for id %s", q.legacy_user_id)
        else:
            _update_communication_preferences(user_uuid=q.user_uuid,
                                              user_dict=user_dict,
                                              user_state=user_state,
                                              session=self.session)
            _set_iterable_status(user=user,
                                 user_state=user_state,
                                 session=self.session)
        q.comm_prefs_propagated_at = datetime.utcnow()

        if not count % 500:
            logging.info("Committing legacy communication preferences, done %d", count)
            self.session.commit()

    if count:
        migrate_communication_preferences.apply_async(countdown=5)


@celery_app.task(bind=True, base=TaskBase, name='figure1.backend.migrate_saved_cases')
def migrate_saved_cases(self):
    prequel_model = UsersPrequelModel()
    count = 0
    for q in self.session.query(LegacyUserQueue) \
            .join(User, User.user_uuid == LegacyUserQueue.user_uuid) \
            .filter(User.user_uid.isnot(None),
                    LegacyUserQueue.user_uuid.isnot(None)) \
            .all():
        for c in set(prequel_model.get_saved_cases(user_id=q.legacy_user_id)):
            lc = self.session.query(LegacyCase) \
                .filter(LegacyCase.legacy_id == str(c)) \
                .join(Case, Case.case_uuid == LegacyCase.case_uuid) \
                .first()
            if lc:
                UserSavedCase.create(case_uuid=lc.case_uuid, user_uuid=q.user_uuid, session=self.session)
        count += 1
        if not count % 250:
            logging.info("Committing user legacy saved cases, done %d users", count)
            self.session.commit()


class LegacyUserSync:
    def __init__(self):
        self.kill_signal = False
        signal.signal(signal.SIGINT, self.kill)
        signal.signal(signal.SIGHUP, self.kill)

    def kill(self, signum, stack):
        logger.error(f"Caught signal {signum}, shutting down")
        self.kill_signal = True

    def populate_legacy_user_queue(self, all_users, session):
        prequel_model = UsersPrequelModel()
        logger.info("Syncing users to legacy user queue")

        if all_users:
            # When populating for all users, resume from oldest mongo ID already retrieved
            cursor = LegacyUserQueue.get_cursor(session=session)
            users = prequel_model.get_all_users(cursor=cursor)
        else:
            users = prequel_model.get_recent_users(days=7)

        count = 0
        for user in users:
            if self.kill_signal:
                logger.error("Caught kill signal, shutting down")
                session.commit()
                break
            count += 1
            LegacyUserQueue.create_or_update(legacy_user_id=user.get('_id'),
                                             last_accessed=user.get('lastAccessed'),
                                             verified=user.get('verified'),
                                             session=session)
            if not count % 10000:
                session.commit()
                logger.info(f"Committing user queue, completed {count}")
        logger.info(f"Done syncing users, completed {count}")
        return self.kill_signal

    def propagate_user_updates(self, session):
        prequel_model = UsersPrequelModel()
        count = 0
        for q in session.query(LegacyUserQueue) \
                .filter(or_(LegacyUserQueue.updated_at > LegacyUserQueue.propagated_at,
                            LegacyUserQueue.propagated_at.is_(None))) \
                .order_by(LegacyUserQueue.updated_at.desc()) \
                .limit(10000) \
                .all():
            if self.kill_signal:
                logger.error("Caught kill signal, shutting down")
                session.commit()
                break
            count += 1
            _migrate_legacy_user(q=q,
                                 prequel_model=prequel_model,
                                 session=session,
                                 force=False)
            if not count % 500:
                logger.info(f"Committing users, completed {count}")
                try:
                    session.commit()
                except DatabaseError as e:
                    logger.error(f'Failed to commit users: {e}')
                    session.rollback()
                    raise
        logger.info(f"Done updating users, completed {count}")
