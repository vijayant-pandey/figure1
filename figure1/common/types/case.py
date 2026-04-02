from enum import Enum
from typing import Any
from typing import List
from typing import Optional

from pydantic import BaseModel
from pydantic import Field
from pydantic import HttpUrl
from pydantic import conlist
from pydantic import constr
from pydantic import validator

from figure1.configuration import app_settings
from .anonymizable_model import AnonymizableBaseModel
from .anonymizable_model import AnonymousFeedCardFields
from .field_validators import force_lower_case
from .field_validators import stringify_uuid
from .locales import Locale
from .media import MediaModel
from .media import MediaUploadModel
from .sponsored_content import FeaturesModel
from .sponsored_content import SponsoredContentModel


class CaseState(Enum):
    REJECTED = 'rejected'
    REPORTED = 'reported'
    DELETED = 'deleted'
    UNSUPPORTED = 'unsupported'

    DRAFT = 'draft'
    PENDING_APPROVAL = 'pending_approval'
    FLAGGED = 'flagged'
    EDIT_SUGGESTED = 'edit_suggested'
    APPROVED = 'approved'
    PENDING_NLP = 'pending_nlp'
    PENDING_TAGGING = 'pending_tagging'
    FLAGGED_TAGGER = 'flagged_tagger'
    ARCHIVED = 'archived'

    SC_DRAFT = 'sc_draft'
    SC_REVIEW = 'sc_review'
    SC_APPROVED = 'sc_approved'
    SC_ARCHIVED = 'sc_archived'


class PublicCaseStates(Enum):
    """
    Public case states can be shown, but are not necessarily universally accessible. This flag decides if a case can be
    fully populated in firestore.
    If this flag isn't matched, only the caseState is populated
    """

    APPROVED = CaseState.APPROVED
    SC_APPROVED = CaseState.SC_APPROVED
    SC_REVIEW = CaseState.SC_REVIEW


class Reaction(Enum):
    AGREE = 'agree'
    CLINICALLYUSEFUL = 'clinicallyUseful'
    INFORMATIVE = 'informative'


class CaseRejectionReasonModel(BaseModel):
    type: str
    allow_revision: bool
    message: Optional[str]


class CaseRejectionReason(Enum):
    SELFIE = CaseRejectionReasonModel(
        type='selfie',
        allow_revision=False,
        message='It may not have been a clinical care case. We do not allow cases displaying your own medical '
                'conditions or those of your family or friends.')
    INAPPROPRIATE_CONTENT = CaseRejectionReasonModel(
        type='inappropriate_content',
        allow_revision=False,
        message='There may have been inappropriate content on the case or post. '
                'We do not allow any type of cases or posts that are inappropriate.')
    SUSPECTED_HOMEWORK = CaseRejectionReasonModel(
        type='suspected_homework',
        allow_revision=False,
        message='It may not have been a clinical care case. Case studies or homework assignments are not appropriate '
                'for Figure 1.')
    UNDERAGE_NUDITY = CaseRejectionReasonModel(
        type='underage_nudity',
        allow_revision=False,
        message='It is our current policy to protect minors in any way we can. If possible, please use our editing '
                'tools to block genitals, buttocks and/ or breast area and resubmit your case.')
    TINEYE = CaseRejectionReasonModel(
        type='tineye',
        allow_revision=False,
        message='There may have been some copyright issues with the image. If the image belongs to you, please contact '
                'our team at support@figure1.com.')
    DELETE_NO_EMAIL = CaseRejectionReasonModel(
        type='delete_no_email',
        allow_revision=False,
        message=None)
    NEED_CLINICAL_INFO = CaseRejectionReasonModel(
        type='need_clinical_info',
        allow_revision=True,
        message='Please include more clinical information in the case summary.')
    NOT_DIRECT_CARE = CaseRejectionReasonModel(
        type='not_direct_care',
        allow_revision=True,
        message='We only allow cases in your direct clinical care. If this is your patient, please describe your '
                'involvement in the case summary.')
    INAPPROPRIATE_PAGING = CaseRejectionReasonModel(
        type='inappropriate_paging',
        allow_revision=True,
        message='The paging feature is intended to be used when immediate feedback is required. Please add a question '
                'that you need answered and resubmit.')
    NON_CLINICAL_PHOTOS = CaseRejectionReasonModel(
        type='non_clinical_photos',
        allow_revision=True,
        message='The image does not follow our community guidelines. '
                'Please resubmit as a text-only case or post if you do not have an image that follows our guidelines.')
    UNSUPPORTED_LANGUAGE = CaseRejectionReasonModel(
        type='unsupported_language',
        allow_revision=True,
        message='Please resubmit your case in English. Unfortunately, we do not support this language yet.')

    @property
    def allow_revision(self):
        return self.value.allow_revision

    @property
    def message(self):
        return self.value.message


