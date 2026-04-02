from enum import Enum
from typing import Optional
from typing import List
from pydantic import BaseModel
from pydantic import HttpUrl
from pydantic import root_validator
from pydantic import Field
from pydantic import validator
from pydantic import EmailStr

from figure1.common.types.anonymizable_model import AnonymizableBaseModel
from figure1.common.types.screen_constants import CasePostingScreens
from figure1.common.types.screen_constants import RegistrationSections
from figure1.common.types.comment import CommentModel


__all__ = [
    'IterableEvent',
    'IterableBaseEvent',
    'NonPublicIterableEvents',
    'CaseEventData',
    'UserEventData',
    'IterableEventWrapper',
    'CaseAggregateEvent',
    'BaseAggregateEvent',
    'IterableAggregateEvent',
    'IterableAggregateEventWrapper',
    'IterableNewCaseEventDataFields',
    'IterableNewGroupCaseEventDataFields',
    'IterableCommentOnYourCaseEventDataFields',
    'IterableCommentReplyEventDataFields',
    'IterableUserCommentedOnCaseYouSavedEventDataFields',
    'IterableCaseUpdateEventDataFields',
    'IterablePagingEventDataFields',
    'IterableCaseAcceptedAnswerEventDataFields',
]


class IterableEvent(Enum):
    ACTIVITY_REMINDER = 'newActivity'
    CASE_NEW_UPDATE = 'newCaseUpdate'
    CASE_POST_TRACKING = 'casePostTracking'
    CASE_POSTED_FOLLOWED_USER = 'casePostedFromUserYouFollow'
    CASE_POSTED_GROUP = 'casePostedFromGroupYouAreIn'
    CASE_POSTED_USER_SAVED_CASE = 'casePostedFromUserWhosCaseYouSaved'
    CASE_REACTION = 'caseReaction'
    CASE_STATE_CHANGED = 'caseStateChanged'
    CME_COMPLETED = 'cmeCompleted'
    COMMENT_DELETED = 'commentDeleted'
    COMMENT_REPLY = 'someoneRepliedToYou'
    COMMENT_SAVED_CASE = 'newCommentOnCaseYouSaved'
    COMMENT_YOUR_CASE = 'caseComment'
    CASE_NEW_ACCEPTED_ANSWER = 'newCaseAcceptedAnswer'
    CASE_NEW_ACCEPTED_ANSWER_SELECTED = 'youCommentWasSelectedAsAcceptedAnswer'
    CASE_ACCEPTED_ANSWER_NOT_CHOSEN = 'youHaveNotChosenAnAcceptedAnswer'
    CASE_ACCEPTED_ANSWER_DELETED = 'acceptedAnswerDeleted'
    DIAGNOSIS_NOT_CHOSEN = 'youHaveNotChosenADiagnosis'
    FOLLOWER = 'SomeoneFollowedYou'
    GROUP_INVITE = 'invitedToGroup'
    GROUP_INVITE_ACCEPTED = 'groupInviteAccepted'
    PAGING_CASE_POSTED_SPECIALTY_SUBSPECIALTY_USERS = 'pagingCaseToSpecialtySubspecialtyUsers'
    PAGING_CASE_POSTED_SPECIALTY_USERS = 'pagingCaseToSpecialtyUsers'
    PAGING_CASE_POSTED_SUBSPECIALTY_USERS = 'pagingCaseToSubspecialtyUsers'
    PROFESSION_CHANGE_APPROVED = 'professionChangeApproved'
    USER_STATUS_CHANGED = 'userStatusChangedEvent'
    USER_REGISTRATION_TRACKING = 'userRegistrationTracking'
    USER_MARKETING_SIGN_UP = 'marketingSignUp'


class IterableBaseEvent(BaseModel):
    firstName: Optional[str] = Field(alias='first_name')
    lastName: Optional[str] = Field(alias='last_name')
    userUuid: str = Field(alias='user_uuid')
    email: EmailStr = Field(alias='email')
    userUid: Optional[str] = Field(alias='user_uid')
    screenName: Optional[str]

    @validator('userUuid', pre=True)
    def stringify_uuid(cls, value):
        return str(value)

    @validator('screenName')
    def validate_screen_id(cls, value):
        if value in CasePostingScreens.draft_list() or value in RegistrationSections.sync_only_list():
            return value
        raise ValueError(f"Screen {value} not in Case Posting list or registration list")

    class Config:
        orm_mode = True
        validate_assignment = True


