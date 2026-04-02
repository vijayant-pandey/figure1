import logging
from typing import Iterator
from celery.canvas import Signature
from http.client import RemoteDisconnected
from googleapiclient.errors import HttpError
from elasticsearch.exceptions import NotFoundError
from .mesh_on_demand import MeshDataAPI, MeshError, PublicationSearch, PublicationSearchOverloaded
from figure1.core import TaskBase, celery_app
from figure1.common.models.db import Case, CaseMeshTerms, CasePublications, Publications, MeshTerms, PublicMeshTerms
from figure1.common.types import CaseState
from figure1.common.elasticsearch import update_case_fields
from figure1.admin.moderation.cases.case_transition_handler import propagate_case_state_update

logger = logging.getLogger(__name__)


@celery_app.task(bind=True,
                 base=TaskBase,
                 autoretry_for=(PublicationSearchOverloaded,),
                 retry_backoff=True,
                 name='figure1.backend.publications.fetch_case_publications')
def add_publications_to_case_task(self, case_uuid):
    if self.session.query(CasePublications).filter(CasePublications.case_uuid == case_uuid).count():
        logger.error("Publications already exist for case_uuid %s", case_uuid)
        return None
    add_publications_to_case(case_uuid=case_uuid, session=self.session)
    logger.info("Finished adding publications")


@celery_app.task(bind=True,
                 base=TaskBase,
                 name='figure1.backend.mesh_terms',
                 autoretry_for=(RemoteDisconnected, MeshError, HttpError),
                 retry_backoff=True)
def fetch_mesh_tags_task(self, case_uuid=None, force=False):
    fetch_mesh_tags(case_uuid=case_uuid, force=force, session=self.session)


def clean_mesh_terms_by_case(case_uuid, session):
    """
    Takes existing mesh terms entries and ensures that the terms are recorded and that the reference is recorded in the
    CaseMeshTerms table.
    :param case_uuid:
    :param session:
    :return:
    """
    existing_approved_mesh_entry: MeshTerms = session.query(MeshTerms) \
        .filter(MeshTerms.case_uuid == case_uuid) \
        .one_or_none()
    if existing_approved_mesh_entry:
        mesh_entry = set()
        approved_mesh_terms = existing_approved_mesh_entry.approved_terms
        logger.debug("Existing mesh terms %s", approved_mesh_terms)
        for term in approved_mesh_terms:
            mesh_term_id = _get_or_set_mesh_terms(term, case_uuid=case_uuid, session=session)
            if mesh_term_id:
                mesh_entry.add(mesh_term_id)
            else:
                logger.error("No mesh code found for term %s", term)
        if mesh_entry:
            CaseMeshTerms.add_new_terms(case_uuid=case_uuid,
                                        term_ids=list(mesh_entry),
                                        moderator_uuid=None,
                                        session=session)
        session.flush()
        case_mesh_terms = list(CaseMeshTerms.get_mesh_terms_for_case(case_uuid=case_uuid, session=session))
        logger.debug("Adding case mesh terms %s", case_mesh_terms)
        update_case_fields(case_uuid=case_uuid, case_field_name="meshTerms", case_field_value=case_mesh_terms)
        existing_approved_mesh_entry.approved_terms = case_mesh_terms
        session.add(existing_approved_mesh_entry)
        session.flush()
        return dict(mesh_terms=case_mesh_terms)
    else:
        logger.error("Unable to find approved mesh term entry for case_uuid %s", case_uuid)
        return dict(mesh_terms=[], error='No case found')


def fetch_mesh_tags(case_uuid=None, force=False, return_task=False, session=None):
    """Fetch mesh tags

    This task is responsible for calling the mesh api which fetches mesh tags for a case. Before returning, it will
    update the case state to CaseState.PENDING_TAGGING.

    There are two modes of operation, the most common is passing a case_uuid in to update a single case, part of this
    is passing in the force flag which simply ignores the state of the case. The other mode is not passing in a
    case_uuid, this is done by a scheduled task currently, this mode acts as a sweeper where any case in PENDING_NLP
    state is run through the mesh api.

    :param case_uuid: If present, mesh tags are looked up for this case, if not present, the database is scanned for
        cases that have the status PENDING_NLP
    :type case_uuid: str

    :param force: This runs the case_uuid passed in without checking state, as a result, the state is not modified.
    :type force: bool

    :param return_task: When a case is updated, a propagate_case_state task is generated, this task is run when the
        lookup finishes by default, but if return_task is True, it returns the task signature.
    :type return_task: Signature

    :param session: The database session, this is the only non-optional parameter.
    :type session: Session

    :returns: None, Signature
    """
    if session is None:
        logger.error("No session passed, returning")
        return

    task = None
    logger.debug("Starting fetch mesh tags task with arguments %s, %s", case_uuid, force)
    if case_uuid:
        logger.debug("Looking for case_uuid %s", case_uuid)
        case = session.query(Case).get(case_uuid)
        m = MeshDataAPI(case_uuid=case_uuid, session=session)
        if force:
            logger.info("Forcing mesh terms fetch")
            _mark_existing_case_terms_deleted(case_uuid=case_uuid, session=session)
            logger.debug("Marked existing case mesh terms deleted")
            m.parse_mesh_data()
            logger.info("Completed mesh term parsing")

        elif case.state == CaseState.PENDING_NLP:
            logger.info("Running mesh terms task for case %s", case_uuid)
            m.parse_mesh_data()
            logger.info("Mesh terms task complete for case %s", case_uuid)
            case.state = CaseState.PENDING_TAGGING
            session.add(case)
            task = propagate_case_state_update(case_uuid=str(case.case_uuid), return_task=True)

        elif case.state != CaseState.PENDING_NLP:
            return {'success': f'Nothing to do.  Mesh tags not required for state {case.state}'}
        session.flush()
        _set_elasticsearch_terms(case_uuid, session)
    else:
        logger.debug("No case_uuid passed, checking for pending cases")
        for case in _get_pending_nlp(session=session):
            if case:
                case_uuid = str(case.case_uuid)
                logger.info("Running mesh tags for case %s", case_uuid)
                m = MeshDataAPI(case_uuid=case_uuid, session=session)
                m.parse_mesh_data()
                logger.info("Mesh task complete for case %s", case_uuid)
                case.state = CaseState.PENDING_TAGGING
                session.merge(case)
                session.flush()
                _set_elasticsearch_terms(case_uuid, session)
                if isinstance(task, Signature):
                    t = propagate_case_state_update(case_uuid=str(case.case_uuid), return_task=True)
                    task.link(t)
                else:
                    task = propagate_case_state_update(case_uuid=str(case.case_uuid), return_task=True)

    session.flush()
    if isinstance(task, Signature):
        logger.info("Running case state updates task")
        if return_task:
            return task
        else:
            task.apply_async()


