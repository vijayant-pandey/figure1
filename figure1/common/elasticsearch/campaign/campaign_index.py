import logging
from sqlite3 import IntegrityError

from elasticsearch import helpers
from sqlalchemy import select, literal

from ..base import BaseIndex
from figure1.common.models.db import ElasticSearchQueue, Campaign
from ..tasks import ElasticsearchTaskBase
from figure1.core import celery_app
from figure1.common.helpers.campaign import CampaignDetail
from figure1.configuration import es_settings
from .campaign_index_schema import CampaignMapSchema

logger = logging.getLogger('elasticsearch.index.campaigns')


@celery_app.task(bind=True, base=ElasticsearchTaskBase, name='figure1.backend.campaigns.startup')
def campaign_startup(self):
    sync_es = CampaignIndex()
    index_name = sync_es.get_active_index(session=self.session)
    logging.info(f"Checking index name {index_name}")
    if index_name:
        logger.info("Active index exists, nothing to do")
    else:
        logging.info("No index name found, generating new index")
        create_new_campaign_index.delay()


@celery_app.task(bind=True, base=ElasticsearchTaskBase, name='figure1.backend.campaigns.create')
def create_new_campaign_index(self):
    sync_es = CampaignIndex()
    sync_es.create_index(session=self.session)
    idx = sync_es.index_name
    return [
        run_bulk_updates.apply_async(kwargs={'index_name': idx}),
    ]


@celery_app.task(bind=True, base=ElasticsearchTaskBase, name='figure1.backend.campaigns.bulk_insert')
def run_bulk_updates(self, index_name):
    sync_es = CampaignIndex()
    while True:
        sync_es.index_name = index_name

        bulk_update = helpers.bulk(self.es_client,
                                   actions=sync_es.get_es_bulk_insert_documents(id_list=[], session=self.session),
                                   index=index_name,
                                   stats_only=True,
                                   max_retries=5,
                                   chunk_size=1000)
        remaining = sync_es.get_queue_size(index_name=index_name, session=self.session)
        logger.info(f"Remaining {remaining}")
        logger.info(f"processed: {bulk_update[0]}, errors: {bulk_update[1]}, remaining: {remaining}")
        if not bulk_update[0]:
            logger.info("Nothing processed, exiting")
            break
        if not remaining:
            logger.info(f"Complete - switching index")
            sync_es.switch_active_index(index_name=index_name)
            return {'processed': bulk_update[0], 'errors': bulk_update[1], 'remaining': remaining}
        logger.info({'processed': bulk_update[0], 'errors': bulk_update[1], 'remaining': remaining})


class CampaignIndex(BaseIndex):
    index_alias = es_settings.campaign_alias
    _index_name = None

    @property
    def index_name(self):
        return self._index_name

    @index_name.setter
    def index_name(self, val):
        self._index_name = val

    @index_name.getter
    def index_name(self):
        if self._index_name is None:
            ai = self.get_active_index()
            if not ai:
                return None
            i = ai.get('idx_name')
            if i:
                return i
            return None
        return self._index_name

    @property
    def index_map_data(self):
        return CampaignMapSchema.campaign_map_data

    def create_queue_items(self, session):
        session.query(ElasticSearchQueue).filter(ElasticSearchQueue.index_name == self.index_name).delete()
        session.commit()

        campaign = Campaign.__table__
        queue = ElasticSearchQueue.__table__
        try:
            session.execute(queue.insert().from_select(
                ['case_uuid', 'index_alias', 'index_name', 'indexed'],
                select([campaign.c.campaign_uuid, literal(self.index_alias), literal(self.index_name), False])
            ))
            session.commit()
        except IntegrityError as ie:
            logger.error("Failed to insert")
            raise ie

    def get_queue_items(self, session):
        for c in session.query(ElasticSearchQueue) \
                .filter(ElasticSearchQueue.index_alias == self.index_alias) \
                .filter(ElasticSearchQueue.indexed.is_(False)) \
                .filter(ElasticSearchQueue.index_name == self.index_name) \
                .with_for_update(skip_locked=True).limit(1000):
            yield c

    def get_es_bulk_insert_documents(self, session, id_list):
        campaign_list = self.get_queue_items(session=session)
        if not campaign_list:
            return []
        for c in campaign_list:
            campaign = self._fetch_campaign(campaign_uuid=c.case_uuid, session=session)
            c.indexed = True
            if campaign:
                campaign.update({'_id': campaign['campaignUuid']})
                yield campaign
            else:
                continue
        session.commit()

    def get_es_insert_documents(self, session, id_list):
        for campaign_uuid in id_list:
            comment = self._fetch_campaign(campaign_uuid=campaign_uuid, session=session)
            if comment:
                yield comment

    def get_es_insert_document(self, session, id):
        return self._fetch_campaign(campaign_uuid=id, session=session)

    def _fetch_campaign(self, campaign_uuid, session):
        return CampaignDetail.elasticsearch_campaign(campaign_uuid=campaign_uuid, session=session)
