import logging
from datetime import datetime, timezone
from elasticsearch_dsl import Document, Keyword, Text, Boolean, Long, Date, InnerDoc, Object, Nested

logger = logging.getLogger('figure1.pro.group_index')


class GroupMemberFilters(InnerDoc):
    userFirstName = Text()
    userLastName = Text()
    userEmail = Text()
    userNpi = Long()
    userUuid = Keyword()


class GroupMemberObject(InnerDoc):
    userUuid = Keyword()
    isCreator = Boolean()


class GroupCreatorObject(InnerDoc):
    userUuid = Keyword()
    userUid = Keyword()
    userEmail = Text()


class GroupIndex(Document):
    groupUuid = Keyword(required=True)
    groupName = Text()
    groupDescription = Text()
    groupActive = Boolean()
    groupCaseCount = Long()
    groupActiveMemberCount = Long()
    groupCreator = Object(GroupCreatorObject)
    groupCreatedAt = Date()
    groupUpdatedAt = Date()
    groupMemberFilters = Object(GroupMemberFilters)
    groupMembers = Object(GroupMemberObject)
    groupType = Keyword()
    groupAvatar = Text()

    def save(
            self,
            **kwargs
    ):
        self.meta.id = self.groupUuid
        self.groupUpdatedAt = datetime.now(tz=timezone.utc)
        return super().save(**kwargs)


def update_group(group_uuid,
                 group_member_count=None,
                 group_case_count=None,
                 group_description=None,
                 group_name=None):
    """
    Requires a group uuid - all other fields are optional. Call this to update an existing document

    :param group_uuid: Required - uuid of the group
    :type group_uuid: str

    :param group_member_count: Optional - Number of Active members in a group
    :type group_member_count: int

    :param group_case_count: Optional - Number of cases in a group
    :type group_case_count: int

    :param group_description: Optional - Update a group description
    :type group_description: str

    :param group_name: Optional - Update a group name
    :type group_name: str
    :return:
    """
    gi = GroupIndex.get(group_uuid)
    if gi is None:
        gi = GroupIndex(group_uuid=group_uuid)
        gi.save()

    update_keys = {}
    if group_member_count is not None:
        try:
            int(group_member_count)
        except ValueError:
            logger.error("Invalid group member count %s", group_member_count)
        else:
            update_keys.update({'groupActiveMemberCount': group_member_count})
    if group_case_count is not None:
        try:
            int(group_case_count)
        except ValueError:
            logger.error("Invalid group case count %s", group_case_count)
        else:
            update_keys.update({'groupCaseCount': group_case_count})
    if group_description is not None:
        update_keys.update({'groupDescription': group_description})
    if group_name is not None:
        update_keys.update({'groupName': group_name})
    if update_keys:
        gi.update(**update_keys)
