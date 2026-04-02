import enum
import logging
import re
import string
from random import choice
from uuid import UUID

from celery import group
from celery.canvas import Signature
from firebase_admin import auth
from firebase_admin.auth import ActionCodeSettings
from pydantic import EmailError
from pydantic import validate_email
from sqlalchemy import func
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import Session

from figure1.common.activities.user_profile_activities import verify_user_activity_count_task
from figure1.common.comms import sync_communication_preferences_task
from figure1.common.elasticsearch import add_or_update_user
from figure1.common.firebase import check_firebase_uid
from figure1.common.firebase import create_firebase_user
from figure1.common.firebase import do_firebase_sync
from figure1.common.firebase import get_firebase_user
from figure1.common.helpers import UserDocument
from figure1.common.helpers import UserManagement
from figure1.common.helpers.user import OnboardingWorkflow
from figure1.common.helpers.word_filter import WordMatcher
from figure1.common.iterable import delete_iterable_users
from figure1.common.iterable import IterableAPI
from figure1.common.iterable import update_iterable_user
from figure1.common.iterable import update_iterable_user_comm_preferences
from figure1.common.mixpanel import update_mixpanel_user
from figure1.common.models.db import AnonymousUser
from figure1.common.models.db import DmdNpiInfo
from figure1.common.models.db import GroupMemberFilter
from figure1.common.models.db import Groups
from figure1.common.models.db import LegacyUser
from figure1.common.models.db import User
from figure1.common.models.db import UserFollow
from figure1.common.models.db import UserProfile
from figure1.common.models.firebase import FirebaseCollectionManager
from figure1.notifications import notify_user_of_new_follower_task
from figure1.common.types import GroupModel
from figure1.common.types import StandaloneEmailKind
from figure1.common.types import UNKNOWN_SCREEN
from figure1.common.types import UpdateUserModel
from figure1.common.types import UserTypes
from figure1.common.types import UserVerificationUpdate
from figure1.common.types import VerificationType
from figure1.common.types import OnboardingState
from figure1.configuration import app_settings
from figure1.core import firebase_app
from figure1.core import managed_session
from figure1.events import UserEvents
from figure1.exceptions import DuplicateUser
from figure1.exceptions import GroupException
from figure1.exceptions import InvalidNPINumber
from figure1.exceptions import InvalidUserType
from figure1.exceptions import IterableException
from figure1.exceptions import IterableMisconfiguredException
from figure1.exceptions import UserDeleted
from figure1.exceptions import UserError
from figure1.exceptions import UsernameNotAllowed
from figure1.exceptions import UserNotFound
from figure1.exceptions.user import UserIsNotInvited
from figure1.feeds import write_feed_metadata_task
from figure1.pro.cases.domain import update_cme_for_anonymous_user
from figure1.pro.groups.domain import add_members_to_group
from figure1.pro.users import check_legacy_password
from figure1.pro.users import get_user_by_email_case_insensitive
from figure1.pro.verification.verify import verify_by_npi

logger = logging.getLogger(__name__)
fb = FirebaseCollectionManager()


class LoginPath(enum.Enum):
    HAS_FIREBASE_AUTH = 'has_firebase_auth'
    LEGACY_USER_INVALID_PASSWORD = 'legacy_user_invalid_password'
    LEGACY_USER_VALID_PASSWORD = 'legacy_user_valid_password'


def _parse_user_type(user_type):
    if not user_type or user_type.upper() not in [t.name for t in UserTypes]:
        raise InvalidUserType(msg=f'Invalid usertype: {user_type}', return_code=422)
    return UserTypes[user_type.upper()]


def _random_string(length):
    letters = string.ascii_letters
    return ''.join(choice(letters) for _ in range(length))


def _obfuscate_email(email):
    """
    Returns an email in the form b*****@figure1.com
    """
    try:
        split = email.rsplit('@', 1)
        result = split[0][0] + '******@' + split[1]
    except ValueError:
        return ''
    except IndexError:
        return ''

    return result


def _get_user_by_email_or_username(session, email=None, username=None):
    user = None
    if email:
        email = email.strip()
        user = session.query(User) \
            .filter(func.lower(User.email) == func.lower(email),
                    User.deleted_at.is_(None)) \
            .one_or_none()
    if username:
        username = username.strip()
        user = session.query(User) \
            .filter(User.username == username,
                    User.deleted_at.is_(None)) \
            .one_or_none()
        if not user:
            # Fallback check to handle email being passed as the wrong property
            user = session.query(User) \
                .filter(func.lower(User.email) == func.lower(username),
                        User.deleted_at.is_(None)) \
                .one_or_none()
    if not user:
        raise UserNotFound(msg="Cannot find existing user")
    else:
        return user


