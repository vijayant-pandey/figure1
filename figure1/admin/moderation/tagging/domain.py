import logging
from typing import Optional
from celery.canvas import Signature
from datetime import timezone, datetime
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm.exc import NoResultFound
from figure1.admin.moderation.cases.case_transition_handler import propagate_case_state_update
from figure1.common.elasticsearch import update_moderation_case_detail, update_case_fields
from figure1.common.helpers import CaseManagement
from figure1.core import managed_session
from figure1.common.models.db import MeshTerms, CaseSpecialtyV2, User, CaseNote, Case, CaseMeshTerms, PublicMeshTerms
from figure1.common.types import CaseState
from .mesh_on_demand import MeshDataAPI
from .mesh_tasks import clean_mesh_terms_by_case, add_publications_to_case_task

logger = logging.getLogger(__name__)


def update_elasticsearch_specialties(case_uuid, session):
    specialty_list_result = session.query(CaseSpecialtyV2.specialty_uuid) \
        .filter(CaseSpecialtyV2.case_uuid == case_uuid).all()
    specialty_list = [str(x[0]) for x in specialty_list_result]
    update_case_fields(case_uuid=case_uuid, case_field_name="specialtyUuids", case_field_value=specialty_list)


@managed_session
def set_specialties(specialties: list, case_uuid, session=None):
    for specialty in specialties:
        CaseSpecialtyV2.create(case_uuid=case_uuid,
                               specialty_uuid=specialty,
                               session=session)
    try:
        session.flush()
        update_elasticsearch_specialties(case_uuid=case_uuid, session=session)
        return {'success': 'Specialties set'}
    except DatabaseError as ie:
        logger.error(f"Failed to commit - {ie}")
        session.rollback()
        raise


@managed_session
def remove_specialties(specialties: list, case_uuid, session=None):
    for specialty in specialties:
        session.query(CaseSpecialtyV2) \
            .filter(CaseSpecialtyV2.case_uuid == case_uuid,
                    CaseSpecialtyV2.specialty_uuid == specialty).delete()
    try:
        session.flush()
        update_elasticsearch_specialties(case_uuid=case_uuid, session=session)
        return {'success': 'Specialties removed'}
    except DatabaseError as ie:
        logger.error(f"Failed to remove specialties - {ie}")
        session.rollback()
        raise


def _get_or_set_mesh_terms(term, case_uuid, session):
    """
    Given a mesh term, returns the id if it is found online or in the database. Otherwise returns None
    """
    mesh_term = PublicMeshTerms.find_mesh_terms(term, session=session)
    if mesh_term:
        logger.debug("Found id %s for term %s", mesh_term.mesh_term_id, term)
        return mesh_term.mesh_term_id
    else:
        m = MeshDataAPI(case_uuid=case_uuid, session=session)
        term_code = m.add_term(term)
        logger.info("Found id %s for term %s", term_code, term)
        return term_code if term_code else None


@managed_session
def clean_mesh_terms(case_uuid, session=None):
    """
    Takes mesh terms from an approved case, removes any that have been marked inactive, and corrects any that are
    not using the preferred label
    """
    case_update = {}
    if isinstance(case_uuid, list):
        for c in case_uuid:
            u = clean_mesh_terms_by_case(case_uuid=c, session=session)
            case_update.update({c: u})
    if isinstance(case_uuid, str):
        u = clean_mesh_terms_by_case(case_uuid=case_uuid, session=session)
        case_update.update({case_uuid: u})
    return case_update


def find_publications_for_case(case_uuid, return_task=False) -> Optional[Signature]:
    """
    Finds publications for a case. If mesh terms exist in the MeshTerms table, but not in the CaseMeshTerms, then
    the clean_mesh_terms process is run to create the necessary entries. If there are no mesh terms, this process
    will not attempt to fetch them.

    Optionally returns a task

    :param case_uuid: List of case_uuids or a single case_uuid
    :type case_uuid: str

    :param return_task: If set to true, return a celery task signature, otherwise execute asynchronously
    :type return_task: bool

    :return: Task signature or none.
    :rtype: Signature
    """
    task = None
    if isinstance(case_uuid, list):
        for c in case_uuid:
            if isinstance(task, Signature):
                task.link(add_publications_to_case_task.si(case_uuid=c))
            else:
                task = add_publications_to_case_task.si(case_uuid=c)
        if return_task:
            return task

    if isinstance(case_uuid, str):
        if isinstance(task, Signature):
            task.link(add_publications_to_case_task.si(case_uuid=case_uuid))

        else:
            task = add_publications_to_case_task.si(case_uuid=case_uuid)

        if return_task:
            return task

    task.apply_async()


@managed_session
def set_mesh_terms(mesh_terms: list, case_uuid, session=None):
    """
    Add new mesh terms to a case
    """
    existing_term_ids = set(list(CaseMeshTerms.get_mesh_ids_for_case(case_uuid=case_uuid, session=session)))
    new_term_ids = set()
    logger.debug("Existing mesh term ids %s", existing_term_ids)
    for msh_term in mesh_terms:
        term_code = _get_or_set_mesh_terms(term=msh_term, case_uuid=case_uuid, session=session)
        if term_code:
            logger.debug("Adding term code %s", term_code)
            new_term_ids.add(term_code)
        else:
            logger.error("No data found for term %s", msh_term)

    logger.debug("New terms to add %s", new_term_ids)
    logger.debug("Existing terms %s", existing_term_ids)
    terms_to_add = new_term_ids - existing_term_ids
    if terms_to_add:
        logger.debug("Adding terms %s", terms_to_add)
        CaseMeshTerms.add_new_terms(case_uuid=case_uuid,
                                    term_ids=list(terms_to_add),
                                    moderator_uuid=None,
                                    session=session)
    session.flush()
    mesh_terms = list(CaseMeshTerms.get_mesh_terms_for_case(case_uuid=case_uuid, session=session))
    update_case_fields(case_uuid=case_uuid, case_field_name="meshTerms", case_field_value=mesh_terms)
    return dict(success=mesh_terms)


