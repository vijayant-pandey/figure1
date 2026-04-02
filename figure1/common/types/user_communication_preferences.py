import enum
from typing import Optional, List
from pydantic import BaseModel, Field, validator


class CommunicationMethods(enum.Enum):
    """
    The channel method may encompass more than one method. It doesn't really mean anything in this context
    """
    EMAIL = 'email'
    PUSH = 'push'
    SMS = 'sms'
    CHANNEL = 'channel'


class CommunicationTypes(enum.Enum):
    """
    Communication Types are the top level of the settings, they loosely categorize settings.
    """
    ACTIVITY = 'activity'
    CONTENT = 'content'
    TRANSACTIONAL = 'transactional'
    CHANNEL = 'channel'


class ActivityNotificationCategories(enum.Enum):
    CommentsRepliesLikes = 'commentsreplieslikes'
    Paging = 'paging'
    Follow = 'follow'
    SavedCases = 'savedcases'
    WeeklyDigest = 'weeklydigest'


class internalCommunicationSettingsModel(BaseModel):
    """
    This model is only used internally, it represents a single communication item. This is surfaced either through
    groups for defaults, or through the user communication preference model.

    """
    communicationUuid: str = Field(alias='communication_uuid')
    communicationMethod: CommunicationMethods = Field(alias='communication_method')
    communicationEnabled: bool = Field(alias='communication_enabled')
    communicationDefaultSetting: bool = Field(alias='communication_default_setting')
    communicationSetting: bool = Field(alias='communication_default_setting')
    communicationName: str = Field(alias='communication_name')
    communicationDescription: str = Field(alias='communication_description')
    communicationIterableMessageType: str = Field(alias='communication_iterable_message_type')
    communicationDisplayOrder: int = Field(alias='communication_display_order', default=0)

    class Config:
        orm_mode = True
        use_enum_values = True

    @validator('communicationUuid', pre=True)
    def stringify_uuid(cls, value):
        return str(value) if value else None


class CommunicationSettingsModel(BaseModel):
    """
    Communication preferences are sorted by group, so this is the top level. This model serializes all of the group
    data and returns a list communication types.
    """
    communicationGroupUuid: str = Field(alias='communication_group_uuid')
    communicationGroupCategory: Optional[ActivityNotificationCategories] = Field(alias='communication_group_category')
    communicationGroupName: str = Field(alias='communication_group_name')
    communicationGroupType: CommunicationTypes = Field(alias='communication_group_type')
    communicationGroupDescription: str = Field(alias='communication_group_description')
    communicationGroupDisplayOrder: int = Field(alias='communication_group_display_order', default=0)
    communicationGroupItems: Optional[List[internalCommunicationSettingsModel]] = \
        Field(alias='communication_group')

    class Config:
        orm_mode = True
        use_enum_values = True

    @validator('communicationGroupUuid', pre=True)
    def stringify_uuid(cls, value):
        return str(value) if value else None


class SpecialtyCommunicationSettingsModel(BaseModel):
    communicationUuid: str = Field(alias='communication_uuid')
    treeUuid: str = Field(alias='tree_uuid')
    communicationDefaultSetting: bool = Field(alias='communication_default_setting')
    communication: internalCommunicationSettingsModel

    class Config:
        orm_mode = True
        use_enum_values = True

    @validator('communicationUuid', 'treeUuid', pre=True)
    def stringify_uuid(cls, value):
        return str(value) if value else None


class UserCommunicationPreferencesModel(BaseModel):
    userCommunicationSetting: bool = Field(alias='communication_setting')
    communication: internalCommunicationSettingsModel

    class Config:
        orm_mode = True
        use_enum_values = True


class UserPreferencesModel(BaseModel):
    activity: Optional[List[CommunicationSettingsModel]]
    content: Optional[List[CommunicationSettingsModel]]
    transactional: Optional[List[CommunicationSettingsModel]]

    class Config:
        orm_mode = True
        use_enum_values = True


class ActivityNotificationTypes(enum.Enum):
    RealTime = 'realtime'
    Digest = 'digest'


class ActivityNotificationCategorycomments(BaseModel):
    notificationCategory: ActivityNotificationCategories = ActivityNotificationCategories.CommentsRepliesLikes
    description: str = 'Comments, Replies and Likes'
    displayOrder: int = 1
    notificationType: ActivityNotificationTypes = ActivityNotificationTypes.RealTime
    preferences: Optional[List[CommunicationSettingsModel]]

    class Config:
        orm_mode = True
        use_enum_values = True


class ActivityNotificationCategorypaging(BaseModel):
    notificationCategory: ActivityNotificationCategories = ActivityNotificationCategories.Paging
    description: str = 'Paging my specialty'
    displayOrder: int = 4
    notificationType: ActivityNotificationTypes = ActivityNotificationTypes.RealTime
    preferences: Optional[List[CommunicationSettingsModel]]

    class Config:
        orm_mode = True
        use_enum_values = True


class ActivityNotificationCategoryfollow(BaseModel):
    notificationCategory: ActivityNotificationCategories = ActivityNotificationCategories.Follow
    description: str = 'Followers/ Following'
    displayOrder: int = 2
    notificationType: ActivityNotificationTypes = ActivityNotificationTypes.RealTime
    preferences: Optional[List[CommunicationSettingsModel]]

    class Config:
        orm_mode = True
        use_enum_values = True


class ActivityNotificationCategorysavedCases(BaseModel):
    notificationCategory: ActivityNotificationCategories = ActivityNotificationCategories.SavedCases
    description: str = 'Saved Cases'
    displayOrder: int = 3
    notificationType: ActivityNotificationTypes = ActivityNotificationTypes.RealTime
    preferences: Optional[List[CommunicationSettingsModel]]

    class Config:
        orm_mode = True
        use_enum_values = True


class ActivityNotificationCategoryweeklyDigest(BaseModel):
    notificationCategory: ActivityNotificationCategories = ActivityNotificationCategories.WeeklyDigest
    description: str = 'Activity Summaries'
    displayOrder: int = 1
    notificationType: ActivityNotificationTypes = ActivityNotificationTypes.Digest
    preferences: Optional[List[CommunicationSettingsModel]]

    class Config:
        orm_mode = True
        use_enum_values = True


class ActivityCategories(BaseModel):
    commentRepliesLikes: Optional[ActivityNotificationCategorycomments]
    paging: Optional[ActivityNotificationCategorypaging]
    follow: Optional[ActivityNotificationCategoryfollow]
    savedCases: Optional[ActivityNotificationCategorysavedCases]
    weeklyDigest: Optional[ActivityNotificationCategoryweeklyDigest]

    class Config:
        orm_mode = True
        use_enum_values = True


class UserPreferencesModelV2(BaseModel):
    activity: Optional[ActivityCategories]
    content: Optional[List[CommunicationSettingsModel]]
    transactional: Optional[List[CommunicationSettingsModel]]

    class Config:
        orm_mode = True
        use_enum_values = True