def _add_user_to_group(session, group_uuid, user_uuid):
    try:
        res = add_members_to_group(group_uuid=group_uuid, users_uuid=[user_uuid], session=session)
        return res.pop('task')
    except GroupException:
        logger.error("couldn't add member to group")
    except TypeError:
        logger.error("users_uuid must be a list. nothing to do")


def _validate_anonymous_user_before_create(anon_user: AnonymousUser, session: Session):
    if not anon_user:
        return False

    linked_user = User.get_user_by_uuid(user_uuid=anon_user.user_uuid, session=session)
    if linked_user:
        logger.error(f"The anonymous_uid: {anon_user.user_uid} linked to an existing user")
        return False

    return True


def _get_npi_number_from_dmd_by_email(email: str, session: Session):
    """
    Given a email, return a npi number from DMD or None
    :param email:
    :param session:
    :return:
    """
    dmd_npi_info = DmdNpiInfo.get_dmd_npi_info_by_email(email=email, session=session)
    if dmd_npi_info:
        return dmd_npi_info.dmd_npi

    return None


@managed_session
def invite_colleagues(user_uid, emails, session):
    """
    Sends invitations to join figure1 to a list of emails
    :param emails:
    :param user_uid:
    :param session:
    :return:
    """
    campaign_id = app_settings.iterable_invite_colleagues_campaign_id
    if not campaign_id:
        logger.error("env iterable_invite_colleagues_campaign_id is missing")
        raise IterableMisconfiguredException(msg="env iterable_invite_colleagues_campaign_id is missing",
                                             return_code=501)
    iterable_client = IterableAPI()
    if iterable_client.iterable_api_disabled:
        logger.error("Iterable api is disabled, nothing to do")
        return None

    invitee = User.get_user_by_uid(user_uid=user_uid, session=session, raise_exception=True)
    data_fields = {
        "inviteeEmail": invitee.email,
        "inviteeUID": str(user_uid)
    }
    if invitee.username:
        data_fields["inviteeUsername"] = invitee.username
    if invitee.first_name:
        data_fields["firstName"] = invitee.first_name
    if invitee.last_name:
        data_fields["lastName"] = invitee.last_name
    if invitee.user_uuid:
        data_fields["inviteeUUID"] = str(invitee.user_uuid)
    sent_emails = []
    unsent_emails = []
    for email in emails:
        try:
            validated_email = validate_email(email)
            iterable_client.trigger_campaign(campaign_id=campaign_id, recipient_email=validated_email[1],
                                             data_fields=data_fields)
            sent_emails.append(validated_email[1])
        except EmailError:
            unsent_emails.append(email)
            logger.exception("Email is incorrect %s", email)
        except IterableException:
            unsent_emails.append(email)
            logger.exception("Encountered an error while triggering the campaign")

    task = delete_iterable_users.si(emails=sent_emails)
    task.apply_async(countdown=10)
    return dict(sent_emails=sent_emails, unsent_emails=unsent_emails)


@managed_session
def force_user_sync(session, user_uid):
    logger.error("Syncing user_uid %s", user_uid)
    mgmt = UserManagement(user_uid=user_uid, session=session, include_deleted=True)
    if mgmt.user.deleted_at is not None:
        return delete_user(user_uid=user_uid, session=session)
    user_uuid = str(mgmt.user.user_uuid)
    # Set up task to sync user to firebase
    task = do_firebase_sync.si(firebasemodel='FirebaseUsersDB', uuid=user_uuid, merge=False)
    task.link(do_firebase_sync.si(firebasemodel='FirebaseUsersProfileDB', uuid=user_uuid, merge=False))
    task.link(verify_user_activity_count_task.si(user_uuid=user_uuid))
    task.link(sync_communication_preferences_task.si(user_uuid=user_uuid))
    # Set up task to sync user to iterable and mixpanel
    iterable_task = update_iterable_user.si(user_uid=user_uid)
    iterable_task.link(update_iterable_user_comm_preferences.si(user_uid=user_uid))
    iterable_task.link(update_mixpanel_user.si(user_uuid=user_uuid))
    # Execute the task groups in parallel
    user_task_group = group(iterable_task, task)
    user_task_group.apply_async()