@managed_session
def remove_mesh_terms(mesh_terms: list, case_uuid, session=None):
    """
    Remove mesh terms from a case
    """
    for msh_term in mesh_terms:
        term_code = _get_or_set_mesh_terms(term=msh_term, case_uuid=case_uuid, session=session)
        if term_code:
            CaseMeshTerms.mark_terms_deleted(case_uuid=case_uuid,
                                             term_ids=term_code,
                                             moderator_uuid=None,
                                             session=session)
        else:
            logger.error("No data found for term %s", msh_term)
    session.flush()
    mesh_terms = list(CaseMeshTerms.get_mesh_terms_for_case(case_uuid=case_uuid, session=session))
    update_case_fields(case_uuid=case_uuid, case_field_name="meshTerms", case_field_value=mesh_terms)
    return dict(success=mesh_terms)


@managed_session
def approve_mesh_terms(case_uuid, moderator_uid, session=None, publish_date: datetime = None):
    mesh_terms = list(CaseMeshTerms.get_mesh_terms_for_case(case_uuid=case_uuid, session=session))
    user = User.get_user_by_uid(user_uid=moderator_uid, session=session, raise_exception=True)
    try:
        case = session.query(Case).filter(Case.case_uuid == case_uuid).one()
    except NoResultFound:
        return {'error': 'No case found'}
    mt = MeshTerms()
    mt.case_uuid = case_uuid
    mt.approved_terms = mesh_terms
    mt.approver_uid = moderator_uid
    session.merge(mt)
    case.event_author_uuid = user.user_uuid
    case.state = CaseState.APPROVED
    if publish_date:
        case.published_at = publish_date.astimezone(timezone.utc)
    session.add(case)
    session.flush()

    logger.info("Adding publications to mesh terms")
    add_publications_to_case_task.apply_async(kwargs=dict(case_uuid=case_uuid), countdown=5)
    return dict(success=mesh_terms)


@managed_session
def force_set_case_state(case_uuid, session=None):
    case = session.query(Case).get(case_uuid)
    if case:
        case.state = CaseState.PENDING_TAGGING
        session.add(case)
    try:
        session.flush()
    except Exception as e:
        logger.error(f"Failed to update case_state {e}")
        return {'error': 'Case state update failed'}
    try:
        propagate_case_state_update(case_uuid=case_uuid)
    except Exception as pe:
        logger.error(f"Failed to propagate case state changes {pe}")
        return {'error': 'failed to propagate to PENDING_TAGGING'}

    return {'success': "Updated case state to PENDING_TAGGING"}


@managed_session
def flag_case_for_moderator(case_uuid, moderator_uid, case_note=None, session=None):
    user = User.get_user_by_uid(user_uid=moderator_uid, session=session, raise_exception=True)
    tagger_id = str(user.user_uuid)
    try:
        case = session.query(Case).filter(Case.case_uuid == case_uuid).one()
    except NoResultFound:
        return {'error': "No case found"}
    default_note = f'This case has been returned to moderation from tagging : {tagger_id}'
    if case_note:
        note = default_note + '\n--Tagger Note--\n' + case_note
    else:
        note = default_note
    case.state = CaseState.FLAGGED_TAGGER

    try:
        propagate_case_state_update(case_uuid=case_uuid, moderator_uid=moderator_uid)
    except Exception as pe:
        logger.error(f"Failed to propagate case state changes {pe}")
        return {'error': 'failed to propagate FLAGGED_TAGGER case'}

    CaseNote.create(case_uuid=case_uuid, moderator_uuid=user.user_uuid, text=note, session=session)
    try:
        session.add(case)
        session.commit()
    except Exception as ie:
        logger.error(f"Failed to update case state {ie}")
        session.rollback()
        return {'error': 'Case state update failed'}
    update_moderation_case_detail(case_uuid=case_uuid, session=session)
    return {'success': 'Case flagged'}


@managed_session
def reject_flagged_case(case_uuid, moderator_uid, case_note=None, session=None):
    user = User.get_user_by_uid(user_uid=moderator_uid, session=session)
    case = session.query(Case).filter(Case.case_uuid == case_uuid).one_or_none()
    if not case:
        return {'error': "No case found"}
    if not user:
        return {'error': 'User not found'}
    tagger_id = str(user.user_uuid)
    default_note = f'This case has been returned to moderation from tagging : {tagger_id}'
    if case_note:
        note = default_note + '\n--Manager Note--\n' + case_note
    else:
        note = default_note
    case.state = CaseState.PENDING_APPROVAL

    try:
        propagate_case_state_update(case_uuid=case_uuid, moderator_uid=moderator_uid)
    except Exception as ie:
        logger.error(f"Failed to update case state {ie}")
        session.rollback()
        return {'error': 'Case state propagation failed'}

    CaseNote.create(case_uuid=case_uuid, moderator_uuid=user.user_uuid, text=note, session=session)
    try:
        session.add(case)
        session.commit()
    except Exception as ie:
        logger.error(f"Failed to update case state {ie}")
        session.rollback()
        return {'error': 'Case state update failed'}
    update_moderation_case_detail(case_uuid=case_uuid, session=session)
    return {'success': 'Case rejected back to moderation'}
