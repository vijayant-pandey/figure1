from enum import Enum
from uuid import UUID
from typing import Optional
from typing import List
from pydantic import BaseModel
from pydantic import Field
from pydantic import validator
from pydantic import root_validator
import logging

from figure1.common.types.anonymizable_model import AnonymizableBaseModel
from figure1.common.types.anonymizable_model import AnonymousCommentFields

logger = logging.getLogger('figure1.commentmodel')


class PhysicianProfessions(Enum):
    """
    This enum is used to determine if a comment is by a physician or not. Any profession name added here is classified
    as a physician when commenting
    """

    PHYSICIAN = 'physician'


class CommentState(Enum):
    REJECTED = 'rejected'
    REPORTED = 'reported'
    DELETED = 'deleted'

    PENDING_APPROVAL = 'pending_approval'
    PENDING_APPROVAL_FLAGGED = 'pending_approval_flagged'
    ALERTED = 'alerted'
    FLAGGED = 'flagged'
    APPROVED = 'approved'


class CommentModeratorReviewStatus(Enum):
    REVIEWED = 'reviewed'
    PENDING_REVIEW = 'pending_review'


class PublicCommentStates(Enum):
    """
    Public comment states can be shown in firestore.  If the flag isn't matched, the comment is not populated in fs.
    Comment text and data may not be sent in full for some public comment states, for example DELETED and REPORTED.
    """

    APPROVED = CommentState.APPROVED
    REJECTED = CommentState.REJECTED
    REPORTED = CommentState.REPORTED
    DELETED = CommentState.DELETED
    ALERTED = CommentState.ALERTED
    FLAGGED = CommentState.FLAGGED


class CommentTranslationModel(BaseModel):
    language: Optional[str] = Field(alias='language')
    text: Optional[str] = Field(alias='text')

    class Config:
        use_enum_values = True
        orm_mode = True
        validate_assignment = True


class CommentModel(AnonymizableBaseModel):
    author: Optional[dict]
    parentUuid: Optional[str] = Field(alias='path')
    parentCommentUuid: Optional[str] = Field(alias='path')
    commentUuid: Optional[str] = Field(alias='comment_uuid')
    authorUuid: Optional[str] = Field(alias='author_uuid')
    contentUuid: Optional[str] = Field(alias='content_uuid')
    createdAt: Optional[str] = Field(alias='created_at')
    updatedAt: Optional[str] = Field(alias='updated_at')
    edited: Optional[bool] = Field(alias='edited')
    text: Optional[str]
    translations: Optional[List[CommentTranslationModel]]
    language: Optional[str] = 'en-US'
    isDeleted: Optional[bool] = Field(alias='deleted_at')
    isPhysician: Optional[bool] = True
    isReported: Optional[bool] = False
    replyable: Optional[bool]
    commentState: CommentState = Field(alias='state')
    isAcceptedAnswer: Optional[bool] = Field(alias='is_accepted_answer')
    moderatorReviewed: Optional[bool] = Field(alias='moderator_reviewed')
    mentions: Optional[List[dict]] = None  # List of user mentions in this comment

    # TODO: remove the following fields once frontend no longer relies on them

    username: Optional[str]
    verified: Optional[bool] = Field(alias='isVerified', default=False)
    avatar: Optional[str] = None
    email: Optional[str]
    professionLabel: Optional[str] = Field(alias='caseCommentDisplayName')
    caseCommentDisplayName: Optional[str] = Field(alias='caseCommentDisplayName')

    fieldsToExcludeIfAnonymous: dict = Field(default=AnonymousCommentFields().toExclude,
                                             exclude=True)

    class Config:
        use_enum_values = True
        orm_mode = True
        validate_assignment = True

    @validator('parentUuid', pre=True, allow_reuse=True)
    def find_parent_comment(cls, value):
        if value:
            v = str(value[0])
            u = UUID(v)
            return str(u)
        else:
            return None

    @validator('parentCommentUuid', pre=True, allow_reuse=True)
    def find_immediate_parent_comment(cls, value):
        if value and len(value) > 1:
            v = str(value[-2])
            u = UUID(v)
            return str(u)
        else:
            return None

    @validator('commentUuid', 'authorUuid', 'contentUuid', 'createdAt', 'updatedAt', pre=True, allow_reuse=True)
    def stringify(cls, value):
        return str(value) if value else None

    @validator('isPhysician', pre=True)
    def handle_is_physician(cls, value):
        if not value:
            return False
        for p in PhysicianProfessions.__members__.values():
            if p.value == value.lower():
                return True
        return False

    @validator('isDeleted', pre=True)
    def handle_deleted(cls, value):
        return True if value else False

    @validator('edited', pre=True)
    def handle_edited(cls, value):
        return True if value else False

    @validator('mentions', pre=True, allow_reuse=True)
    def handle_mentions_from_orm(cls, value):
        # When loading from ORM, the mentions field is a SQLAlchemy relationship
        # We ignore it here and let get_comment_dict_from_object handle it manually
        if value and not isinstance(value, list):
            return None
        # If it's already a list (manually set), keep it
        if isinstance(value, list):
            # Ensure it's a list of dicts, not ORM objects
            if value and hasattr(value[0], '__tablename__'):
                return None  # It's ORM objects, ignore
            return value
        return None

    @root_validator
    def set_state_fields(cls, values):
        state = values.get('commentState')
        if state in [CommentState.REJECTED.value, CommentState.DELETED.value]:
            values['isDeleted'] = True
            values['text'] = 'Comment has been deleted'
        if state == CommentState.REPORTED.value:
            values['text'] = 'Comment has been reported'
            values['isReported'] = True
        return values

    def add_deprecated_fields(self, user_detail_dict):
        self.username = user_detail_dict.get("username")
        self.verified = user_detail_dict.get("isVerified", False)
        self.avatar = user_detail_dict.get("avatar")
        self.email = user_detail_dict.get("email")
        self.professionLabel = user_detail_dict.get("caseCommentDisplayName")
        self.caseCommentDisplayName = user_detail_dict.get("caseCommentDisplayName")