@managed_session
def delete_user_profile(user_uid, data, session=None):
    logger = logging.getLogger(__name__)
    mgmt = UserManagement(user_uid=user_uid, session=session)
    interests = data.get("interests")
    education = data.get("education")
    experience = data.get("experience")
    affiliations = data.get("affiliations")
    if education:
        mgmt.delete_user_education(educationUuids=education)
    if experience:
        mgmt.delete_user_experience(experienceUuids=experience)
    if affiliations:
        mgmt.delete_user_affiliations(affiliationUuids=affiliations)
    session.commit()
    task = do_firebase_sync.si(firebasemodel='FirebaseUsersDB', uuid=str(mgmt.user.user_uuid), merge=False)
    task.link(do_firebase_sync.si(firebasemodel='FirebaseUsersProfileDB', uuid=str(mgmt.user.user_uuid)))
    task.apply_async()
    return {'success': "User profile data deleted"}


@managed_session
def delete_user(user_uid, session=None):
    user = User.get_user_by_uid(user_uid=user_uid, session=session, raise_exception=True, include_deleted=True)
    task = UserEvents.USER_DELETED(user_uuid=str(user.user_uuid))
    task.apply_async()


@managed_session
def create_anonymous_user(user_uid, email=None, session=None):
    """
    Given a user_uid and optionally an email, create and anonymous user and return a uuid. If an email is passed,
    check if this user exists in our database. If so, return that uuid.
    :param user_uid:
    :param email: This is most often a user_uuid because this is how we have to identify the user in query parameters
    from the emails that are sent from iterable.
    :param session:
    :return:
    """
    user = AnonymousUser()
    user.user_uid = user_uid
    existing_user = None
    if email:
        try:
            UUID(email)
        except (TypeError, ValueError):
            pass
        else:
            existing_user = session.query(User.user_uuid).filter(User.user_uuid == email).one_or_none()
        if not existing_user:
            try:
                validate_email(email)
            except EmailError:
                pass
            else:
                user.email = email
                existing_user = session.query(User.user_uuid) \
                    .filter(func.lower(User.email) == email.lower()) \
                    .one_or_none()
    if existing_user:
        user.user_uuid = existing_user[0]
        session.merge(user)
        return {'userUuid': str(existing_user[0])}
    session.merge(user)
    u = session.query(AnonymousUser).get(user.user_uid)
    return {'userUuid': str(u.user_uuid)}


@managed_session
def admin_create_user_internal(user_type: UserTypes, email, username, password=None, session=None):
    """
    Requires a user type, and email, username, and password. If a user_uid is passed, then it is assumed that
    the firestore auth record already exists.
    Otherwise, a firestore auth record is created with the email and password passed in

    :param user_type:
    :param email:
    :param username:
    :param user_uid:
    :param password:
    :param session:
    :return:
    """

    user_type = _parse_user_type(user_type)

    validated_model = UpdateUserModel(userType=user_type,
                                      email=email,
                                      username=username)
    mgmt = UserManagement(email=validated_model.email,
                          username=validated_model.username,
                          session=session,
                          is_admin_created=True)
    mgmt.add_admin_user(email=validated_model.email,
                        username=validated_model.username,
                        user_type=validated_model.userType)

    user = _get_user_by_email_or_username(email=validated_model.email,
                                          username=validated_model.username, session=session)
    user.user_uid = create_firebase_user(email=user.email)
    session.merge(user)
    session.commit()
    UserEvents.USER_PROFILE_SYNC(user_uuid=str(user.user_uuid)).apply().get()
    return UserDocument.user_detail(user_uuid=str(user.user_uuid), session=session)


@managed_session
def admin_update_user_internal(user_type: UserTypes,
                               user_update: UpdateUserModel,
                               user_uid=None,
                               email=None,
                               username=None,
                               session=None):
    """
    Requires user_type, and one of user_uid, email or username, returns 404 if the user isn't found.
    user_type is the type that this user should be moved to. If the type doesn't exist, 400 is returned.

    Optionally, the same structure for user updates can be passed in, this will be passed through to update the user.

    :param user_update:
    :param user_type:
    :param user_uid:
    :param email:
    :param username:
    :param session:
    :return:
    """

    user_type = _parse_user_type(user_type)
    if email:
        mgmt = UserManagement(email=email, session=session)
    elif username:
        mgmt = UserManagement(username=username, session=session)
    elif user_uid:
        mgmt = UserManagement(user_uid=user_uid, session=session)
    else:
        raise UserError(msg="Requires one of email, username, or user_uid", return_code=409)

    if user_type:
        mgmt.set_user_type(user_type=user_type)
    session.flush()

    if user_update.primarySpecialty:
        mgmt.set_primary_specialty(specialty=user_update.primarySpecialty, check_verify=False)
        user_update.primarySpecialty = None
    return update_user_internal(user_uid=mgmt.user.user_uid, user_update=user_update, session=session)