class ContentType(Enum):
    CONTENT = 'content'
    QUIZ = 'quiz'
    QUIZ_SERIES = 'quiz_series'
    QUIZ_SUMMARY = 'quiz_summary'
    FEED_CARD = 'feed_card'
    COVER = 'cover'
    CONCLUSION = 'conclusion'
    CME_HUB_CARD = 'cme_hub_card'
    PROMO_CARD = 'promo_card'


class ContentUpdateType(Enum):
    DIAGNOSIS = 'diagnosis'
    UPDATE = 'update'


class CaseType(Enum):
    STATIC = 'static'
    QUIZ = 'quiz'
    QUIZ_SERIES = 'quiz_series'
    CLINICAL_MOMENTS = 'clinical_moments'
    CME = 'cme'
    PROMO_CARD = 'promo_card'


class CaseClassification(Enum):
    MEDICAL = 'medical'
    NONMEDICAL = 'nonmedical'


class FeedCardType(Enum):
    BASIC = 'basic'
    HIGHLIGHT = 'highlight'
    END_OF_FEED = 'end_of_feed'
    PREVIEW_FEED = 'preview_feed'


class ContentSection(Enum):
    FRONT_MATTER = 'front_matter'
    PRE_TEST = 'pre_test'
    ACTIVITY = 'activity'
    POST_TEST = 'post_test'
    SURVEY = 'survey'


class CaseReactionCountModel(BaseModel):
    """
    Total number of reactions per reaction for a case
    """
    agree: Optional[int] = 0
    clinicallyUseful: Optional[int] = 0
    informative: Optional[int] = 0


class UserCaseReactionModel(BaseModel):
    """
    List of user uuids who have reacted to a case
    """
    agree: List[str] = []
    clinicallyUseful: List[str] = []
    informative: List[str] = []


class FeedCardModel(AnonymizableBaseModel):
    """
    case_uuid is currently required for loaded related cases. Once this is confirmed fixed, remove case_uuid
    """
    caseUuid: str
    case_uuid: str = Field(alias='caseUuid')
    caseState: Optional[str]
    caseClassification: Optional[str]
    allReactions: CaseReactionCountModel = CaseReactionCountModel()
    authorProfessionLabel: Optional[str]
    authorProfessionUuid: Optional[str]
    authorUid: Optional[str]
    authorUsername: Optional[str] = Field(alias='author_username')
    authors: Optional[List[Any]]
    caption: Optional[str]
    title: Optional[str]
    commentCount: Optional[int]
    updateCount: Optional[int]
    createdAt: Optional[str]
    updatedAt: Optional[str]
    publishedAt: Optional[str]
    shareLink: Optional[HttpUrl]
    media: Optional[List[MediaModel]]
    isPagingCase: Optional[bool]
    labels: Optional[List[str]]
    contentCount: Optional[int] = 0
    unverifiedViewCount: Optional[int]
    caseType: Optional[str]
    cme1Credits: Optional[int] = 0
    score: Optional[int]
    isSaved: Optional[bool]
    features: FeaturesModel = FeaturesModel()
    userReactions: List[str] = []
    groupUuid: Optional[str]
    language: Optional[str]
    isSponsored: Optional[bool] = False
    hasDiagnosis: Optional[bool] = False
    isCaseCme: Optional[bool]
    hasAcceptedAnswer: Optional[bool]
    specialtyNames: Optional[List[str]]
    requestHelp: Optional[bool] = False

    # If the self.isAnonymous is True, only fields not in self.fieldsToExcludeIfAnonymous would be
    # returned if self.dict is called.
    fieldsToExcludeIfAnonymous: dict = Field(default=AnonymousFeedCardFields().toExclude,
                                             exclude=True)

    @validator('isCaseCme', pre=True)
    def force_case_cme(cls, value):
        if app_settings.case_cme_enabled is False:
            return False
        else:
            return value

    class Config:
        arbitrary_types_allowed = True
        allow_population_by_field_name = True


