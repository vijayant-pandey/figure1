import logging

from celery import group
from celery.canvas import Signature
from sqlalchemy import func

from figure1.cache_config import cache_region
from figure1.common.activities.user_profile_activities import update_profile_cases_task
from figure1.common.firebase import do_firebase_sync
from figure1.common.helpers import CaseManagement
from figure1.common.helpers import CaseDetail
from figure1.common.mixpanel import send_mixpanel_event
from figure1.common.models.db import Case
from figure1.common.models.db import CaseAuthor
from figure1.common.models.db import Label
from figure1.common.models.db import MeshTerms
from figure1.common.models.firebase import FirebaseCollectionManager
from figure1.common.models.firebase.anonymous_authors_db import sync_user_anonymous_case_task
from figure1.common.types import CaseClassification
from figure1.common.types import CaseState
from figure1.common.types import MixpanelCaseEventData
from figure1.common.types import MixpanelEvent
from figure1.configuration import app_settings
from figure1.core import TaskBase
from figure1.core import celery_app
from figure1.notifications import log_case_state_changed_task
from figure1.notifications import notify_all_users_of_new_case_task
from figure1.notifications import notify_specialty_users_of_paging_case_task


fb = FirebaseCollectionManager()
logger = logging.getLogger(__name__)


class HandleDeadlock(Exception):
    pass


@celery_app.task(bind=True,
                 base=TaskBase,
                 name='figure1.frontend.case_state_change_events')
def on_case_state_change(self, case_uuid, from_state, to_state):
    task = None

    if to_state == CaseState.SC_APPROVED:
        user_activity_task = update_profile_cases_task.si(case_uuid=case_uuid)
        task = do_firebase_sync.si(uuid=case_uuid, firebasemodel="CaseDetailV2")
        task.link(user_activity_task)

    if to_state == CaseState.APPROVED:
        logger.info("Case state was set to approved, updating user activities")
        task = handle_case_approved(case_uuid=str(case_uuid), session=self.session)

    if from_state == CaseState.APPROVED or from_state == CaseState.SC_APPROVED:
        logger.info("Case state was set from approved to %s, removing from activity", to_state)
        task = handle_case_unapproved(case_uuid=str(case_uuid), session=self.session)

    if from_state == CaseState.SC_REVIEW and to_state == CaseState.SC_DRAFT:
        logger.info("Case state set back to draft, remove from firestore")
        task = do_firebase_sync.si(uuid=case_uuid, firebasemodel="CaseDetailV2")
    if isinstance(task, Signature):
        task.apply_async(countdown=10)


@cache_region.cache_on_arguments(expiration_time=30)
def handle_case_approved(case_uuid, session):
    """
    When a case is marked as approved, do this. This is normally triggered by a sqlalchemy event that watches for
    changes to case state, however it may also be triggered manually. To prevent duplicate events, execution is
    delayed by 10 seconds.
    :param case_uuid:
    :param session:
    :return:
    """
    case = session.query(Case).get(case_uuid)
    case_author_list_q = session.query(CaseAuthor).filter(CaseAuthor.case_uuid == case_uuid)
    case_specialty_names = CaseDetail.get_case_specialty_names(case_uuid=case_uuid, session=session)

    def _generate_event_given_author(the_author):
        return MixpanelCaseEventData(case_uuid=case.case_uuid,
                                     author_uuid=str(the_author.author_uuid) if the_author else None,
                                     author_username=the_author.author.username if the_author else None,
                                     case_classification=case.case_classification.value,
                                     case_specialties=case_specialty_names,
                                     title=case.content[0].caption,
                                     status=status,
                                     labels=[x.name for x in labels],
                                     paging_type='Page a Specialist' if case.is_paging_case else 'Normal Case')

    if not case.published_at:
        case.published_at = func.now()
    session.add(case)

    if app_settings.case_cme_enabled and case.case_classification == CaseClassification.MEDICAL:
        # set case_state=CaseState.APPROVED because there are chances of
        # the case.state(not committed yet) being CaseState.PENDING_NLP.
        CaseManagement.update_case_cme_label(case_uuid=case.case_uuid,
                                             case_state=CaseState.APPROVED,
                                             group_uuid=case.group_uuid,
                                             skip_commit=True,
                                             session=session)
    mesh_terms = session.query(MeshTerms).filter(MeshTerms.case_uuid == case_uuid).one_or_none()
    if hasattr(mesh_terms, 'approver_uid'):
        moderator_uid = mesh_terms.approver_uid
    else:
        moderator_uid = None

    labels = case.labels
    resolved_uuid = Label.get_resolved(session=session).label_uuid
    if any(x.label_uuid == resolved_uuid for x in labels):
        status = 'Resolved'
    else:
        status = 'Unresolved'

    task = do_firebase_sync.si(uuid=case_uuid, firebasemodel="CaseDetailV2")

    for a in case_author_list_q.all():
        event_data = _generate_event_given_author(the_author=a)
        task.link(send_mixpanel_event.si(user_uuid=a.author_uuid,
                                         event_name=MixpanelEvent.CASE_APPROVED.value,
                                         properties=event_data.dict(by_alias=True)))

    task.link(notify_all_users_of_new_case_task.si(case_uuid=case_uuid))
    task.link(log_case_state_changed_task.si(case_uuid=case_uuid,
                                             moderator_uid=moderator_uid,
                                             suppress_user_notification=False))
    if case.group_uuid:
        return task
    else:
        task.link(update_profile_cases_task.si(case_uuid=case_uuid))
        if case.is_anonymous:
            for a in case_author_list_q.all():
                task.link(sync_user_anonymous_case_task.si(user_uuid=str(a.author_uuid), case_uuid=str(case.case_uuid)))

    if case.is_paging_case:
        task.link(notify_specialty_users_of_paging_case_task.si(case_uuid=case_uuid))
    return task


@cache_region.cache_on_arguments(expiration_time=10)
def handle_case_unapproved(case_uuid, session):
    case = session.query(Case).get(case_uuid)
    task_list = []
    if case:
        for a in case.authors:
            fb.set_fs_client(documents=[str(a.user_uuid), case_uuid], collections=['usersProfileDB', 'activity'])
            fb.delete_document()
            logger.info("Starting unapproval process for author %s", str(a.user_uuid))
            task_list.append(update_profile_cases_task.si(case_uuid=case_uuid))
        task_list.append(do_firebase_sync.si(uuid=case_uuid, firebasemodel="CaseDetailV2"))
    else:
        return None
    if task_list:
        return group(task_list)

    CaseManagement.update_case_cme_label(case_uuid=case.case_uuid,
                                         case_state=case.state,
                                         group_uuid=case.group_uuid,
                                         session=session)