@managed_session
def create_user_internal(user_uid,
                         email,
                         first_name,
                         last_name,
                         session,
                         user_npi=None,
                         profession_uuid=None,
                         country_uuid=None,
                         group_uuid=None,
                         screen_id=UNKNOWN_SCREEN,
                         anonymous_uid=None):
    group_uuids = []
    user = User.check_for_user_conflict(user_uid=user_uid, email=email, session=session)
    if user:
        if user.deleted_at is not None:
            raise UserDeleted(user_uid=user_uid, msg="User existed but has been deleted", return_code=410)
        else:
            return {
                'error': f"Unable to create user due to duplicate data",
                'code': 409
            }

    logger.info("Creating new user")
    if first_name or last_name or country_uuid:
        user_model = UpdateUserModel(first_name=first_name, last_name=last_name, country_uuid=country_uuid,
                                     email=email)
    else:
        user_model = UpdateUserModel(email=email)

    if user_model.email.endswith("figure1.com"):
        user_model.userType = UserTypes.FIGURE1_INTERNAL
        user_model.userHiddenFromSearch = True
    elif user_model.email.endswith("formedics.com"):
        user_model.userType = UserTypes.FIGURE1_INTERNAL
        user_model.userHiddenFromSearch = True
    else:
        user_model.userType = UserTypes.USER

    anon_user = AnonymousUser.get_anonymous_user_by_uid(user_uid=anonymous_uid, session=session,
                                                        raise_exception=False)

    user_uuid, is_valid_anonymous_user = None, False
    if _validate_anonymous_user_before_create(anon_user=anon_user, session=session):
        user_uuid = anon_user.user_uuid
        is_valid_anonymous_user = True

    potential_groups = GroupMemberFilter.get_all_group_member_filters_by_email(session, email)
    first_name = user_model.first_name
    last_name = user_model.last_name
    country_uuid = user_model.country_uuid
    for each_potential_group in potential_groups:
        if not first_name and each_potential_group.user_first_name:
            first_name = each_potential_group.user_first_name
        if not last_name and each_potential_group.user_last_name:
            last_name = each_potential_group.user_last_name
        if not country_uuid and each_potential_group.country_uuid:
            country_uuid = each_potential_group.country_uuid

    mgmt = UserManagement(user_uid=user_uid, user_uuid=user_uuid, session=session, is_new_user=True)
    ret = mgmt.add_user(first_name=first_name,
                        last_name=last_name,
                        email=user_model.email,
                        user_type=user_model.userType,
                        user_uuid=user_uuid,
                        legacy=False)
    logger.info("User management object created")

    logger.info("Added user")
    if profession_uuid:
        logger.info("Adding profession")
        mgmt.set_primary_specialty(specialty=profession_uuid)
        logger.info("Profession Added")
    user_uuid = str(mgmt.user.user_uuid)
    if 'error' in ret:
        return ret
    if country_uuid:
        us = UserProfile()
        us.user_uuid = mgmt.user.user_uuid
        us.country_uuid = country_uuid
        session.merge(us)
    group_tasks = []
    if group_uuid:
        group_tasks.append(_add_user_to_group(session, group_uuid, user_uuid))
        group_uuids.append(group_uuid)

    npi_task, is_user_verified_once = None, False
    is_user_specialty_set = False
    for each_potential_group in potential_groups:
        if not is_user_verified_once and each_potential_group.user_npi:
            npi_number = int(each_potential_group.user_npi)
            try:
                update = UserVerificationUpdate(method=VerificationType.NPI,
                                                user_uid=user_uid,
                                                npi_number=npi_number)
                npi_task = verify_by_npi(user_uuid=user_uuid, update=update, session=session)
                is_user_verified_once = True
            except InvalidNPINumber:
                logger.error(f"Unable to verify user: Invalid NPI number: %s", npi_number)
        if not is_user_specialty_set and each_potential_group.tree_uuid:
            mgmt.set_primary_specialty(specialty=each_potential_group.tree_uuid)
            is_user_specialty_set = True

        group_tasks.append(_add_user_to_group(session, each_potential_group.group_uuid, user_uuid))
        group_uuids.append(each_potential_group.group_uuid)

    if not user_npi:
        user_npi = _get_npi_number_from_dmd_by_email(email=email, session=session)

    if user_npi:
        try:
            update = UserVerificationUpdate(method=VerificationType.NPI,
                                            user_uid=user_uid,
                                            npi_number=user_npi)
            npi_task = verify_by_npi(user_uuid=user_uuid, update=update, session=session)
            mgmt.set_onboarding_state(onboarding_state=OnboardingState.CONFIRMATION)
        except InvalidNPINumber:
            logger.error(f"Unable to verify user %s: Invalid NPI number: %s", user_uid, user_npi)
            raise
    else:
        OnboardingWorkflow.update_onboarding_state(user_uuid=user_uuid, session=session)

    mgmt.set_user_flags(flag='hidden_from_search', state=user_model.userHiddenFromSearch)

    mgmt.session.commit()
    task = group(do_firebase_sync.si(firebasemodel='FirebaseUsersDB', uuid=user_uuid),
                 do_firebase_sync.si(firebasemodel='FirebaseUsersProfileDB', uuid=user_uuid),
                 do_firebase_sync.si(firebasemodel='FirebaseUserCmeDB', uuid=user_uuid),
                 *filter(None, group_tasks),
                 *filter(None, [npi_task]))

    task.apply_async()

    if anon_user and is_valid_anonymous_user:
        update_cme_for_anonymous_user(user_uid=user_uid, user_uuid=None, anon_user_uuid=anon_user.user_uuid,
                                      session=session)
    UserEvents.USER_ONBOARDING_STARTED(user_uuid=user_uuid, session=session)
    return {
        'onboardingState': mgmt.user.user_state.onboarding_state.value,
        'user_uuid': user_uuid,
        'group_uuids': group_uuids
    }


