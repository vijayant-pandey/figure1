from .user import UserNotFound, \
    UserUIDNotFound, \
    UserUUIDNotFound, \
    UserError, \
    UserDeleted, \
    DuplicateUser, \
    UserUsernameNotFound, \
    UserEmailNotFound, \
    InvalidUserType, \
    UsernameValidation, \
    GroupException, \
    InsufficientPermissions
from .feed import TopicFeedNotFound, \
    MFYNotFound, \
    EverythingNotFound, \
    FeedNotFound, \
    SearchException, \
    FeedException, \
    GroupFeedNotFound
from .verification import InvalidVerificationStatus, \
    InvalidVerificationType, \
    VerificationException, \
    DuplicateVerificationRequest, \
    VerificationMethodNotFound, \
    InvalidNPINumber, \
    InvalidAPIResponse, \
    NPIAPIError, \
    VerificationNotFound, \
    InvalidOperationForVerificationType
from .s3 import S3Error
from .campaign import CampaignException, \
    InvalidCampaignDates, \
    CampaignNotFound, \
    TacticUpdateError, \
    TacticError, \
    TacticDeleted, \
    TacticInvalidDates, \
    TacticNotFound, \
    InvalidFeedCardType, \
    InvalidContentType
from .case import CaseError, \
    CaseNotFound, \
    ContentNotFound, \
    CaseStateError, \
    CaseNotCompletedError, \
    CertificateTemplateNotFound, \
    CertificateCreationError, \
    DraftNotFound, \
    CaseSyncThrottled

from .comment import CommentError, \
    CommentNotFound, \
    CommentEditNotSupported, \
    AcceptedAnswerError
from .reference import ReferenceDataException, \
    ReferenceDataReadError, \
    CommunicationSettingNotFound, \
    CommunicationChannelNotFound

from .iterable import IterableAPIException, \
    IterableMisconfiguredException, \
    IterableUpdateException, \
    IterableOverloadedException, \
    IterableUserNotFound, \
    IterableUnsupportedDeviceType, \
    IterableException

from .vimeo import VimeoError, VimeoVideoNotFound

from .firebase import FirebaseError

from .validation import UsernameNotAllowed
from .validation import FoundNotAllowedWord

from .specialties import SpecialtyError, InvalidSpecialty, InvalidProfession

from .lock import TaskLockedException, TaskUnlockException, TooManyRequests

from .notification import NotificationException, NotificationNotFound

from .flask import bp as general_exception_endpoints
