import enum
from typing import Optional

from jinja2 import Environment
from pydantic import BaseModel
from pydantic import Field
from pydantic import HttpUrl
from pydantic import validator

from figure1.common.types import CaseClassification
from figure1.common.types import CaseRejectionReason
from figure1.common.types import CommentRejectionReason
from figure1.common.types import UserNotificationState
from figure1.common.types.field_validators import convert_enum
from figure1.common.types.field_validators import remove_extra_whitespaces
from figure1.common.types.field_validators import stringify_uuid

__all__ = ['NotificationModel',
           'NotificationModelBase',
           'CaseDeletedNotificationModel',
           'CaseRejectedNotificationModel',
           'CommentDeletedNotificationModel',
           'NotificationCaseMediaModel']


class NotificationCaseMediaModel(BaseModel):
    caseMediaUrl: Optional[HttpUrl]


class NotificationModelBase(BaseModel):
    notificationUuid: str = Field(alias='notification_uuid')
    createdAt: Optional[str] = Field(alias='created_at')
    state: Optional[UserNotificationState] = Field(alias='state')
    targetUser: Optional[dict]
    sourceUser: Optional[dict]
    sourceGroup: Optional[dict]
    case: Optional[dict]
    caseMedia: Optional[NotificationCaseMediaModel]
    commentUuid: Optional[str] = Field(alias='comment_uuid')
    markdownMessage: Optional[str] = Field(...)
    comment: Optional[dict]
    anonymousMessage: Optional[str] = Field(exclude=True)
    caseClassification: Optional[CaseClassification]

    # Deprecated
    caseUuid: Optional[str] = Field(alias='case_uuid')
    sourceUuid: Optional[str] = Field(alias='source_uuid')
    userUuid: str = Field(alias='user_uuid')
    type: Optional[str]
    activityType: Optional[str]
    longMessage: Optional[str] = Field(...)

    class Config:
        use_enum_values = True
        orm_mode = True

    _stringify = validator('notificationUuid', 'userUuid', 'caseUuid', 'sourceUuid', 'createdAt', 'commentUuid',
                           allow_reuse=True,
                           pre=True)(stringify_uuid)

    _remove_extra_whitespaces = validator('longMessage', 'markdownMessage', 'anonymousMessage',
                                          allow_reuse=True,
                                          always=True,
                                          pre=True)(remove_extra_whitespaces)

    _enums = validator('state',
                       allow_reuse=True,
                       pre=True)(convert_enum)

    @property
    def template_values(self):
        def _strip_newlines(value: str):
            if isinstance(value, str):
                return ' '.join(value.splitlines())
            return ''

        case_title = ''
        source_username = ''
        comment_text = ''
        source_group_name = ''
        case_author_username = ''
        user_profession = ''
        case_classification = CaseClassification.MEDICAL.value
        if self.case:
            case_title = self.case.get('title') if self.case.get('title') else self.case.get('caption')
            case_title = _strip_newlines(case_title)
            case_author_username = self.case.get('authorUsername') if self.case.get('authorUsername') else ''
            case_classification = self.case.get('caseClassification', CaseClassification.MEDICAL.value)

        if self.sourceUser:
            source_username = self.sourceUser.get('username') if self.sourceUser else ''

        if self.comment:
            comment_text = self.comment.get('text') if self.comment.get('text') else ''

        if self.sourceGroup:
            source_group_name = self.sourceGroup.get('groupName') if self.sourceGroup.get('groupName') else ''

        if self.targetUser:
            user_profession = self.targetUser.get('professionName')

        if case_classification.lower() == 'medical':
            case_name = 'case'
        elif case_classification.lower() == 'nonmedical':
            case_name = 'post'
        else:
            case_name = 'case'

        return dict(caseTitle=case_title,
                    sourceUsername=source_username,
                    sourceGroupName=source_group_name,
                    caseAuthorUsername=case_author_username,
                    commentText=comment_text,
                    userProfession=user_profession,
                    caseName=case_name)

    def populate_template(self):
        env = Environment()
        long_message_template = self.longMessage
        markdown_message_template = self.markdownMessage
        is_anonymous_case = self.case and self.case.get('isAnonymous')
        if self.anonymousMessage and is_anonymous_case:
            long_message_template = self.anonymousMessage
            markdown_message_template = self.anonymousMessage

        self.longMessage = env.from_string(long_message_template).render(self.template_values)
        self.markdownMessage = env.from_string(markdown_message_template).render(self.template_values)


class CaseApprovedNotificationModel(NotificationModelBase):
    notificationType: str = 'approve'
    longMessage: str = 'Your {{caseName}} was approved'
    markdownMessage: str = 'Your {{caseName}} was approved'


