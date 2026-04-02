import logging
from figure1.common.firebase import do_firebase_sync
from figure1.notifications import log_case_state_changed_task

logger = logging.getLogger("figure1.moderation.cases.case_transition_handler")


def propagate_case_state_update(
        case_uuid,
        moderator_uid=None,
        suppress_user_notification=True,
        return_task=False):
    task = do_firebase_sync.si(uuid=case_uuid, firebasemodel="CaseDetailV2")
    task.link(log_case_state_changed_task.si(case_uuid=case_uuid,
                                             moderator_uid=moderator_uid,
                                             suppress_user_notification=suppress_user_notification))
    if return_task:
        return task
    else:
        task.apply_async()