class ChildCommentModel(CommentModel):
    parent: Optional['ChildCommentModel']


class ParentCommentModel(CommentModel):
    children: Optional[List['ParentCommentModel']]


ParentCommentModel.update_forward_refs()
ChildCommentModel.update_forward_refs()


class CommentRejectionReasonModel(BaseModel):
    type: str
    message: Optional[str]


class CommentRejectionReason(Enum):
    DISRESPECTFUL_PATIENT = CommentRejectionReasonModel(
        type='disrespectful_patient',
        message='It may have violated one of our community guidelienes: respect the patients.')
    PRIVACY_ISSUE = CommentRejectionReasonModel(
        type='privacy_issue',
        message='There may have been a potential privacy issue in your comment.')
    PERSONAL_QUESTION_COMMENT = CommentRejectionReasonModel(
        type='personal_question_comment',
        message='It may have been a personal question. Figure 1 is intended for sharing information about patients '
                'under your care.')
    DISRESPECTFUL_USER = CommentRejectionReasonModel(
        type='disrespectful_user',
        message='It may have violated one of our community guidelines: be kind to your fellow community members.')
    UNSUPPORTED = CommentRejectionReasonModel(
        type='unsupported',
        message='It may not have had a scientific basis. Cases and discussion on Figure 1 must have a scientific '
                'basis.')
    PROMOTIONAL = CommentRejectionReasonModel(
        type='promotional',
        message='It may have promoted a particular person, organization, product, or service. Please contact our team '
                'if you are interested in partnership opportunities.')
    UNPROFESSIONAL = CommentRejectionReasonModel(
        type='unprofessional',
        message='It may have been unprofessional. Insensitive, lewd, or otherwise unprofessional comments are not '
                'appropriate for this community.')
    UNSUPPORTED_LANGUAGE = CommentRejectionReasonModel(
        type='unsupported_language',
        message='We currently do not support comments in this language.')
    TREATMENT_REFERENCE = CommentRejectionReasonModel(
        type='treatment_reference',
        message='It may have mentioned treatment on a Sponsored post. The U.S. Federal Drug Administration regulations '
                'prohibit any mention of treatment on sponsored disease-state awareness posts like this.')
    OFF_TOPIC = CommentRejectionReasonModel(
        type='off_topic',
        message='It may not have been related to the case or discussion.  Cases and discussion on Figure 1 must be '
                'relevant to the topic.')
    NO_EMAIL = CommentRejectionReasonModel(
        type='no_email',
        message='')

    @property
    def message(self):
        return self.value.message
