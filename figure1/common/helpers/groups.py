import logging
import uuid
from typing import Optional, List
from pydantic import ValidationError
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from .word_filter import WordMatcher
from .case_management import CaseManagement
from .user import UserDocument
from figure1.common.models.db import Groups, \
    GroupMember, \
    GroupMemberFilter, \
    GroupFeedDescriptor, \
    FeedKind, \
    FeedType, \
    User, \
    Case
from figure1.common.types import GroupMemberModel, \
    GroupModel, \
    Locale, \
    CaseState
from figure1.common.types.groups import GroupTypes
from figure1.common.types.elasticsearch import GroupIndex
from figure1.exceptions import GroupException
from figure1.exceptions.user import GroupMemberNotFound

logger = logging.getLogger('database.groups')


class GroupManagement:
    """
    Class for managing groups
    """

    @staticmethod
    def refresh_all_elasticsearch_groups(session):
        for group in session.query(Groups.group_uuid).all():
            GroupManagement._group_updated(group_uuid=group[0], session=session)

    @staticmethod
    def _group_updated(group_uuid, session, if_expire_all=False):
        if if_expire_all:
            session.expire_all()
        group_created_at = session.query(Groups.created_at).filter(Groups.group_uuid == group_uuid).first()[0]
        group_model = GroupManagement.get_group(group_uuid=group_uuid, session=session)
        GroupManagement._update_elasticsearch(group_uuid=group_uuid,
                                              group_model=group_model,
                                              group_created_at=group_created_at)

        return group_model

    @staticmethod
    def _update_elasticsearch(group_uuid, group_model, group_created_at):
        group_idx: GroupIndex = GroupIndex.get(id=group_uuid, ignore=404)
        if not group_idx:
            group_idx = GroupIndex()
        if isinstance(group_model, GroupModel):
            group_model_dict = group_model.dict(exclude={'groupFilters': {'__all__': {'groupFilterUuid'}},
                                                         'groupMembers': {'__all__': {'user'}}})
            group_idx.groupDescription = group_model_dict.get('groupDescription')
            group_idx.groupUuid = group_model_dict.get('groupUuid')
            group_idx.groupName = group_model_dict.get('groupName')
            group_idx.groupType = group_model_dict.get('groupType')
            group_idx.groupActiveMemberCount = len(group_model_dict.get('groupMembers'))
            group_idx.groupMemberFilters = group_model_dict.get('groupFilters')
            group_idx.groupCreator = group_model_dict.get('groupCreator')
            group_idx.groupActive = group_model_dict.get('groupActive')
            group_idx.groupAvatar = group_model_dict.get('groupAvatar')
            if isinstance(group_created_at, datetime):
                group_idx.groupCreatedAt = group_created_at
            group_idx.save()

    @staticmethod
    def force_group_update(group_uuid, session):
        GroupManagement._group_updated(group_uuid=group_uuid, session=session)

    @staticmethod
    def create_group(group_name, group_label, group_type, session, **kwargs) -> GroupModel:
        """
        Add a new group.
        There are no checks.

        :param group_name: Required for a new group, this is displayed
        :param group_label: Required for a new group, this is used for sorting/searching
        :param group_type: Required for a new group
        :param session: Database session
        :param kwargs: Optional arguments to set, can be group_description or group_active or group_creator_uuid
        :raise: GroupException
        :return: GroupModel
        """
        group = Groups()
        group.group_uuid = uuid.uuid4()

        if isinstance(group_name, str):
            group.group_name = group_name
        else:
            raise GroupException(msg="Group name must be a string", return_code=406)

        WordMatcher.find_blocked_word_in_string(group_name)

        if isinstance(group_label, str):
            group.group_label = group_label
        else:
            raise GroupException(msg="Group label must be a string", return_code=406)

        if isinstance(group_type, GroupTypes):
            group.group_type = group_type
        else:
            raise GroupException(msg="Group type must be a GroupTypes instance", return_code=406)

        group.group_active = False
        for k, v in kwargs.items():
            if k == 'group_active' and isinstance(v, bool):
                setattr(group, k, v)
            elif k == 'group_description' and isinstance(v, str):
                setattr(group, k, v)
            elif k == 'group_creator_uuid' and isinstance(v, str):
                setattr(group, k, v)
            else:
                if hasattr(group, k):
                    setattr(group, k, v)
                else:
                    logger.error("Group instance has no attribute %s", k)
        session.add(group)
        session.flush()
        GroupManagement._create_group_feed(group=group, session=session)
        if kwargs.get('group_creator_uuid'):
            GroupManagement.add_user_to_group(user_uuid=kwargs.get('group_creator_uuid'),
                                              group_uuid=group.group_uuid,
                                              session=session)
        return GroupManagement._group_updated(group.group_uuid, session=session)

    @staticmethod
    def delete_group(group_uuid, session) -> None:
        """
        In order to delete an institutional group, all members and cases must first be removed.  An exception is raised
        otherwise.

        For other group types, members are removed and cases are marked as deleted.

        The associated FeedType and GroupFeedDescriptor are also deleted.

        :param group_uuid: Group identifier
        :param session: Database session
        :raise: GroupException
        :return: None
        """
        case_query = session.query(Case).filter(Case.group_uuid == group_uuid)
        group = GroupManagement.get_group(group_uuid=group_uuid, session=session)
        group_idx = GroupIndex.get(str(group_uuid))
        if not group:
            raise GroupException(msg="Group not found", return_code=404)
        if group.groupType == GroupTypes.INSTITUTIONAL.name.lower():
            if group.groupMembers:
                raise GroupException(msg="Institutional group has members, cannot delete", return_code=406)
            elif case_query.count():
                raise GroupException(msg="Institutional group has cases, cannot delete", return_code=406)
        else:
            cases = []
            for case in case_query.all():
                CaseManagement.delete_case(case_uuid=case.case_uuid, session=session, destructive=False)
                case.group_uuid = None
                cases.append(case)
            session.add_all(cases)
            session.query(GroupMember).filter(GroupMember.group_uuid == group_uuid).delete()
        group_idx.delete()

        session.query(GroupMemberFilter).filter(GroupMemberFilter.group_uuid == group_uuid).delete()
        session.flush()
        for gf in session.query(GroupFeedDescriptor).filter(GroupFeedDescriptor.group_uuid == group_uuid).all():
            session.query(FeedType).filter(FeedType.feed_type_uuid == gf.feed_type_uuid).delete()
        session.query(GroupFeedDescriptor).filter(GroupFeedDescriptor.group_uuid == group_uuid).delete()
        session.query(Groups).filter(Groups.group_uuid == group_uuid).delete()
        session.flush()

    @staticmethod
    def modify_group(group_uuid, session, **kwargs) -> Optional[GroupModel]:
        """
        Modifies parameters of a group, does not add or remove users.

        :param group_uuid: Uuid of group to modify
        :param session: Database session to use when modifying
        :param kwargs: Any column name in the Groups database model, group_name, group_label, group_description,
            group_active. Note that the types must match, for example group_active is a boolean value, so if the value
             is passed in, only a True or False is valid. Any fields not passed in are not modified
        :return: GroupModel
        """
        if 'group_name' in kwargs:
            WordMatcher.find_blocked_word_in_string(word_string=kwargs.get('group_name'))
        if 'group_description' in kwargs:
            WordMatcher.find_blocked_word_in_string(word_string=kwargs.get('group_description'))

        group = session.query(Groups).filter(Groups.group_uuid == group_uuid).one_or_none()
        if group:
            for k, v in kwargs.items():
                if k == 'group_uuid' or k == 'group_creator_uuid':
                    continue
                if hasattr(group, k):
                    setattr(group, k, v)

            session.add(group)
        session.flush()
        return GroupManagement._group_updated(group_uuid, session=session)

    @staticmethod
    def get_group(group_uuid, session) -> Optional[GroupModel]:
        """
        Returns a model populated with the group metadata and a list of members or None if no group is  found

        :param group_uuid: Group identifier
        :param session: Database session
        :return: GroupModel
        """
        g = Groups.get_group_by_uuid(group_uuid, session)
        if not g:
            return None

        return GroupModel.from_orm(g)

    @staticmethod
    def get_all_groups(session) -> List[GroupModel]:
        """
        Yields list of populated group models, any that fail validation are skipped
        :param session:
        :return:
        """
        for group in Groups.get_all_groups(session=session):
            try:
                yield GroupModel.from_orm(group)
            except ValidationError as v:
                logger.exception("Caught validation error, %s", v)

    @staticmethod
    def get_all_groups_as_dict(session) -> List[dict]:
        """
        Get a list of all group dict

        :param session: Database session
        """
        for group in GroupManagement.get_all_groups(session=session):
            yield group.dict()

    @staticmethod
    def get_group_members_as_dict(group_uuid, session) -> List[dict]:
        """
        Get a list of group member dict

        :param group_uuid: Group uuid
        :param session: Database session
        :raise: GroupUUIDNotFound
        """
        members = Groups.get_members_by_group_uuid(group_uuid, session)
        return [GroupMemberModel.from_orm(each).dict() for each in members]

    @staticmethod
    def get_group_member_by_user_uuid_as_dict(group_uuid, user_uuid, session) -> dict:
        """
        Get a group member dict

        :param group_uuid: Group uuid
        :param user_uuid: User uuid
        :param session: Database session
        :raise: GroupMemberNotFound
        """
        group_member = session.query(GroupMember) \
            .filter(GroupMember.group_uuid == group_uuid,
                    GroupMember.user_uuid == user_uuid) \
            .one_or_none()
        if not group_member:
            raise GroupMemberNotFound

        is_creator = GroupMemberModel.from_orm(group_member).dict().get('isCreator') or False
        user_data = UserDocument.get_compact_user_data(user_uuid=user_uuid, session=session, use_cache=False)
        user_data.update({'isCreator': is_creator})

        return user_data

    @staticmethod
    def get_cases_by_group_as_dict(group_uuid, session) -> List[dict]:
        """
        Get a list of group case dict

        :param group_uuid: Group uuid
        :param session: Database session
        :raise: GroupUUIDNotFound
        """
        cases = Groups.get_group_cases_by_group_uuid(group_uuid, session)
        return [each.as_dict() for each in cases]

    @staticmethod
    def get_groups_by_user_as_dict(user_uuid, session) -> List[dict]:
        """
        Get a list of group dict given user

        :param user_uuid: User uuid
        :param session: Database session
        :raise: UserUUIDNotFound
        """
        user = User.get_user_by_uuid(user_uuid, session)
        return [GroupModel.from_orm(each.group).dict() for each in user.user_groups]

    @staticmethod
    def add_user_to_group(user_uuid, group_uuid, session):
        """
        Add a user to a group

        :param user_uuid: User uuid to add to a group
        :param group_uuid: Group to add the user_uuid too
        :param session: Database session
        :raise: GroupException
        """
        if session.query(Groups).get(group_uuid):
            group_member = GroupMember()
            group_member.group_uuid = group_uuid
            group_member.user_uuid = user_uuid
            session.add(group_member)
            session.flush()
        else:
            raise GroupException("Group uuid not found")
        return GroupManagement._group_updated(group_uuid, session=session, if_expire_all=True)

    @staticmethod
    def invite_user_to_group(email: str,
                             group_uuid: str,
                             session: Session,
                             user_uuid: Optional[str] = None,
                             first_name: Optional[str] = None,
                             last_name: Optional[str] = None,
                             npi_number: Optional[str] = None,
                             tree_uuid: Optional[str] = None,
                             country_uuid: Optional[str] = None,
                             inviter_uuid: Optional[str] = None):
        gmf = session.query(GroupMemberFilter) \
            .filter(GroupMemberFilter.user_email == email, GroupMemberFilter.group_uuid == group_uuid) \
            .first()
        if gmf:
            logger.debug("User %s has already been invited to group %s", email, group_uuid)
            return gmf

        group_member_filter = GroupMemberFilter()
        group_member_filter.group_filter_uuid = uuid.uuid4()
        group_member_filter.group_uuid = group_uuid
        group_member_filter.user_email = email
        group_member_filter.user_uuid = user_uuid

        if first_name:
            group_member_filter.user_first_name = first_name
        if last_name:
            group_member_filter.user_last_name = last_name
        if npi_number:
            group_member_filter.user_npi = npi_number
        if tree_uuid:
            group_member_filter.tree_uuid = tree_uuid
        if country_uuid:
            group_member_filter.country_uuid = country_uuid
        if inviter_uuid:
            group_member_filter.inviter_uuid = inviter_uuid

        session.add(group_member_filter)
        session.flush()
        GroupManagement._group_updated(group_uuid, session=session)
        return group_member_filter

    @staticmethod
    def remove_user_from_group(user_uuid, group_uuid, session):
        """
        Remove this user from this group

        :param user_uuid: User uuid to add to a group
        :param group_uuid: Group to add the user_uuid too
        :param session: Database session
        """

        session.query(GroupMember) \
            .filter(GroupMember.user_uuid == user_uuid,
                    GroupMember.group_uuid == group_uuid).delete()

        session.flush()
        GroupManagement._group_updated(group_uuid, session=session, if_expire_all=True)

    @staticmethod
    def check_user_group_filter(npi=None, first_name=None, last_name=None, email=None):
        pass

    @staticmethod
    def _create_group_feed(group: Groups, session: Session) -> GroupFeedDescriptor:
        """
        Creates a feed that filters for cases in the group.  This creates a FeedType and GroupFeedDescriptor.

        :param group: The group that the feed should filter for
        :param session: Database session
        :return: GroupFeedDescriptor
        """

        ft = FeedType.create(kind=FeedKind.GROUP,
                             name=group.group_name,
                             label=group.group_label,
                             session=session)

        gf = GroupFeedDescriptor()
        gf.feed_type_uuid = ft.feed_type_uuid
        gf.group_uuid = group.group_uuid
        gf.name = group.group_name
        gf.label = group.group_label
        gf.hidden = True
        gf.state_filter = CaseState.APPROVED.name
        gf.display_order = 1000
        gf.language = Locale.EN_US.code
        gf.filter_query = {
            "term": {
                "groupUuid": str(group.group_uuid)
            }
        }
        gf.expire_query = {}
        gf.sort_fields = []

        return session.merge(gf)
