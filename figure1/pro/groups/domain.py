import csv
import logging
import os

from celery.canvas import Signature
from celery.canvas import group
from pydantic import EmailError
from pydantic import validate_email

from figure1.common.firebase import do_firebase_sync
from figure1.common.helpers import GroupManagement
from figure1.common.helpers import CaseManagement
from figure1.common.iterable import IterableAPI
from figure1.common.iterable import delete_iterable_users
from figure1.common.mixpanel import update_mixpanel_user
from figure1.common.models.db import User
from figure1.common.models.db import GroupMember
from figure1.common.models.db import Groups
from figure1.common.models.db import Case
from figure1.common.models.db import GroupMemberFilter
from figure1.common.models.firebase.groups_db import sync_single_group_task
from figure1.common.models.firebase.groups_db import sync_single_group_member_task
from figure1.common.models.firebase.groups_db import delete_single_group_member_task
from figure1.common.models.firebase.groups_db import delete_single_group_task
from figure1.common.slack_client import SlackClient
from figure1.common.slack_client import SlackColour
from figure1.common.slack_client import SlackIcon
from figure1.notifications import notify_group_invite_accepted_task
from figure1.notifications import notify_user_of_group_invite_task
from figure1.common.types.groups import GroupTypes
from figure1.common.types.groups import GroupUploadModel
from figure1.common.utils import validate_npi
from figure1.configuration import app_settings
from figure1.core import managed_session
from figure1.exceptions import GroupException
from figure1.exceptions import IterableException
from figure1.exceptions.case import FailedToCloneCaseToGroup
from figure1.exceptions.user import GroupUUIDNotFound
from figure1.exceptions.user import InvalidGroupMembersFile
from figure1.exceptions.user import GroupInactive
from figure1.exceptions.user import DuplicateGroupName

logger = logging.getLogger(__name__)


def _get_sync_user_task(user_uuid: str) -> Signature:
    return group(do_firebase_sync.si(firebasemodel='FirebaseUsersDB', uuid=user_uuid, merge=False),
                 update_mixpanel_user.si(user_uuid=user_uuid))


def _send_pending_user_invite_emails(members):
    sent_emails, unsent_emails, errors = [], [], []
    iterable_profiles_to_delete = []
    campaign_id = app_settings.iterable_invite_group_members_campaign_id
    iterable_client = IterableAPI()

    if not campaign_id:
        logger.error("Iterable campaign id dose not exist, nothing to do")
        return None, None, ["Iterable campaign id does not exist, nothing to do"]

    if iterable_client.iterable_api_disabled:
        logger.error("Iterable api is disabled, nothing to do")
        return None, None, ["Iterable api is disabled, nothing to do"]

    for each_member in members:
        email, group_filter_uuid = each_member["email"], each_member["group_filter_uuid"]
        # we don't create group_filter for our existing users.
        # we don't send email to our existing users.
        if not group_filter_uuid:
            logger.error(f"Should not send email to this existing user: {email}")
            continue

        data_fields = {
            "inviteeEmail": email,
            "groupFilterUuid": str(group_filter_uuid),
            "groupName": each_member["group_name"]
        }
        try:
            validated_email = validate_email(email)
            iterable_client.trigger_campaign(campaign_id=campaign_id,
                                             recipient_email=validated_email[1],
                                             data_fields=data_fields)
            sent_emails.append(validated_email[1])
        except EmailError:
            unsent_emails.append(email)
            error_msg = f"Email is incorrect {email}"
            logger.exception(error_msg)
            errors.append(error_msg)
        except IterableException:
            unsent_emails.append(email)
            error_msg = f"Encountered an error while triggering the campaign for email: {email}"
            logger.exception(error_msg)
            errors.append(error_msg)

        iterable_profiles_to_delete.append(email)

    task = delete_iterable_users.si(emails=iterable_profiles_to_delete)
    task.apply_async(countdown=10)

    return sent_emails, unsent_emails, errors


def _handle_group_member_line(data_line, session):
    npi_number = data_line.pop(0)
    first_name = data_line.pop(0)
    last_name = data_line.pop(0)
    email_address = data_line.pop(0)
    group_uuid = data_line.pop(0)
    tree_uuid = data_line.pop(0)
    country_uuid = data_line.pop(0)

    email_address = email_address.strip()
    group = Groups.get_group_by_uuid(group_uuid=group_uuid, session=session)
    if not group:
        return None, f"Group {group_uuid} is not found."

    if npi_number:
        if not validate_npi(npi_number):
            return None, f"Invalid npi number {npi_number}."

    group_member_filter = session.query(GroupMemberFilter) \
        .filter(GroupMemberFilter.user_email == email_address,
                GroupMemberFilter.group_uuid == group_uuid) \
        .all()
    if group_member_filter:
        return None, f"The group member filter already exists for group_uuid {group_uuid} and email {email_address}."

    user = User.get_user_by_email(email=email_address, session=session, raise_exception=False)
    group_filter = None
    if user:
        user_uuid = user.user_uuid
        add_members_to_group(group_uuid, [user_uuid])
    else:
        group_filter = GroupManagement.invite_user_to_group(session=session,
                                                            email=email_address,
                                                            group_uuid=group_uuid,
                                                            first_name=first_name,
                                                            last_name=last_name,
                                                            npi_number=npi_number,
                                                            tree_uuid=tree_uuid,
                                                            country_uuid=country_uuid)

    return {"email": email_address,
            "group_filter_uuid": group_filter.group_filter_uuid if group_filter else "",
            "group_name": group.group_name}, None