@managed_session
def link_existing_anonymous_user(anonymous_uid, user_uid, session=None):
    """
    if an anon user completes few slides in cme then signs in, this func will search the db for anonymous user, gets
    the real user info from the db, then pushes the progress of the anonymous user to the real user.
    :param anonymous_uid:
    :param user_uid:
    :param session:
    :return:
    """
    anon_user = AnonymousUser.get_anonymous_user_by_uid(user_uid=anonymous_uid,
                                                        session=session,
                                                        raise_exception=True)
    user = User.get_user_by_uid(user_uid=user_uid, session=session, raise_exception=True)

    update_cme_for_anonymous_user(user_uid=user.user_uid, user_uuid=user.user_uuid,
                                  anon_user_uuid=anon_user.user_uuid, session=session)
    return {'success': "anonymous user has been linked to the existing user"}


def check_usernames(username):
    """
    A username may have special characters -+._
    A user must be at least 3 characters long

    Finally, each username is checked against a list of words that should not be allowed. There are two lists,
    forbidden words are words that cannot appear anywhere in the username, disallowed words can used as part of
    a username, but cannot be used on their own.

    :param username: The username to check
    :param session:
    :return: None
    :raises: UsernameValidation
    """
    correct_pattern = r'\A(?=.{3})[\\+._-]*[a-zA-Z0-9]{1,}[a-zA-Z0-9\\+._-]{1,}[\\+._-]*$'
    if not re.match(correct_pattern, username):
        raise UsernameNotAllowed(message=f"Username {username} does not meet the character requirements")
    logger.error("Checking username %s", username)
    WordMatcher.find_blocked_word_in_string(username)
    logger.error("Username %s passed", username)


@managed_session
def sync_public_profile(user_uuid=None, user_uid=None, username=None, session=None):
    mgmt = UserManagement(user_uid=user_uid, user_uuid=user_uuid, username=username, session=session)
    do_firebase_sync.delay(firebasemodel='FirebaseUsersProfileDB', uuid=mgmt.user.user_uuid)
    return {
        'success': 'Task to sync user started',
        'userUuid': mgmt.user.user_uuid,
        'userUid': mgmt.user.user_uid,
    }