class NonPublicIterableEvents(Enum):
    """
    Non-public iterable events can not be sent if a case is anonymous.
    """
    CASE_POSTED_FOLLOWED_USER = IterableEvent.CASE_POSTED_FOLLOWED_USER
    CASE_POSTED_USER_SAVED_CASE = IterableEvent.CASE_POSTED_USER_SAVED_CASE
    CASE_POSTED_GROUP = IterableEvent.CASE_POSTED_GROUP


class CaseEventData(IterableBaseEvent):
    caseTitle: Optional[str]
    caseCaption: Optional[str]
    DraftUid: Optional[str]


class UserEventData(IterableBaseEvent):
    pass


class IterableEventWrapper(BaseModel):
    eventName: IterableEvent = Field(alias='event')
    email: EmailStr
    dataFields: dict = Field(alias='data_fields')
    userId: str = Field(alias='user_uuid')

    @validator('userId', pre=True)
    def stringify_uuid(cls, value):
        return str(value)

    class Config:
        use_enum_values = True
        orm_mode = True


class CaseAggregateEvent(BaseModel):
    caseTitle: Optional[str]
    caseCaption: Optional[str]
    comments: List[CommentModel] = []
    reactionCount: int = 0
    commentCount: int = 0
    caseUuid: str


class BaseAggregateEvent(BaseModel):
    cases: List[CaseAggregateEvent] = []
    totalFollowerCount: int = 0
    totalReactionCount: int = 0
    totalCommentCount: int = 0


class IterableAggregateEvent(BaseModel):
    firstName: Optional[str]
    lastName: Optional[str]
    userUuid: Optional[str]
    email: Optional[str]
    userUid: Optional[str]
    event: Optional[BaseAggregateEvent]


class IterableAggregateEventWrapper(BaseModel):
    eventName: str
    email: EmailStr
    dataFields: IterableAggregateEvent
    userId: Optional[str]


class IterableNewCaseEventDataFields(BaseModel):
    caseCaption: Optional[str]
    caseTitle: Optional[str]
    caseUuid: Optional[str]
    caseAuthorUsername: Optional[str]
    caseAuthorFirstName: Optional[str]
    caseAuthorLastName: Optional[str]
    caseAuthorUuid: Optional[str]
    caseAuthorEmail: Optional[str]
    receiverUuid: Optional[str]
    caseClassification: Optional[str]
    caseMediaUrl: Optional[HttpUrl]

    @validator('caseUuid', 'caseAuthorUuid', 'receiverUuid', pre=True)
    def stringify_uuid(cls, value):
        return str(value) if value else None


class IterableNewGroupCaseEventDataFields(BaseModel):
    groupUuid: Optional[str]
    groupName: Optional[str]
    caseUuid: Optional[str]
    caseSubmissionDate: Optional[str]
    caseTitle: Optional[str]
    authorUsername: Optional[List[str]]
    caseLabels: Optional[List[str]]
    caseClassification: Optional[str]
    caseMediaUrl: Optional[HttpUrl]
    caseCaption: Optional[str]

    @validator('groupUuid', 'caseUuid', pre=True)
    def stringify_uuid(cls, value):
        return str(value) if value else None


class IterableCommentOnYourCaseEventDataFields(BaseModel):
    caseCaption: Optional[str]
    caseTitle: Optional[str]
    caseUuid: Optional[str]
    commentUuid: Optional[str]
    receiverUuid: Optional[str]
    receiverUid: Optional[str]
    groupUuid: Optional[str]
    groupName: Optional[str]
    caseClassification: Optional[str]
    commentText: Optional[str]
    caseMediaUrl: Optional[HttpUrl]

    @validator('caseUuid', 'receiverUuid', 'groupUuid', 'commentUuid', pre=True)
    def stringify_uuid(cls, value):
        return str(value) if value else None


class IterableCommentReplyEventDataFields(AnonymizableBaseModel):
    caseTitle: Optional[str]
    caseUuid: Optional[str]
    commentUuid: Optional[str]
    mainCommentAuthorUuid: Optional[str]
    receiverUuid: Optional[str]
    respondentUuid: Optional[str]
    is_op: Optional[bool]
    groupUuid: Optional[str]
    groupName: Optional[str]
    caseClassification: Optional[str]
    replyText: Optional[str]
    caseMediaUrl: Optional[HttpUrl]
    caseAuthorUsername: Optional[str]

    isAnonymous: Optional[bool] = Field(exclude=True, default=False)
    fieldsToExcludeIfAnonymous: dict = Field(exclude=True,
                                             default={"respondentUuid": True})

    @validator('caseUuid', 'mainCommentAuthorUuid',
               'receiverUuid', 'respondentUuid',
               'groupUuid', 'commentUuid', pre=True)
    def stringify_uuid(cls, value):
        return str(value) if value else None