@managed_session
def _check_group_name(group_name, session=None):
    if session.query(Groups).filter(Groups.group_name == group_name).one_or_none():
        raise DuplicateGroupName(group_name=group_name)


@managed_session
def create_users_group(data: GroupUploadModel, session=None):
    _check_group_name(data.group_name, session=session)
    creator = User.get_user_by_uuid(user_uuid=data.group_creator_uuid, raise_exception=True, session=session)
    group_args = {
        "group_description": data.group_description,
        "group_name": data.group_name,
        "group_label": data.group_label,
        "group_active": data.group_active,
        "group_type": data.group_type,
        "group_creator_uuid": data.group_creator_uuid,
        "is_public": data.is_public_group,
    }

    group_model = GroupManagement.create_group(session=session, **group_args)

    task = sync_single_group_task.si(group_model.groupUuid)
    if creator:
        if not creator.hidden_from_search:
            task.link(sync_single_group_member_task.si(group_model.groupUuid, creator.user_uuid))
        task.link(_get_sync_user_task(user_uuid=creator.user_uuid))
    if group_args.get('group_type') == GroupTypes.USER:
        if data.is_public_group is True:
            m = "A new public group has been created for moderation"
        else:
            m = "A new group has been created for moderation"
        SlackClient().send_message(message=m,
                                   colour=SlackColour.GREEN,
                                   icon=SlackIcon.ROCKET,
                                   channel=app_settings.slack_channel_group_moderation_notifications,
                                   entity=group_model)

    return {"group": group_model.dict(), "task": task}


@managed_session
def admin_update_group(group_uuid, update: GroupUploadModel, session=None):
    group_model_data = GroupManagement.modify_group(group_uuid=group_uuid,
                                                    **update.dict(exclude_none=True),
                                                    session=session)
    task = sync_single_group_task.si(group_uuid)
    return {'group': group_model_data, 'task': task}


@managed_session
def delete_users_group(group_uuid, session=None):
    GroupManagement.delete_group(session=session, group_uuid=group_uuid)
    task = delete_single_group_task.si(group_uuid=group_uuid)
    return {'success': "group has been deleted", "task": task}


@managed_session
def add_members_to_group(group_uuid, users_uuid, session=None):
    """
    add users to a group

    :param users_uuid: list of users uuid to add to a group
    :param group_uuid: Group uuid
    :param session:
    """
    if not isinstance(users_uuid, list):
        raise TypeError('users_uuid must be a list of strings')

    group_exists = GroupManagement.get_group(group_uuid=group_uuid, session=session)

    if group_exists:
        task = None
        for user_uuid in users_uuid:
            # check if member already exists
            member_exists = session.query(GroupMember).filter(GroupMember.group_uuid == group_uuid,
                                                              GroupMember.user_uuid == user_uuid).one_or_none()
            if not member_exists:

                user = User.get_user_by_uuid(user_uuid=user_uuid, session=session, raise_exception=False)
                if user:
                    GroupManagement.add_user_to_group(user_uuid=user.user_uuid, group_uuid=group_uuid,
                                                      session=session)
                    if not task:
                        task = _get_sync_user_task(user_uuid=user_uuid)
                    else:
                        task.link(_get_sync_user_task(user_uuid=user_uuid))

                    task.link(notify_group_invite_accepted_task.si(group_uuid=group_uuid, user_uuid=user_uuid))
                    if not user.hidden_from_search:
                        task.link(sync_single_group_member_task.si(group_uuid, user_uuid))
        session.flush()
    else:
        raise GroupException("group does not exist", return_code=404)

    return {'task': task}


@managed_session
def remove_members_from_group(group_uuid, users_uuid, session=None):
    """
    remove user from a group

    :param users_uuid: list of users uuid to remove from a group
    :param group_uuid: group uuid
    :param session:
    """
    group = GroupManagement.get_group(group_uuid=group_uuid, session=session)
    if group:
        task = None
        for user_uuid in users_uuid:
            GroupManagement.remove_user_from_group(user_uuid=user_uuid, group_uuid=group_uuid,
                                                   session=session)
            if not task:
                task = _get_sync_user_task(user_uuid=user_uuid)
            else:
                task.link(_get_sync_user_task(user_uuid=user_uuid))

            task.link(delete_single_group_member_task.si(group_uuid=group_uuid, user_uuid=user_uuid))
        session.flush()
    else:
        raise GroupException("group does not exist", return_code=404)

    return {'task': task}