@managed_session
def update_user_internal(user_uid: str,
                         user_update: UpdateUserModel,
                         session: Session = None):
    """
    First clear out the users recommended for you feed, then add whatever is sent. At the end, the recommended for you
    feed is regenerated.

    :param user_uid:
    :param user_update:
    :param session:
    :return:
    """
    logger = logging.getLogger(__name__)
    u = user_update
    mgmt = UserManagement(user_uid=user_uid, session=session)
    user_uuid = str(mgmt.user.user_uuid)
    user = mgmt.user

    if u.first_name:
        mgmt.update_first_name(first_name=u.first_name)

    if u.last_name:
        mgmt.update_last_name(last_name=u.last_name)

    if u.first_name and u.last_name and not u.display_name:
        u.display_name = f'{u.first_name} {u.last_name}'

    if u.username:
        mgmt.update_username(username=u.username)

    if u.specialtyTreeUuids or u.specialtyTreeUuids == []:
        mgmt.set_specialties(specialties=u.specialtyTreeUuids)

    if u.primarySpecialty:
        if user.onboarding_completed is True:
            mgmt.set_primary_specialty(specialty=u.primarySpecialty)
        else:
            mgmt.set_primary_specialty(specialty=u.primarySpecialty, check_verify=False)

    if u.interests:
        mgmt.set_interests(interests=u.interests)

    if u.custom_school or u.custom_specialty:
        mgmt.set_custom_data(data=u)

    if u.education is not None:
        if not len(u.education):
            logger.debug("Got empty array - deleting user education")
            mgmt.delete_user_education()
        else:
            mgmt.update_user_education(data=u.education)
            mgmt.add_user_education(data=u.education)
    if u.experience is not None:
        if not len(u.experience):
            logger.debug("Got empty array - deleting user experience")
            mgmt.delete_user_experience()
        else:
            mgmt.update_user_experience(data=u.experience)
            mgmt.add_user_experience(data=u.experience)

    if u.affiliations is not None:
        if not len(u.affiliations):
            logger.debug("Got empty array - deleting user experience")
            mgmt.delete_user_affiliations()
        else:
            mgmt.update_user_affiliation(data=u.affiliations)
            mgmt.add_user_affiliations(data=u.affiliations)

    if u.sponsoredContentEnabled is True or u.sponsoredContentEnabled is False:
        mgmt.set_user_flags(flag='sponsored_content_enabled', state=u.sponsoredContentEnabled)

    if u.onboardingCompleted is True or u.onboardingCompleted is False:
        mgmt.set_user_flags(flag='onboarding_completed', state=u.onboardingCompleted)

    if u.onboardingInterestsCompleted is True or u.onboardingInterestsCompleted is False:
        mgmt.set_user_flags(flag='onboarding_interests_completed', state=u.onboardingInterestsCompleted)

    if u.email and u.email.lower() != mgmt.user.email.lower():
        if get_user_by_email_case_insensitive(email=u.email, session=session):
            raise DuplicateUser
        old_email = mgmt.user.email
        mgmt.set_user_email(email=u.email)
        UserEvents.USER_EMAIL_UPDATED(user_uid=user_uid, old_email=old_email, new_email=u.email)
    mgmt.update_user_profile(profile_update=u)

    force_author_update = user.user_type not in [UserTypes.FIGURE1_INTERNAL, UserTypes.USER]

    task = UserEvents.USER_UPDATED(user_uuid=user_uuid,
                                   session=session,
                                   user_update_model=u,
                                   force_author_update=force_author_update,
                                   return_task=True)
    session.flush()

    if u.onboardingCompleted:
        write_feed_metadata_task.delay(user_uid=user_uid)

    return {'task': task,
            **UserDocument.user_detail(user_uuid=user_uuid, session=session)}


@managed_session
def update_user_avatar_internal(user_uid, url, session=None) -> Signature:
    mgmt = UserManagement(user_uid=user_uid, session=session)
    mgmt.update_user_profile(profile_update=UpdateUserModel(avatar=url))

    user_uuid = str(mgmt.user.user_uuid)

    return UserEvents.USER_UPDATED(user_uuid=user_uuid, session=session, avatar_updated=True, return_task=True)


@managed_session
def update_background_image(user_uid, url, session=None) -> Signature:
    mgmt = UserManagement(user_uid=user_uid, session=session)
    mgmt.update_user_profile(profile_update=UpdateUserModel(backgroundImage=url))
    user_uuid = str(mgmt.user.user_uuid)
    return UserEvents.USER_UPDATED(user_uuid=user_uuid, session=session, return_task=True)


@managed_session
def follow_user(user_uuid, user_uid, session=None):
    requester_user = User.get_user_by_uid(user_uid=user_uid, session=session, raise_exception=True)
    target_user = User.get_user_by_uuid(user_uuid=user_uuid, session=session, raise_exception=True)
    UserFollow.follow_user(session=session,
                           user_uuid=target_user.user_uuid,
                           follower_user_uuid=requester_user.user_uuid)
    session.flush()

    req_user_profile = UserDocument.get_compact_user_data(user_uid=user_uid, session=session)
    fb.set_fs_client(collections=['usersProfileDB', 'followers'],
                     documents=[str(target_user.user_uuid), str(requester_user.user_uuid)])
    fb.set(req_user_profile, merge=False)

    target_profile = UserDocument.get_compact_user_data(user_uuid=user_uuid, session=session)
    fb.set_fs_client(collections=['usersProfileDB', 'following'],
                     documents=[str(requester_user.user_uuid), user_uuid])
    fb.set(target_profile)

    task = do_firebase_sync.si(firebasemodel='FirebaseUsersProfileDB', uuid=str(target_user.user_uuid))
    task.link(do_firebase_sync.si(firebasemodel='FirebaseUsersProfileDB', uuid=str(requester_user.user_uuid)))
    task.apply_async()

    if requester_user.user_type != UserTypes.FIGURE1_INTERNAL or not requester_user.hidden_from_search:
        notify_task = notify_user_of_new_follower_task.si(follower_uuid=requester_user.user_uuid,
                                                          target_user_uuid=target_user.user_uuid)
        notify_task.apply_async(countdown=10)
    return {'success': 'user followed'}


