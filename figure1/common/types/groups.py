import enum
from typing import List, Optional
from pydantic import BaseModel, validator, Field, HttpUrl, constr, root_validator

from .user_types import BaseUserModel


class GroupTypes(enum.Enum):
    INSTITUTIONAL = 'institutional'
    USER = 'user'


class GroupMemberModel(BaseModel):
    """
    Model for one group member, should be used as part of GroupModel
    """
    userUuid: str = Field(alias='user_uuid')
    user: BaseUserModel
    isCreator: bool = Field(alias='is_creator', default=False)

    @validator('userUuid', pre=True)
    def stringify(cls, value):
        return str(value) if value else None

    class Config:
        orm_mode = True


class GroupCreatorModel(BaseModel):
    """
    Model for the group creator, should be used as part of GroupModel
    """
    userUuid: str = Field(alias='user_uuid')
    userUid: Optional[str] = Field(alias='user_uid')
    userEmail: str = Field(alias='email')

    @validator('userUuid', pre=True)
    def stringify(cls, value):
        return str(value) if value else None

    class Config:
        orm_mode = True


class GroupModel(BaseModel):
    """
    Description of a given group. groupMembers is a list of users in this group.
    """
    groupUuid: str = Field(alias='group_uuid')
    groupName: str = Field(alias='group_name')
    groupLabel: str = Field(alias='group_label')
    groupDescription: Optional[str] = Field(alias='group_description')
    groupActive: bool = Field(alias='group_active')
    groupAvatar: Optional[HttpUrl] = Field(alias='group_avatar')
    groupMembers: List[GroupMemberModel] = Field(alias='members')
    groupFilters: Optional[List['GroupFilterModel']] = Field(alias='group_member_filter')
    groupType: Optional[GroupTypes] = Field(alias='group_type')
    feedTypeUuid: Optional[str] = Field(alias='group_feed')
    groupCreatorUuid: Optional[str] = Field(alias='group_creator_uuid')
    groupCreator: Optional[GroupCreatorModel] = Field(alias='creator')
    isPublicGroup: Optional[bool] = Field(alias='is_public')
    membersCount: int = 0

    @validator('groupUuid', 'groupCreatorUuid', pre=True)
    def stringify(cls, value):
        return str(value) if value else None

    @validator('feedTypeUuid', pre=True)
    def parse_feed_type(cls, value):
        return str(value[0].feed_type_uuid) if value else None

    @root_validator(pre=True)
    def handle_properties(cls, values):
        values = dict(values)
        if isinstance(values['members'], list):
            values['membersCount'] = sum((1 for each in values['members'] if not each.user.hidden_from_search))
        return values

    class Config:
        use_enum_values = True
        orm_mode = True


class GroupFilterModel(BaseModel):
    groupFilterUuid: str = Field(alias='group_filter_uuid')
    userFirstName: Optional[str] = Field(alias='user_first_name')
    userLastName: Optional[str] = Field(alias='user_last_name')
    userEmail: Optional[str] = Field(alias='user_email')
    userNpi: Optional[int] = Field(alias='user_npi')
    userUuid: Optional[str] = Field(alias='user_uuid')

    @validator('userUuid', 'groupFilterUuid', pre=True)
    def stringify(cls, value):
        return str(value) if value else None

    class Config:
        orm_mode = True


class GroupUploadModel(BaseModel):
    group_name: constr(max_length=1000)
    group_label: constr(max_length=1000)
    group_type: GroupTypes = GroupTypes.USER
    group_creator_uuid: str
    group_description: Optional[constr(max_length=10000)]
    group_active: Optional[bool]
    is_public_group: Optional[bool] = False


class GroupUpdateModel(GroupUploadModel):
    group_name: Optional[constr(max_length=1000)]
    group_label: Optional[constr(max_length=1000)]
    group_creator_uuid: Optional[str]


GroupModel.update_forward_refs()