def add_publications_to_case(case_uuid, session):
    """
    Given a case_uuid with mesh terms, look for publications for that case_uuid

    :param case_uuid:
    :param session:
    :return:
    """

    def add_publications(pub_med_ids):
        if pub_med_ids:
            for ix, pmid in enumerate(pub_med_ids):
                cp = CasePublications()
                cp.case_uuid = case_uuid
                cp.pub_med_id = pmid
                cp.display_order = ix
                session.merge(cp)
            session.flush()
            return True
        return False

    logger.info("Searching for publications for case %s", case_uuid)
    problem_mesh_terms = list(CaseMeshTerms.get_mesh_terms_for_case(case_uuid=case_uuid,
                                                                    session=session,
                                                                    mesh_term_type='PROBLEM'))
    all_mesh_terms = list(CaseMeshTerms.get_mesh_terms_for_case(case_uuid=case_uuid,
                                                                session=session,
                                                                mesh_term_type='ALL'))
    if problem_mesh_terms:
        pub_med_ids = find_publications_for_mesh_terms(terms=problem_mesh_terms, session=session)
        if add_publications(pub_med_ids) is True:
            logger.info("Added publications for problem mesh terms")
            return
    if all_mesh_terms:
        pub_med_ids = find_publications_for_mesh_terms(terms=all_mesh_terms, session=session)
        return add_publications(pub_med_ids)


def find_publications_for_mesh_terms(terms, session):
    """
    Returns a list of publication ids to fetch summaries for.
    :param terms:
    :return:
    """
    fetch_summaries = []
    results = PublicationSearch.search_terms(terms=terms)
    for pubmedid in results.pubMedIds:
        if not Publications.q.get(pubmedid):
            fetch_summaries.append(pubmedid)
    if fetch_summaries:
        for p in fetch_summaries_for_pub_med_ids(fetch_summaries):
            session.add(p)
        session.flush()
    return results.pubMedIds


def fetch_summaries_for_pub_med_ids(pub_med_ids) -> Iterator[Publications]:
    """
    Given a list of pub_med_ids, yields an instantiated Publications class for each entry found.

    :param pub_med_ids:
    :return:
    """
    if not isinstance(pub_med_ids, list):
        raise ValueError("pub_med_ids must be a list")
    if not pub_med_ids:
        return None

    for summaries in PublicationSearch.lookup_summary(pubmedIds=pub_med_ids):
        for result in summaries.results:
            if result.error is not None:
                logger.error("Lookup of %s resulted in error %s", result.pubMedId, result.error)
            else:
                p = Publications()
                p.title = result.title
                p.pub_med_id = result.pubMedId
                yield p


def _mark_existing_case_terms_deleted(case_uuid, session):
    for term in session.query(CaseMeshTerms).filter(CaseMeshTerms.case_uuid == case_uuid).all():
        term.mark_deleted()
        session.add(term)
    session.flush()


def _set_elasticsearch_terms(case_uuid, session):
    mesh_terms = list(CaseMeshTerms.get_mesh_terms_for_case(case_uuid=case_uuid, session=session))
    try:
        update_case_fields(case_uuid=case_uuid, case_field_name="meshTerms", case_field_value=mesh_terms)
    except NotFoundError:
        logger.error("Failed to find elasticsearch case to update while fetching mesh terms")
    return mesh_terms


def _get_pending_nlp(session):
    for c in session.query(Case) \
            .filter(Case.state == CaseState.PENDING_NLP) \
            .order_by(Case.updated_at.asc()) \
            .with_for_update(skip_locked=True) \
            .all():
        logger.info("Returning %s to process", c.case_uuid)
        yield c


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