@managed_session
def unfollow_user(user_uuid, user_uid, session=None):
    requester_user = User.get_user_by_uid(user_uid=user_uid, session=session, raise_exception=True)
    target_user = User.get_user_by_uuid(user_uuid=user_uuid, session=session, raise_exception=True)

    UserFollow.unfollow_user(session=session,
                             user_uuid=target_user.user_uuid,
                             follower_user_uuid=requester_user.user_uuid)
    session.flush()

    fb.set_fs_client(collections=['usersProfileDB', 'followers'],
                     documents=[str(target_user.user_uuid), str(requester_user.user_uuid)])
    fb.delete_document()
    fb.set_fs_client(collections=['usersProfileDB', 'following'],
                     documents=[str(requester_user.user_uuid), user_uuid])
    fb.delete_document()
    task = do_firebase_sync.si(firebasemodel='FirebaseUsersProfileDB', uuid=str(target_user.user_uuid))
    task.link(do_firebase_sync.si(firebasemodel='FirebaseUsersProfileDB', uuid=str(requester_user.user_uuid)))
    task.apply_async()

    return {'success': 'user unfollowed'}


@managed_session
def user_auth_check(email, username, password, session):
    user = _get_user_by_email_or_username(email=email, username=username, session=session)

    if user.user_uid:
        check_firebase_uid(uid=user.user_uid, email=user.email, fb_app=firebase_app())
        return {
            'status': LoginPath.HAS_FIREBASE_AUTH.value,
            'email': user.email
        }

    lu = session.query(LegacyUser) \
        .filter(LegacyUser.user_uuid == user.user_uuid) \
        .one_or_none()
    if not lu:
        raise UserError(msg=f'Legacy ID could not be found for user {user.user_uuid}', rc=500)

    if check_legacy_password(legacy_id=lu.legacy_id, password=password):
        return {
            'status': LoginPath.LEGACY_USER_VALID_PASSWORD.value,
            'email': user.email
        }
    else:
        return {
            'status': LoginPath.LEGACY_USER_INVALID_PASSWORD.value,
            'email': user.email
        }


@managed_session
def _prepare_firestore_link_gen(email=None, username=None, session=None):
    fb_app = firebase_app()
    user = _get_user_by_email_or_username(email=email, username=username, session=session)
    fb_user_uid = get_firebase_user(email=user.email, fb_app=fb_app)
    if not fb_user_uid:
        fb_user_uid = create_firebase_user(email=user.email, uid=user.user_uid, fb_app=fb_app)
    if user.user_uid is not None and user.user_uid != fb_user_uid:
        logging.error("User %s has uid %s that does not match the auth record uid %s",
                      user.email, user.user_uid, fb_user_uid)
        user.user_uid = fb_user_uid
        session.add(user)
    if user.user_uid is None:
        user.user_uid = fb_user_uid
        session.merge(user)
        session.flush()
        UserEvents.USER_UID_SET(user_uuid=user.user_uuid, user_uid=user.user_uid, session=session, wait=False)
    else:
        session.flush()
        task = UserEvents.USER_PROFILE_SYNC(user_uuid=str(user.user_uuid))
        task.apply_async(countdown=5)

    return str(user.user_uuid), user.email, fb_app


def generate_password_reset_link(email=None, username=None):
    """
    Generates a password reset link for a user.
    If the user does not yet exist in firebase, create the user first.
    :param email:
    :param username:
    :return:
    """
    user_uuid, email, app = _prepare_firestore_link_gen(email=email, username=username)
    reset_link = auth.generate_password_reset_link(email=email, app=app)
    return dict(resetLink=reset_link, email=email, userUuid=user_uuid)


def generate_email_login_link(email=None, username=None):
    """
    Generates an email login link for a user.
    If the user does not yet exist in firebase, create the user first.
    :param email:
    :param username:
    :return:
    """

    user_uuid, email, app = _prepare_firestore_link_gen(email=email, username=username)
    login_link = auth.generate_sign_in_with_email_link(email=email,
                                                       app=app,
                                                       action_code_settings=ActionCodeSettings(
                                                           url=app_settings.generate_default_login_link()))
    return dict(loginLink=login_link, email=email, userUuid=user_uuid)