class IterableUserCommentedOnCaseYouSavedEventDataFields(AnonymizableBaseModel):
    caseCaption: Optional[str]
    caseTitle: Optional[str]
    caseUuid: Optional[str]
    commentUuid: Optional[str]
    commenterUUID: Optional[str]
    is_OP: Optional[bool]
    caseAuthorEmail: Optional[List[str]]
    caseAuthorUsername: Optional[List[str]]
    caseAuthorsUUID: Optional[List[str]]
    receiverUuid: Optional[str]
    groupUuid: Optional[str]
    groupName: Optional[str]
    caseClassification: Optional[str]
    caseMediaUrl: Optional[HttpUrl]
    commentText: Optional[str]

    isAnonymous: Optional[bool] = Field(exclude=True, default=False)
    fieldsToExcludeIfAnonymous: dict = Field(exclude=True,
                                             default={"caseAuthorEmail": True,
                                                      "caseAuthorUsername": True,
                                                      "caseAuthorsUUID": True})

    @root_validator(pre=True)
    def exclude_commenter_uuid_if_is_op(cls, values):
        if values["is_OP"] is True and values["isAnonymous"] is True:
            if "fieldsToExcludeIfAnonymous" in values:
                values["fieldsToExcludeIfAnonymous"].update({"commenterUUID": True})
            else:
                values["fieldsToExcludeIfAnonymous"] = {"caseAuthorEmail": True,
                                                        "caseAuthorUsername": True,
                                                        "caseAuthorsUUID": True,
                                                        "commenterUUID": True}

        return values

    @validator('caseUuid', 'commenterUUID',
               'receiverUuid', 'groupUuid', 'commentUuid', pre=True)
    def stringify_uuid(cls, value):
        return str(value) if value else None

    @validator('caseAuthorsUUID', pre=True)
    def stringify_list_of_uuids(cls, value):
        return [str(each) for each in value] if value else None


class IterableCaseUpdateEventDataFields(AnonymizableBaseModel):
    caseTitle: Optional[str]
    caseUuid: Optional[str]
    groupUuid: Optional[str]
    groupName: Optional[str]
    caseCurrentStatus: Optional[str]
    casePreviousStatus: Optional[str]
    diagnosisUpdateAdded: Optional[bool]
    authorUsername: Optional[str]
    caseMediaUrl: Optional[HttpUrl]

    isAnonymous: Optional[bool] = Field(exclude=True, default=False)
    fieldsToExcludeIfAnonymous: dict = Field(exclude=True,
                                             default={"authorUsername": True})

    @validator('caseUuid', 'groupUuid', pre=True)
    def stringify_uuid(cls, value):
        return str(value) if value else None


class IterablePagingEventDataFields(AnonymizableBaseModel):
    caseCaption: Optional[str]
    caseTitle: Optional[str]
    caseUuid: Optional[str]
    caseTimeApproval: Optional[str]
    caseSpecialty: Optional[List[str]]
    caseMediaUrl: Optional[HttpUrl]
    authorsInfo: Optional[List]

    isAnonymous: Optional[bool] = Field(exclude=True, default=False)
    fieldsToExcludeIfAnonymous: dict = Field(exclude=True,
                                             default={"authorsInfo": True})

    @validator('caseUuid', pre=True)
    def stringify_uuid(cls, value):
        return str(value) if value else None


class IterableCaseAcceptedAnswerEventDataFields(AnonymizableBaseModel):
    caseTitle: Optional[str]
    caseUuid: Optional[str]
    commentUuid: Optional[str]
    authorUsername: Optional[str]
    deletionReason: Optional[str]
    acceptedAnswerSet: Optional[bool]
    numberOfComments: Optional[int]
    diagnosisUpdateAdded: Optional[bool]
    caseSubmissionDate: Optional[str]
    caseCaption: Optional[str]
    caseMediaUrl: Optional[HttpUrl]

    isAnonymous: Optional[bool] = Field(exclude=True, default=False)
    fieldsToExcludeIfAnonymous: dict = Field(exclude=True,
                                             default={"authorUsername": True})

    @validator('caseUuid', 'commentUuid', pre=True)
    def stringify_uuid(cls, value):
        return str(value) if value else None
