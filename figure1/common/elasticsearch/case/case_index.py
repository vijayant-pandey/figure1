import logging
from typing import Optional

from celery import chain
from celery import group
from celery.canvas import Signature
from elasticsearch import helpers
from elasticsearch.exceptions import NotFoundError
from pydantic import ValidationError

from figure1.common.helpers import CampaignDetail
from figure1.common.helpers import CaseDetail
from figure1.common.models.db import CampaignCase
from figure1.common.models.db import Case
from figure1.common.models.db import CaseReaction
from figure1.common.models.db import ElasticSearchQueue
from figure1.configuration import es_settings
from figure1.core import celery_app
from figure1.core import es
from figure1.core import managed_session
from figure1.exceptions import CaseError
from figure1.exceptions import CaseNotFound
from figure1.store import IndexQueue
from .case_index_schema import CaseMapSchema
from .domain import update_case_reaction
from ..base import BaseIndex
from ..tasks import ElasticsearchTaskBase

logger = logging.getLogger('elasticsearch.index.cases')


def startup() -> Optional[Signature]:
    sync_es = CaseIndex()
    if not sync_es.index_name:
        logger.warning("No index name found, generating new index")
        new_index = create_new_case_index()
        new_index_tasks = populate_new_case_index(index_name=new_index)
        return chain(new_index_tasks,
                     switch_elasticsearch_index_task.si(index_name=new_index))
    else:
        logger.info("Using concrete index %s", sync_es.index_name)
        return None


@celery_app.task(base=ElasticsearchTaskBase, name='figure1.backend.cases.switch_index')
def switch_elasticsearch_index_task(index_name):
    switch_elasticsearch_index(index_name=index_name)


@celery_app.task(base=ElasticsearchTaskBase, name='figure1.backend.cases.bulk_insert')
def run_bulk_updates_task(index_name):
    """
    Returns none if no queue has been created, otherwise runs bulk updates
    """
    q = IndexQueue(index_alias=es_settings.cases_alias, index_name=index_name)
    if q.get_queue_count() <= 0:
        logger.error("No indexing queue found or none created")
        return None
    else:
        logger.error("Start case index with %s items pending", q.get_queue_count())
        run_bulk_updates(index_name=index_name)


@managed_session
def run_bulk_updates(index_name, session=None, create_queue=False):
    """
    If create_queue is True, then a queue is created. When this is passed, it is not safe to run this multiple times
    simultaneously.

    This runs until the queue is empty, it is safe to run this in multiple threads or multiple celery tasks

    """
    sync_es = CaseIndex(index_name=index_name)
    if create_queue is True:
        sync_es.create_queue_items(session=session)
    q = IndexQueue(index_alias=es_settings.cases_alias, index_name=index_name)
    remaining = q.get_queue_count()
    if not remaining:
        return
    while True:
        bulk_update = helpers.bulk(es,
                                   actions=sync_es.get_es_bulk_insert_documents(id_list=[], session=session),
                                   index=index_name,
                                   stats_only=True,
                                   max_retries=5,
                                   yield_ok=False,
                                   chunk_size=200)

        remaining = q.get_queue_count()
        if not remaining:
            logger.error("Bulk update complete")
            break
        else:
            logger.error(f"Remaining {remaining}")
        logger.error(f"processed: {bulk_update[0]}, errors: {bulk_update[1]}, remaining: {remaining}")
    return f"processed: {bulk_update[0]}, errors: {bulk_update[1]}, remaining: {remaining}"


@managed_session
def populate_new_case_index(workers=4, session=None, index_name=None) -> Signature:
    """
    If index name is passed, then this index is populated. This will fail if run against an active index if there are
    any updates to the index while it is being populated. This is due to how the bulk insert commands run.

    If no index name is passed, a new concrete index is created.
    """
    if index_name is None:
        sync_es = CaseIndex(create_index=True)
    else:
        sync_es = CaseIndex(index_name=index_name)

    idx = sync_es.index_name
    sync_es.create_queue_items(session=session)
    case_idx_group = []
    try:
        workers = int(workers)
    except TypeError:
        workers = 4

    for i in range(workers):
        case_idx_group.append(run_bulk_updates_task.si(index_name=idx))
    logger.error("Return group of %s workers", workers)
    return group(*case_idx_group)


def create_new_case_index():
    """
    Create and return a new concrete index.
    """
    return CaseIndex(create_index=True).index_name


@managed_session
def _update_index_data(index_name, session):
    sync_es = CaseIndex(index_name=index_name)
    sync_es.add_moderation_data(session=session)
    sync_es.refresh_campaign_data(session=session)
    sync_all_case_reactions(session=session)


def switch_elasticsearch_index(index_name):
    """
    Update the aliases to point to a new concrete index.
    """
    sync_es = CaseIndex(index_name=index_name)
    sync_es.add_aliases()
    sync_es.switch_active_index(index_name=index_name)
    _update_index_data(index_name=index_name)


def sync_all_case_reactions(session):
    for c in session.query(CaseReaction.case_uuid) \
            .filter(CaseReaction.deleted_at.is_(None)) \
            .group_by(CaseReaction.case_uuid) \
            .all():
        reactions = CaseReaction.get_case_reactions(case_uuid=c[0], session=session)
        update_case_reaction(case_uuid=c[0], reaction=reactions)