class CaseDeletedNotificationModel(NotificationModelBase):
    notificationType: str = 'case_delete'
    longMessage: str = 'Your {{caseName}} was deleted. Tap here to find out why.'
    markdownMessage: str = 'Your {{caseName}} was deleted. Tap here to find out why.'

    draftUid: Optional[str]
    rejectionReason: Optional[CaseRejectionReason]
    rejectionReasonMessage: Optional[str]
    rejectionRevisionAllowed: Optional[bool]


class CaseRejectedNotificationModel(NotificationModelBase):
    notificationType: str = 'reject'
    longMessage: str = "Your {{caseName}} '{{caseTitle|truncate(50)}}' requires editing"
    markdownMessage: str = "Your {{caseName}} '{{caseTitle|truncate(50)}}' requires editing"

    draftUid: Optional[str]
    rejectionReason: Optional[CaseRejectionReason]
    rejectionReasonMessage: Optional[str]
    rejectionRevisionAllowed: Optional[bool]


class CommentDeletedNotificationModel(NotificationModelBase):
    notificationType: str = 'comment_delete'
    longMessage: str = 'Your comment was deleted'
    markdownMessage: str = 'Your comment was deleted'

    rejectionReason: Optional[CommentRejectionReason]
    rejectionReasonMessage: Optional[str]


class CommentOnSavedCaseNotificationModel(NotificationModelBase):
    notificationType: str = 'comment_saved_case'
    longMessage: str = "There's a new comment on a {{caseName}} you saved, '{{caseTitle|truncate(50)}}'"
    markdownMessage: str = "There's a new comment on a {{caseName}} you saved, '{{caseTitle|truncate(50)}}'"


class CommentOnSavedCaseByAuthorNotificationModel(NotificationModelBase):
    notificationType: str = 'comment_saved_case_op'
    longMessage: str = "{{caseAuthorUsername}} commented on their {{caseName}} you saved, '{{caseTitle|truncate(50)}}'"
    markdownMessage: str = "**{{caseAuthorUsername}}** commented on their {{caseName}} you saved, " \
                           "'{{caseTitle|truncate(50)}}'"
    anonymousMessage: str = "The case author commented on their {{caseName}} you saved, '{{caseTitle|truncate(50)}}'"


class CommentOnYourCaseNotificationModel(NotificationModelBase):
    notificationType: str = 'comment'
    longMessage: str = '''{{sourceUsername}} commented on your {{caseName}}: "{{commentText|truncate(50)}}"'''
    markdownMessage: str = '''**{{sourceUsername}}** commented on your {{caseName}}: "{{commentText|truncate(50)}}"'''


class NewCaseFromFollowedUserNotificationModel(NotificationModelBase):
    notificationType: str = 'new_case_followed_user'
    longMessage: str = '{{sourceUsername}}, who you follow, shared a new {{caseName}}'
    markdownMessage: str = '**{{sourceUsername}}**, who you follow, shared a new {{caseName}}'


class NewCaseFromUserWhoseCaseYouSavedNotificationModel(NotificationModelBase):
    notificationType: str = 'new_case_user_saved_case'
    longMessage: str = '{{caseAuthorUsername}}, whose {{caseName}} you saved, shared a new {{caseName}}'
    markdownMessage: str = '**{{caseAuthorUsername}}**, whose {{caseName}} you saved, shared a new {{caseName}}'


class NewCaseFromGroupNotificationModel(NotificationModelBase):
    notificationType: str = 'new_group_case'
    longMessage: str = '{{caseAuthorUsername}} shared a new {{caseName}} in your {{sourceGroupName}} group'
    markdownMessage: str = '**{{caseAuthorUsername}}** shared a new {{caseName}} in your **{{sourceGroupName}}** group'
    anonymousMessage: str = 'Someone shared a new {{caseName}} in your **{{sourceGroupName}}** group'


class NewFollowerNotificationModel(NotificationModelBase):
    notificationType: str = 'new_follower'
    longMessage: str = '{{sourceUsername}} followed you'
    markdownMessage: str = '**{{sourceUsername}}** followed you'


class PagingCaseNotificationModel(NotificationModelBase):
    notificationType: str = 'paging'
    longMessage: str = '{{caseAuthorUsername}} is seeking immediate feedback in your specialty.'
    markdownMessage: str = '**{{caseAuthorUsername}}** is seeking immediate feedback in your specialty.'
    anonymousMessage: str = 'Someone is seeking immediate feedback in your specialty.'


class ReactionOnYourCaseNotificationModel(NotificationModelBase):
    notificationType: str = 'react'
    longMessage: str = '{{sourceUsername}} liked your {{caseName}}'
    markdownMessage: str = '**{{sourceUsername}}** liked your {{caseName}}'