@managed_session
def reset_password(email, username, session=None):
    reset_link = generate_password_reset_link(email=email, username=username)
    IterableAPI().send_standalone_email(kind=StandaloneEmailKind.RESET_PASSWORD,
                                        recipient_email=reset_link.get("email"),
                                        data_fields=reset_link,
                                        session=session)
    return {
        'success': 'Password reset email sent',
        'email': _obfuscate_email(reset_link.get("email")),
    }


@managed_session
def send_login_link(email, username, session=None):
    login_link = generate_email_login_link(email=email, username=username)
    IterableAPI().send_standalone_email(kind=StandaloneEmailKind.LOGIN_LINK,
                                        recipient_email=login_link.get("email"),
                                        data_fields=login_link,
                                        session=session)
    return {
        'success': 'Login link sent',
        'email': _obfuscate_email(login_link.get("email")),
    }


@managed_session
def set_user_uid(email, user_uid, session, anonymous_uid=None):
    """
    The longest part of this is running the legacy user migration. However the frontends expect this to be done
    when this returns. So we try to start it as early as we can, and run other stuff in a different task group.
    if anonymous_uid found, push the cme anonymous user progress to the legacy user.
    :param email:
    :param user_uid:
    :param session:
    :param anonymous_uid
    :return:
    """
    user = User.get_user_by_email(email=email, session=session, raise_exception=True)
    if user.user_uid:
        raise UserError(msg=f'User {email} already has a uid set',
                        return_code='409')
    user.user_uid = user_uid
    session.add(user)
    session.commit()
    if anonymous_uid:
        try:
            link_existing_anonymous_user(anonymous_uid=anonymous_uid, user_uid=user_uid, session=session)
        except UserError:
            logger.error("unable to link anonymous user, nothing to do")
    UserEvents.USER_UID_SET(user_uuid=user.user_uuid, user_uid=user_uid, session=session, wait=True)

    user_detail = UserDocument.user_detail(user_uuid=user.user_uuid, session=session)

    return {
        'onboardingState': user_detail['onboardingState'],
        'firstName': user_detail['firstName'],
        'lastName': user_detail['lastName'],
        'primarySpecialty': user_detail['primarySpecialty'],
    }


@managed_session
def rewrite_user_metadata(user_uid=None, user_type=None, username=None, session=None):
    if user_uid:
        write_feed_metadata_task.delay(user_uid=user_uid)
    if username:
        u = User.get_user_by_username(username=username, session=session, raise_exception=True)
        if u.user_uid:
            write_feed_metadata_task.delay(user_uid=u.user_uid)
        else:
            raise UserNotFound
    if user_type and isinstance(user_type, str):
        task = None
        if user_type.upper() in UserTypes.__members__:
            logger.info("Usertype %s processing", user_type)
            for u in session.query(User) \
                    .filter(User.user_type == user_type.upper(),
                            User.deleted_at.is_(None),
                            User.onboarding_interests_completed.is_(True),
                            User.user_uid.isnot(None)) \
                    .all():
                if not task:
                    task = write_feed_metadata_task.si(user_uid=u.user_uid)
                else:
                    task.link(write_feed_metadata_task.si(user_uid=u.user_uid))
        if task:
            task.apply_async()


@managed_session
def refresh_user_saved_cases(user_uuid, session):
    UserEvents.USER_SAVED_CASE_SYNC(user_uuid=user_uuid, session=session)


@managed_session
def sync_elasticsearch(user_uuid=None, session=None):
    elasticsearch_user_detail = UserDocument.elasticsearch_user_detail(user_uuid=user_uuid, session=session)
    add_or_update_user(user_uuid=user_uuid, user_detail=elasticsearch_user_detail)


@managed_session
def get_user_group_filter_by_uuid(group_filter_uuid, session=None):
    return GroupMemberFilter.get_by_uuid(session, group_filter_uuid)


@managed_session
def get_user_potential_group(email, group_uuid, session=None):
    potential_group = session.query(Groups) \
        .filter(Groups.group_uuid == group_uuid) \
        .join(GroupMemberFilter, GroupMemberFilter.group_uuid == Groups.group_uuid) \
        .where(GroupMemberFilter.user_email == email).one_or_none()
    if not potential_group:
        raise UserIsNotInvited(msg=f"the email: {email} is not invited to group: {group_uuid} .", return_code=400)

    return GroupModel.from_orm(potential_group).dict(exclude={"groupMembers"})
