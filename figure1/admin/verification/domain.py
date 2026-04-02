import logging

from celery.canvas import group
from figure1.admin.reference_data import sync_verification_tags
from figure1.common.mixpanel import send_mixpanel_event
from figure1.common.utils import validate_npi
from figure1.core import managed_session
from figure1.common.firebase import do_firebase_sync
from figure1.common.models.db import User, VerificationTag, School
from figure1.common.helpers import UserManagement, VerificationManagement
from figure1.common.types import UpdateUserModel, VerificationStatus, MixpanelEvent
from figure1.common.types.endpoints import VerificationTagUpdate
from figure1.common.types.endpoints import VerificationStatusUpdate
from figure1.events import UserEvents
from figure1.exceptions import InvalidNPINumber
from figure1.pro.verification.tasks import get_npi_info, delete_npi_info

logger = logging.getLogger(__name__)


def _validate(session, user_uid=None, moderator_uid=None):
    moderator_uuid, user_uuid = None, None
    if moderator_uid:
        moderator_uuid = User.get_user_uuid_by_uid(user_uid=moderator_uid, session=session)
        if not moderator_uuid:
            logger.error("Moderator uuid not found for uid %s", moderator_uid)
            return {
                'error': f'Moderator was not found',
                'code': 404
            }

    if user_uid:
        user_uuid = User.get_user_uuid_by_uid(user_uid=user_uid, session=session)
        if not user_uuid:
            return {
                'error': f'User {user_uid} was not found',
                'code': 404
            }

    return {
        'moderator_uuid': moderator_uuid,
        'user_uuid': user_uuid,
    }


@managed_session
def edit_verification(moderator_uid, user_uid, data, flag_for_review, session):
    res = _validate(moderator_uid=moderator_uid, user_uid=user_uid, session=session)
    if 'error' in res:
        return res
    user_uuid = res.get('user_uuid')
    moderator_uuid = res.get('moderator_uuid')
    try:
        user_mgmt = UserManagement(user_uid=user_uid, session=session)
    except Exception as e:
        logger.error(f"Unable to create user management object {e}")
        return {'error': f'Unable to lookup user {user_uid}'}

    verify_mgmt = VerificationManagement(user_uuid=user_uuid, moderator_uuid=moderator_uuid, session=session)
    verify_mgmt.flagged_for_review(flag=flag_for_review)
    first_name = data.get('first_name')
    last_name = data.get('last_name')
    specialty_uuid = data.get('specialty_uuid')
    primary_specialty = data.get('primary_specialty_tree_uuid')
    npi_number = data.get('npi_number')
    medical_license = data.get('medical_license')
    school_uuid = data.get('school_uuid')
    graduation_year = data.get('graduation_year')
    country_uuid = data.get('country_uuid')
    state_uuid = data.get('state_uuid')

    update_model = UpdateUserModel()

    if first_name is not None:
        user_mgmt.update_first_name(first_name=first_name)

    if last_name is not None:
        user_mgmt.update_last_name(last_name=last_name)

    if first_name is not None and last_name is not None:
        update_model.display_name = f'{first_name} {last_name}'

    if specialty_uuid:
        user_mgmt.replace_specialty(specialty_uuid=specialty_uuid)

    if primary_specialty:
        user_mgmt.set_primary_specialty(specialty=primary_specialty, check_verify=False)

    if npi_number is not None:
        npi_task = None
        try:
            npi_number_int = int(npi_number)
            if validate_npi(npi_number_int):
                verify_mgmt.update_npi_number(npi_number=npi_number_int)
                npi_task = get_npi_info.si(npi=npi_number_int, user_uuid=user_uuid)
            else:
                raise InvalidNPINumber(return_code=422, user_uuid=user_uuid, npi=npi_number)
        except ValueError:
            if npi_number.strip() == "":
                verify_mgmt.delete_npi()
                npi_task = delete_npi_info.si(user_uuid=user_uuid)

        if npi_task:
            npi_task.link(do_firebase_sync.si(firebasemodel='FirebaseUsersDB', uuid=user_uuid))
            npi_task.apply_async()

    if medical_license is not None:
        verify_mgmt.update_license_number(license_number=medical_license)

    if school_uuid is not None:
        if str(school_uuid).strip() == "":
            school_uuid = None
        else:
            s = session.query(School).filter(School.school_uuid == school_uuid).one_or_none()
            if not s:
                return {'error': 'Invalid school_uuid'}

        verify_mgmt.update_school(school_uuid=school_uuid)

    if graduation_year is not None:
        graduation_year = graduation_year if str(graduation_year).strip() else None
        verify_mgmt.update_graduation_year(graduation_year=graduation_year)

    if country_uuid or state_uuid:
        update_model.country_uuid = country_uuid
        update_model.state_uuid = state_uuid

    user_mgmt.update_user_profile(profile_update=update_model)

    return UserEvents.USER_PROFILE_SYNC(user_uuid=user_uuid)


