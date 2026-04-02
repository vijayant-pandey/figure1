import logging

from elasticsearch import helpers
from ..base import BaseIndex, MappingData
from figure1.core import celery_app
from figure1.common.models.db import SpecialtyTreeV2
from figure1.common.types import SpecialtyTreeModel
from figure1.configuration import es_settings
from ..tasks import ElasticsearchTaskBase

specialty_index_alias = es_settings.public_specialty_alias
logger = logging.getLogger('elasticsearch.index.specialty')


@celery_app.task(bind=True, base=ElasticsearchTaskBase, name='figure1.backend.specialty.startup')
def specialty_startup(self):
    sync_es = SpecialtyIndex()
    index = sync_es.get_active_index(session=self.session)
    if not index:
        logger.info("No index found, generating new index")
        create_new_specialty_index.delay()


@celery_app.task(bind=True, base=ElasticsearchTaskBase, name='figure1.backend.specialty.create')
def create_new_specialty_index(self):
    sync_es = SpecialtyIndex()
    sync_es.create_index(session=self.session)
    idx = sync_es.index_name
    return run_bulk_updates.apply_async(kwargs={'index_name': idx})


@celery_app.task(bind=True, base=ElasticsearchTaskBase, name='figure1.backend.specialty.bulk_insert')
def run_bulk_updates(self, index_name):
    sync_es = SpecialtyIndex()
    sync_es.index_name = index_name
    bulk_update = helpers.bulk(self.es_client,
                               actions=sync_es.get_es_bulk_insert_documents(id_list=[], session=self.session),
                               index=index_name,
                               stats_only=True,
                               max_retries=5,
                               chunk_size=200)
    logger.info(f"processed: {bulk_update[0]}, errors: {bulk_update[1]}")
    sync_es.switch_active_index(index_name=index_name)
    logger.info({'processed': bulk_update[0], 'errors': bulk_update[1]})


class SpecialtyIndex(BaseIndex):
    index_alias = specialty_index_alias
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
        return MappingData.specialty_map_data

    def get_queue_items(self, session):
        pass

    def get_es_bulk_insert_documents(self, session, id_list):
        for t in session.query(SpecialtyTreeV2).all():
            td = {}
            to: SpecialtyTreeModel = t.as_object()
            for k, v in to:
                if k in ['profession', 'specialty', 'subspecialty']:
                    continue
                td.update({k: v})
            if to.profession:
                td.update({**to.profession.dict(exclude_none=True)})
            if to.specialty:
                td.update({**to.specialty.dict(exclude_none=True)})
            if to.subspecialty:
                td.update({**to.subspecialty.dict(exclude_none=True)})
            yield td
        return

    def get_es_insert_documents(self, session, id_list):
        pass

    def get_es_insert_document(self, session, id):
        pass