class ReplyToYourCommentNotificationModel(NotificationModelBase):
    notificationType: str = 'comment_reply'
    longMessage: str = '''{{sourceUsername}} replied to you: "{{commentText|truncate(50)}}"'''
    markdownMessage: str = '''**{{sourceUsername}}** replied to you: "{{commentText|truncate(50)}}"'''


class ReplyToYourCommentByAuthorNotificationModel(NotificationModelBase):
    notificationType: str = 'comment_reply_op'
    longMessage: str = '''The author, {{sourceUsername}} has replied to you: "{{commentText|truncate(50)}}"'''
    markdownMessage: str = '''The author, **{{sourceUsername}}** has replied to you: "{{commentText|truncate(50)}}"'''
    anonymousMessage: str = '''The case author has replied to you: "{{commentText|truncate(50)}}"'''


class SavedCaseUpdateNotificationModel(NotificationModelBase):
    notificationType: str = 'saved_case_update'
    longMessage: str = "{{sourceUsername}} updated a case you saved, '{{caseTitle|truncate(50)}}'"
    markdownMessage: str = "**{{sourceUsername}}** updated a case you saved, '{{caseTitle|truncate(50)}}'"
    anonymousMessage: str = "The case author updated a case you saved, '{{caseTitle|truncate(50)}}'"


class CaseNotDiagnosisChosenModel(NotificationModelBase):
    notificationType: str = 'case_not_diagnosis_chosen'
    longMessage: str = "Any progression on your case? You can update and add a diagnosis"
    markdownMessage: str = "Any progression on your case? You can **update and add a diagnosis**"


class CommentedCaseDiagnosisNotificationModel(NotificationModelBase):
    notificationType: str = 'commented_case_diagnosis'
    longMessage: str = "The author {{sourceUsername}} added a diagnosis to a case you commented on"
    markdownMessage: str = "The author **{{sourceUsername}}** added a diagnosis to a case you commented on"
    anonymousMessage: str = "The case author added a diagnosis to a case you commented on"


class SavedCaseDiagnosisNotificationModel(NotificationModelBase):
    notificationType: str = 'saved_case_diagnosis'
    longMessage: str = "The author {{sourceUsername}} added a diagnosis to a case you saved"
    markdownMessage: str = "The author **{{sourceUsername}}** added a diagnosis to a case you saved"
    anonymousMessage: str = "The case author added a diagnosis to a case you saved"


class LikedCaseDiagnosisNotificationModel(NotificationModelBase):
    notificationType: str = 'liked_case_diagnosis'
    longMessage: str = "The author {{sourceUsername}} added a diagnosis to a case you liked"
    markdownMessage: str = "The author **{{sourceUsername}}** added a diagnosis to a case you liked"
    anonymousMessage: str = "The case author added a diagnosis to a case you liked"


class ProfessionChangeApprovedNotificationModel(NotificationModelBase):
    notificationType: str = 'profession_change_approved'
    longMessage: str = "Your profession edit request was reviewed and your profession has been updated."
    markdownMessage: str = "Your profession edit request was reviewed and your profession has been updated."


class GroupInviteAcceptedNotificationModel(NotificationModelBase):
    notificationType: str = 'group_invite_accepted'
    longMessage: str = "{{sourceUsername}} joined your {{sourceGroupName}} group.  See all group members"
    markdownMessage: str = "**{{sourceUsername}}** joined your **{{sourceGroupName}}** group.  See all group members"


class NewAcceptedAnswerSavedCaseNotificationModel(NotificationModelBase):
    """
    Triggered if a case the user has saved on has a new accepted answer
    """
    notificationType: str = 'new_accepted_answer_saved_case'
    notificationGroup: str = 'accepted_answer'
    notificationGroupPriority: int = 3
    longMessage: str = """The author, {{sourceUsername}}, selected an accepted answer on a case you saved"""
    markdownMessage: str = """The author, **{{sourceUsername}}**, selected an **accepted answer** on a case you saved"""
    anonymousMessage: str = "The case author selected an accepted answer on a case you saved"


class NewAcceptedAnswerLikedCaseNotificationModel(NotificationModelBase):
    """
    Triggered if a case the user has liked on has a new accepted answer
    """
    notificationType: str = 'new_accepted_answer_liked_case'
    notificationGroup: str = 'accepted_answer'
    notificationGroupPriority: int = 4
    longMessage: str = """The author, {{sourceUsername}}, selected an accepted answer on a case you liked"""
    markdownMessage: str = """The author, **{{sourceUsername}}**, selected an **accepted answer** on a case you liked"""
    anonymousMessage: str = "The case author selected an accepted answer on a case you liked"