@managed_session
def add_verification_note(moderator_uid, user_uids, text, flag_for_review, session):
    task_group = []
    for user_uid in user_uids:
        res = _validate(moderator_uid=moderator_uid, user_uid=user_uid, session=session)
        if 'error' in res:
            return res
        moderator_uuid = res.get('moderator_uuid')
        user_uuid = res.get('user_uuid')

        verify_mgmt = VerificationManagement(user_uuid=user_uuid, moderator_uuid=moderator_uuid, session=session)
        verify_mgmt.flagged_for_review(flag=flag_for_review)
        verify_mgmt.add_note(moderator_uuid=moderator_uuid, text=text)
        task_group.append(UserEvents.USER_PROFILE_SYNC(user_uuid=user_uuid))
    return group(task_group)


@managed_session
def update_verification_status(status_update: VerificationStatusUpdate, session):
    if not isinstance(status_update, VerificationStatusUpdate):
        raise ValueError("status_update must be type VerificationStatusUpdate")
    res = _validate(moderator_uid=status_update.moderatorUid, session=session)
    if 'error' in res:
        return res
    moderator_uuid = res.get('moderator_uuid')
    task_group = []
    if status_update.userUids:
        for user_uid in status_update.userUids:
            res = _validate(user_uid=user_uid, session=session)
            if 'error' in res:
                return res
            user_uuid = res.get('user_uuid')
            verify_mgmt = VerificationManagement(user_uuid=user_uuid, moderator_uuid=moderator_uuid, session=session)
            if status_update.verificationStatus:
                if status_update.verificationStatus == VerificationStatus.REVIEW_REQUIRED:
                    verify_mgmt.flagged_for_review(flag=True)
                    verify_mgmt.update_status(status=VerificationStatus.VERIFIED)
                else:
                    verify_mgmt.update_status(status=status_update.verificationStatus)
            if status_update.flagForReview is True or status_update.flagForReview is False:
                verify_mgmt.flagged_for_review(flag=status_update.flagForReview)
                if status_update.flagForReview is True:
                    verify_mgmt.update_status(status=VerificationStatus.VERIFIED)
            session.flush()
            UserEvents.USER_VERIFICATION_STATE_CHANGE(user_uuid=user_uuid, moderator_uid=status_update.moderatorUid)

            if status_update.verificationStatus == VerificationStatus.VERIFIED:
                verification_type = verify_mgmt.verification.verification_type.name.lower()
                send_mixpanel_event.delay(user_uuid=user_uuid,
                                          event_name=MixpanelEvent.USER_VERIFIED.value,
                                          properties={"Method": verification_type})
            task_group.append(UserEvents.USER_PROFILE_SYNC(user_uuid=user_uuid))
    return group(task_group)


@managed_session
def update_user_tags(tag_update: VerificationTagUpdate, session):
    if not isinstance(tag_update, VerificationTagUpdate):
        raise ValueError("tag_update must be an instance of VerificationTagUpdate")
    moderator_uuid = _validate(moderator_uid=tag_update.moderatorUid, session=session).get('moderator_uuid')
    if tag_update.userUids:
        for user_uid in tag_update.userUids:
            res = _validate(user_uid=user_uid, session=session)
            if 'error' in res:
                logger.error("Caught error %s", res)
                return res
            user_uuid = res.get('user_uuid')
            verify_mgmt = VerificationManagement(user_uuid=user_uuid, moderator_uuid=moderator_uuid, session=session)
            verify_mgmt.update_tags(tag_uuids=tag_update.tagUuids)
            session.flush()
            logger.info("Updating user %s", user_uuid)


@managed_session
def create_tag(moderator_uid, name, session):
    res = _validate(moderator_uid=moderator_uid, session=session)
    if 'error' in res:
        return res

    try:
        VerificationTag.create(name=name, session=session)
    except Exception as e:
        session.rollback()
        logging.error(f'Failed to create tag: {e}')
        return {'error': 'Failed to create tag'}

    sync_verification_tags.delay()
    return {'success': 'Tag created'}


@managed_session
def update_tag(moderator_uid, uuid, name, session):
    res = _validate(moderator_uid=moderator_uid, session=session)
    if 'error' in res:
        return res

    try:
        VerificationTag.update(tag_uuid=uuid, name=name, session=session)
    except Exception as e:
        session.rollback()
        logging.error(f'Failed to update tag: {e}')
        return {'error': 'Failed to update tag'}

    sync_verification_tags.delay()
    return {'success': 'Tag updated'}


@managed_session
def delete_tag(moderator_uid, uuid, session):
    res = _validate(moderator_uid=moderator_uid, session=session)
    if 'error' in res:
        return res

    try:
        VerificationTag.delete(tag_uuid=uuid, session=session)
    except Exception as e:
        session.rollback()
        logging.error(f'Failed to delete tag: {e}')
        return {'error': 'Failed to delete tag'}

    sync_verification_tags.delay()
    return {'success': 'Tag deleted'}
