import enum


class UserNotificationState(enum.Enum):
    NEW = 'new'
    ACKNOWLEDGED = 'acknowledged'
    READ = 'read'


class UserNotificationType(enum.Enum):
    APPROVE = 'approved'
    CASE_DELETE = 'case_delete'
    CASE_NOT_DIAGNOSIS_CHOSEN = 'case_not_diagnosis_chosen'
    CASE_NOT_ACCEPTED_ANSWER_CHOSEN = 'case_not_accepted_answer_chosen'
    COMMENT = 'comment'
    COMMENT_DELETE = 'comment_delete'
    COMMENT_REPLY = 'comment_reply'
    COMMENT_REPLY_OP = 'comment_reply_op'
    COMMENT_SAVED_CASE = 'comment_saved_case'
    COMMENT_SAVED_CASE_OP = 'comment_saved_case_op'
    NEW_CASE_FOLLOWED_USER = 'new_case_followed_user'
    NEW_CASE_USER_SAVED_CASE = 'new_case_user_saved_case'
    NEW_CASE_GROUP = 'new_case_group'
    NEW_FOLLOWER = 'new_followed'
    PAGING = 'paging'
    REACT = 'react'
    REJECT = 'reject'
    SAVED_CASE_UPDATE = 'saved_case_update'
    COMMENTED_CASE_DIAGNOSIS = 'commented_case_diagnosis'
    SAVED_CASE_DIAGNOSIS = 'saved_case_diagnosis'
    LIKED_CASE_DIAGNOSIS = 'liked_case_diagnosis'
    PROFESSION_CHANGE_APPROVED = 'profession_change_approved'
    GROUP_INVITE_ACCEPTED = 'group_invite_accepted'
    NEW_ACCEPTED_ANSWER_SELECTED = 'new_accepted_answer_selected'
    NEW_ACCEPTED_ANSWER_COMMENTED_CASE = 'new_accepted_answer_commented_case'
    NEW_ACCEPTED_ANSWER_LIKED_CASE = 'new_accepted_answer_liked_case'
    NEW_ACCEPTED_ANSWER_SAVED_CASE = 'new_accepted_answer_saved_case'
    ACCEPTED_ANSWER_DELETED = 'accepted_answer_deleted'


class NonPublicNotificationTypes(enum.Enum):
    """
    Non-public notification types can not be sent if a case is anonymous.
    """
    NEW_CASE_FOLLOWED_USER = UserNotificationType.NEW_CASE_FOLLOWED_USER
    NEW_CASE_USER_SAVED_CASE = UserNotificationType.NEW_CASE_USER_SAVED_CASE
    NEW_CASE_GROUP = UserNotificationType.NEW_CASE_GROUP