class CaseIndex(BaseIndex):
    index_alias = es_settings.cases_alias

    def __repr__(self):
        return f"Case index alias is {self.index_alias}, index name is {self.index_name}"

    def __init__(self, index_name=None, create_index=False):
        super().__init__()
        if create_index:
            self.index_name = self.create_elasticsearch_index()

        elif not index_name:
            self.index_name = self.get_active_index()
        else:
            self.index_name = index_name

    @property
    def index_map_data(self):
        return CaseMapSchema.case_map_data

    def create_queue_items(self, session):
        q = IndexQueue(index_alias=self.index_alias, index_name=self.index_name)
        case_list = session.query(Case.case_uuid)
        cl = list(case_list.yield_per(10000).all())
        q.write_queue_items(items=[str(x[0]) for x in cl])

    def add_aliases(self):
        viewable_cases = {
            "bool": {
                "filter": [
                    {
                        "terms": {
                            "caseState": ["APPROVED"]
                        }
                    },
                    {
                        "range": {
                            "publishedAt": {"lte": "now/d"}
                        }
                    }
                ]
            }
        }

        approved_sponsored_content = {
            "bool": {
                "filter": [
                    {
                        "terms": {
                            "caseState": ["SC_APPROVED"]
                        }
                    },
                    {
                        "range": {
                            "publishedAt": {'lte': 'now/d'}
                        }
                    },
                    {
                        "nested": {
                            "path": "campaignSettings",
                            "query": {
                                "range": {
                                    "campaignSettings.startDate": {
                                        "lte": "now/d"
                                    }
                                }
                            }
                        }
                    },
                    {
                        "bool": {
                            "should": [
                                {
                                    "nested": {
                                        "path": "campaignSettings",
                                        "query": {
                                            "range": {
                                                "campaignSettings.endDate": {
                                                    "gt": "now/d"
                                                }
                                            }
                                        }
                                    }
                                },
                                {
                                    "bool": {
                                        "must_not": {
                                            "nested": {
                                                "path": "campaignSettings",
                                                "query": {
                                                    "exists": {
                                                        "field": "campaignSettings.endDate"
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        }
        logger.error("Index name is %s", self.index_name)
        self.add_filtered_alias(index_name=self.index_name,
                                alias_name='newcases_public',
                                alias_filter=viewable_cases)

        self.add_filtered_alias(index_name=self.index_name,
                                alias_name='newcases_sponsored_content',
                                alias_filter=approved_sponsored_content)

    def get_queue_items(self, session):
        for c in session.query(ElasticSearchQueue) \
                .filter(ElasticSearchQueue.index_alias == self.index_alias) \
                .filter(ElasticSearchQueue.indexed.is_(False)) \
                .filter(ElasticSearchQueue.index_name == self.index_name) \
                .with_for_update(skip_locked=True).limit(1000):
            yield c

    def get_es_bulk_insert_documents(self, session, id_list):
        q = IndexQueue(index_alias=self.index_alias, index_name=self.index_name)
        if q.get_queue_count() < 1:
            return StopIteration
        while q.get_queue_count():
            c = q.get_next_item()
            if not c:
                logger.error("Queue count is %s", q.get_queue_count())
                break
            try:
                case = self._fetch_case(case_uuid=c, session=session)
            except (CaseNotFound, CaseError):
                logger.exception("Error fetching case %s - skipping", c)
                continue
            except ValidationError:
                logger.exception("Error validating case structure for case %s: ", c)
                continue
            if case:
                case.update({'_id': case['caseUuid']})
                logger.debug("Processing case %s", c)
                yield case
            else:
                continue

    def get_es_insert_documents(self, session, id_list):
        for case_id in id_list:
            try:
                case = self._fetch_case(case_uuid=case_id, session=session)
            except ValidationError:
                continue
            if case:
                yield case
            else:
                continue

    def get_es_insert_document(self, session, id):
        return self._fetch_case(case_uuid=id, session=session)

    def add_moderation_data(self, session):
        u = CaseDetail.elasticsearch_moderation_case_detail(session=session)
        for case_uuid in u:
            try:
                es.update(index=self.index_name, id=case_uuid, retry_on_conflict=5, body={
                    "doc": {**u[case_uuid]}
                })
                logger.info(f"Added to case uuid {case_uuid}")
            except Exception as e:
                logger.error(f"Failed to insert to case {case_uuid} - error {e} - index is {self.index_name}")

    def refresh_campaign_data(self, session):
        for tactic_uuid in session.query(CampaignCase).filter(CampaignCase.deleted_at.is_(None)).all():
            update = CampaignDetail.tactic_details(case_uuid=tactic_uuid.case_uuid, session=session)
            try:
                es.update(index=self.index_name,
                          id=str(tactic_uuid.case_uuid),
                          body={"doc": {"campaignSettings": update.dict()}})
            except NotFoundError:
                logger.error("Tactic %s not found", tactic_uuid.case_uuid)
                continue

    def _fetch_case(self, case_uuid, session):
        return CaseDetail.elasticsearch_case_detail(case_uuid=case_uuid, session=session)
