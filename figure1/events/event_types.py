from enum import Enum
from typing import Callable

from .comment_events import handle_comment_posted
from .comment_events import handle_comment_deleted
from .comment_events import handle_comment_reported
from .comment_events import handle_comment_updated
from .comment_events import handle_accepted_answer_updated
from .comment_events import handle_previous_accepted_answer_removed
from .comment_events import handle_accepted_answer_reviewed
from .comment_events import handle_accepted_answer_pending_review
from .user_events import handle_user_delete
from .user_events import handle_user_updated
from .user_events import handle_user_comm_prefs_updated
from .user_events import handle_user_topic_sub
from .user_events import handle_user_topic_unsub
from .user_events import handle_update_external_state
from .user_events import handle_update_internal_state
from .user_events import handle_user_email_updated
from .user_events import handle_onboarding_completed
from .user_events import handle_onboarding_started
from .user_events import handle_user_verification_state_change
from .user_events import trigger_user_saved_case_sync
from .user_events import handle_user_uid_set
from .user_events import sync_user_profile

from .case_events import handle_case_approved

from .aggregation_events import regenerate_user_profile
from .aggregation_events import generate_recommended_case
from .aggregation_events import on_new_comment
from .aggregation_events import on_new_comment_task
from .aggregation_events import on_new_reaction
from .aggregation_events import on_new_reaction_task
from .aggregation_events import on_case_save
from .aggregation_events import on_case_save_task


class AggregationEvents(Enum):
    GENERATE_USER_PROFILE: Callable = regenerate_user_profile
    GENERATE_RECOMMENDATION: Callable = generate_recommended_case
    ON_NEW_COMMENT: Callable = on_new_comment
    ON_NEW_COMMENT_TASK: Callable = on_new_comment_task
    ON_NEW_REACTION: Callable = on_new_reaction
    ON_NEW_REACTION_TASK: Callable = on_new_reaction_task
    ON_CASE_SAVE: Callable = on_case_save
    ON_CASE_SAVE_TASK: Callable = on_case_save_task


class CommentEvents(Enum):
    COMMENT_POSTED: Callable = handle_comment_posted
    COMMENT_DELETED: Callable = handle_comment_deleted
    COMMENT_REPORTED: Callable = handle_comment_reported
    COMMENT_UPDATED: Callable = handle_comment_updated
    ACCEPTED_ANSWER_UPDATED: Callable = handle_accepted_answer_updated
    PREVIOUS_ACCEPTED_ANSWER_REMOVED: Callable = handle_previous_accepted_answer_removed
    ACCEPTED_ANSWER_REVIEWED: Callable = handle_accepted_answer_reviewed
    ACCEPTED_ANSWER_PENDING_REVIEW: Callable = handle_accepted_answer_pending_review


class UserEvents(Enum):
    USER_DELETED: Callable = handle_user_delete
    USER_UPDATED: Callable = handle_user_updated
    USER_SUBSCRIBE: Callable = handle_user_topic_sub
    USER_UNSUBSCRIBE: Callable = handle_user_topic_unsub
    USER_COMM_PREFS_UPDATED: Callable = handle_user_comm_prefs_updated
    USER_EXTERNAL_UPDATE: Callable = handle_update_external_state
    USER_STATE_UPDATE: Callable = handle_update_internal_state
    USER_EMAIL_UPDATED: Callable = handle_user_email_updated
    USER_ONBOARDING_COMPLETED: Callable = handle_onboarding_completed
    USER_ONBOARDING_STARTED: Callable = handle_onboarding_started
    USER_VERIFICATION_STATE_CHANGE: Callable = handle_user_verification_state_change
    USER_SAVED_CASE_SYNC: Callable = trigger_user_saved_case_sync
    USER_UID_SET: Callable = handle_user_uid_set
    USER_PROFILE_SYNC: Callable = sync_user_profile


class CaseEvents(Enum):
    CASE_APPROVED: Callable = handle_case_approved