@managed_session
def invite_members_to_group(user_uid, group_uuid, users_uuid, session=None):
    """
    invite users to a group

    :param user_uid: user who initiated the invite
    :param users_uuid: list of users uuid to invite to a group
    :param group_uuid: group uuid
    :param session:
    """
    if not isinstance(users_uuid, list):
        raise TypeError('users_uuid must be a list of strings')

    inviter = User.get_user_by_uid(user_uid=user_uid, session=session, raise_exception=True)
    group = GroupManagement.get_group(group_uuid=group_uuid, session=session)

    if not group:
        raise GroupException("group does not exist", return_code=404)
    elif not group.groupActive:
        raise GroupInactive()

    task = None
    for user_uuid in users_uuid:
        member_exists = session.query(GroupMember).filter(GroupMember.group_uuid == group_uuid,
                                                          GroupMember.user_uuid == user_uuid).one_or_none()
        if not member_exists:
            user = User.get_user_by_uuid(user_uuid=user_uuid, session=session, raise_exception=False)
            if user:
                gmf = GroupManagement.invite_user_to_group(session=session,
                                                           email=user.email,
                                                           user_uuid=user.user_uuid,
                                                           group_uuid=group_uuid,
                                                           inviter_uuid=inviter.user_uuid)
                if not task:
                    task = notify_user_of_group_invite_task.si(group_filter_uuid=gmf.group_filter_uuid)
                else:
                    task.link(notify_user_of_group_invite_task.si(group_filter_uuid=gmf.group_filter_uuid))
    session.flush()
    return {'task': task}


@managed_session
def get_groups_by_user_uuid(user_uuid, session=None):
    """
    get groups by user

    :param user_uuid: user_uuid
    :param session
    """
    return GroupManagement.get_groups_by_user_as_dict(user_uuid, session)


@managed_session
def get_groups(session=None):
    """
    get groups
    :param session
    """
    return list(GroupManagement.get_all_groups_as_dict(session))


@managed_session
def get_members_by_group_uuid(group_uuid, session=None):
    """
    get group members

    :param group_uuid: group_uuid
    :param session
    """
    return GroupManagement.get_group_members_as_dict(group_uuid, session)


@managed_session
def get_cases_by_group_uuid(group_uuid, session=None):
    """
    get group cases

    :param group_uuid: group_uuid
    :param session
    """
    return GroupManagement.get_cases_by_group_as_dict(group_uuid, session)


@managed_session
def add_case_to_group(group_uuid, case_uuid, session=None):
    """
    add a case to a group

    :param group_uuid: group_uuid
    :param case_uuid: case_uuid
    :param session
    """
    group = Groups.get_group_by_uuid(group_uuid, session)
    case = Case.get_case(case_uuid, raise_exception=True, session=session)

    if not group:
        raise GroupUUIDNotFound(msg="Group does not exist")

    try:
        case.clone(session, group_uuid=group_uuid)
    except Exception:
        raise FailedToCloneCaseToGroup(msg=f"Failed to clone case to group: {group_uuid}.", return_code=500)


@managed_session
def remove_case_from_group(group_uuid, case_uuid, session=None):
    """
    Remove a case from a group

    :param group_uuid: group_uuid
    :param case_uuid: case_uuid
    :param session
    """
    group = Groups.get_group_by_uuid(group_uuid, session)
    case = Case.get_case(case_uuid, raise_exception=True, session=session)

    if not group:
        raise GroupUUIDNotFound(msg="group does not exist")

    if group.group_uuid != case.group_uuid:
        raise GroupException(f"the case: {case.case_uuid} does not belong to group: {group.group_uuid}",
                             return_code=406)

    case.group_uuid = None
    CaseManagement.delete_case(case_uuid=case_uuid, session=session, destructive=False)


@managed_session
def update_groups_avatar_internal(group_uuid, url, session=None):
    return GroupManagement.modify_group(group_uuid=group_uuid, session=session, group_avatar=url)


@managed_session
def import_group_members(filename, session=None):
    """
    Imports a list of groups members from a csv file
    """
    count, errors = 0, []
    members = []
    if not os.path.isfile(filename):
        raise InvalidGroupMembersFile(msg=f"Filename {filename} is not a file.")

    with open(filename, mode='r', newline='') as fn:
        reader = csv.reader(fn)
        for line in reader:
            member_dict, error = _handle_group_member_line(data_line=line, session=session)
            if member_dict:
                members.append(member_dict)
                count += 1
            if error:
                errors.append(error)

    sent_emails, unsent_emails, invite_errors = _send_pending_user_invite_emails(members)

    return {
        "ImportUpdatedCount": count,
        "ImportErrorCount": len(errors),
        "ImportErrors": errors,
        "SentEmails": sent_emails,
        "UnsentEmails": unsent_emails,
        "InviteEmailErrors": invite_errors
    }