class NewAcceptedAnswerCommentedCaseNotificationModel(NotificationModelBase):
    """
    Triggered if a case the user has commented on has a new accepted answer
    """
    notificationType: str = 'new_accepted_answer_commented_case'
    notificationGroup: str = 'accepted_answer'
    notificationGroupPriority: int = 2
    longMessage: str = """The author, {{sourceUsername}}, selected an accepted answer on a case you commented on"""
    markdownMessage: str = """The author, **{{sourceUsername}}**, selected an **accepted answer** on a case you \
    commented on """
    anonymousMessage: str = "The case author selected an accepted answer on a case you commented on"


class NewAcceptedAnswerSelectedNotificationModel(NotificationModelBase):
    """
    Triggered if a user's comment is selected as the accepted answer
    """
    notificationType: str = 'new_accepted_answer_selected'
    notificationGroup: str = 'accepted_answer'
    notificationGroupPriority: int = 1
    longMessage: str = """The author, {{sourceUsername}}, has selected your comment as the accepted answer on their \
    case """
    markdownMessage: str = """The author, **{{sourceUsername}}**, has selected your comment \
    as the **accepted answer** on their case """
    anonymousMessage: str = "Good job! The case author selected your comment as the accepted answer on their case"


class AcceptedAnswerDeletedNotificationModel(NotificationModelBase):
    """
    Triggered if a user's accepted answer is deleted
    """
    notificationType: str = 'accepted_answer_deleted'
    notificationGroup: str = 'accepted_answer'
    notificationGroupPriority: int = 1
    longMessage: str = """The comment you selected as the accepted answer on your case was deleted. Select another \
    comment"""
    markdownMessage: str = """The comment you selected as the **accepted answer** on your case was deleted. \
    Select another comment"""


class CaseNotAcceptedAnswerChosenModel(NotificationModelBase):
    notificationType: str = 'case_not_accepted_answer_chosen'
    notificationGroup: str = 'accepted_answer'
    notificationGroupPriority: int = 1
    longMessage: str = "Check out the comments on your case to select an accepted answer"
    markdownMessage: str = "Check out the comments on your case to select an **accepted answer**"


class NotificationModel(enum.Enum):
    APPROVE = CaseApprovedNotificationModel
    CASE_DELETE = CaseDeletedNotificationModel
    CASE_NOT_DIAGNOSIS_CHOSEN = CaseNotDiagnosisChosenModel
    CASE_NOT_ACCEPTED_ANSWER_CHOSEN = CaseNotAcceptedAnswerChosenModel
    COMMENT = CommentOnYourCaseNotificationModel
    COMMENT_DELETE = CommentDeletedNotificationModel
    COMMENT_REPLY = ReplyToYourCommentNotificationModel
    COMMENT_REPLY_OP = ReplyToYourCommentByAuthorNotificationModel
    COMMENT_SAVED_CASE = CommentOnSavedCaseNotificationModel
    COMMENT_SAVED_CASE_OP = CommentOnSavedCaseByAuthorNotificationModel
    NEW_CASE_FOLLOWED_USER = NewCaseFromFollowedUserNotificationModel
    NEW_CASE_USER_SAVED_CASE = NewCaseFromUserWhoseCaseYouSavedNotificationModel
    NEW_CASE_GROUP = NewCaseFromGroupNotificationModel
    NEW_FOLLOWER = NewFollowerNotificationModel
    PAGING = PagingCaseNotificationModel
    REACT = ReactionOnYourCaseNotificationModel
    REJECT = CaseRejectedNotificationModel
    SAVED_CASE_UPDATE = SavedCaseUpdateNotificationModel
    COMMENTED_CASE_DIAGNOSIS = CommentedCaseDiagnosisNotificationModel
    SAVED_CASE_DIAGNOSIS = SavedCaseDiagnosisNotificationModel
    LIKED_CASE_DIAGNOSIS = LikedCaseDiagnosisNotificationModel
    PROFESSION_CHANGE_APPROVED = ProfessionChangeApprovedNotificationModel
    GROUP_INVITE_ACCEPTED = GroupInviteAcceptedNotificationModel
    NEW_ACCEPTED_ANSWER_SELECTED = NewAcceptedAnswerSelectedNotificationModel
    NEW_ACCEPTED_ANSWER_COMMENTED_CASE = NewAcceptedAnswerCommentedCaseNotificationModel
    NEW_ACCEPTED_ANSWER_LIKED_CASE = NewAcceptedAnswerLikedCaseNotificationModel
    NEW_ACCEPTED_ANSWER_SAVED_CASE = NewAcceptedAnswerSavedCaseNotificationModel
    ACCEPTED_ANSWER_DELETED = AcceptedAnswerDeletedNotificationModel