class FeedCardDisplayModel(BaseModel):
    buttonText: Optional[str]
    buttonUrl: Optional[str]
    externalLinkText: Optional[str]
    externalLinkUrl: Optional[str]
    questionAnswerDetails: Optional[str]
    heading: Optional[str]
    colour: Optional[str]
    features: FeaturesModel = FeaturesModel()
    sponsoredContent: Optional[SponsoredContentModel]
    questionOptions: Optional[List[Any]]
    contentType: Optional[str]
    contentUuid: Optional[str]
    feedCardTitle: Optional[str]
    feedCardMedia: Optional[MediaModel]
    feedCardLabel: Optional[str]
    feedCardType: FeedCardType

    _force_lower = validator('feedCardType', allow_reuse=True, pre=True)(force_lower_case)

    class Config:
        arbitrary_types_allowed = True
        allow_population_by_field_name = True
        use_enum_values = True


class CaseConstraints(BaseModel):
    """
    This is only needed for models that edit a case.
    """
    title: Optional[constr(max_length=1000)]
    caption: Optional[constr(max_length=10000)]
    diagnosis: Optional[constr(max_length=10000)]


class CaseUploadModel(CaseConstraints):
    caseUuid: Optional[str] = Field(alias='case_uuid')
    caseClassification: Optional[CaseClassification] = Field(alias='case_classification',
                                                             default=CaseClassification.MEDICAL)
    media: List[MediaUploadModel] = Field(max_items=100)
    paging: Optional[bool] = False
    requestHelp: Optional[bool] = Field(alias='request_help', default=False)
    labelUuids: conlist(str, max_items=10) = Field(alias='label_uuids')
    specialtyUuids: conlist(str, max_items=50) = Field(alias='specialty_uuids')
    isAnonymous: Optional[bool] = Field(alias='is_anonymous', default=False)
    groupUuid: Optional[str] = Field(alias='group_uuid')
    postProcessMedia: Optional[bool] = Field(alias='post_process_media', default=True)


class PromoCardPlatformSpecificModel(BaseModel):
    buttonLink: Optional[str]
    showCard: Optional[bool]


class PromoCardModel(CaseConstraints):
    diagnosis: Optional[constr(max_length=10000)] = Field(exclude=True)
    campaignUuid: Optional[str]
    caseUuid: Optional[str]
    buttonText: Optional[str]
    dismissButton: Optional[bool]
    dismissOnClick: Optional[bool]
    endDate: Optional[str]
    startDate: Optional[str]
    mobile: Optional[PromoCardPlatformSpecificModel]
    web: Optional[PromoCardPlatformSpecificModel]
    priority: Optional[int]

    _stringify_uuid = validator('campaignUuid', 'caseUuid', allow_reuse=True, pre=True)(stringify_uuid)


class ModerationCaseEdit(CaseConstraints):
    caseUuid: str = Field(alias='case_uuid')
    moderatorUid: str = Field(alias='moderator_uid')
    suggestedEdit: bool = Field(alias='suggested_edit', default=True)
    contentUuid: Optional[str] = Field(alias='content_uuid')
    language: Optional[str]
    caseClassification: Optional[CaseClassification] = Field(alias='case_classification')

    @validator('language', pre=True)
    def validate_language(cls, value):
        return Locale.get_from_code(value).code
