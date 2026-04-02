import logging
from elasticsearch import helpers
from figure1.configuration import es_settings
from figure1.core import celery_app
from figure1.common.models.db import Country
from ..base import BaseIndex, MappingData
from ..tasks import ElasticsearchTaskBase

countries_alias = es_settings.public_countries_alias
logger = logging.getLogger('elasticsearch.index.public_country')


@celery_app.task(bind=True, base=ElasticsearchTaskBase, name='figure1.backend.public_country.startup')
def public_country_startup(self):
    sync_es = PublicCountries()
    index = sync_es.get_active_index(session=self.session)
    if not index:
        logger.info("No index found, generating new index")
        create_new_public_country_index.delay()


@celery_app.task(bind=True, base=ElasticsearchTaskBase, name='figure1.backend.public_country.reindex')
def create_new_public_country_index(self):
    sync_es = PublicCountries()
    sync_es.create_index(session=self.session)
    index_name = sync_es.index_name
    bulk_update = helpers.bulk(self.es_client,
                               actions=sync_es.get_es_bulk_insert_documents(id_list=[], session=self.session),
                               index=index_name,
                               stats_only=True,
                               max_retries=5,
                               chunk_size=200)
    logger.info(f"processed: {bulk_update[0]}, errors: {bulk_update[1]}")
    sync_es.switch_active_index(index_name=index_name)


class PublicCountries(BaseIndex):
    index_alias = countries_alias
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
        return MappingData.country_search_data

    def create_queue_items(self, session):
        pass

    def get_queue_items(self, session):
        pass

    def get_es_insert_documents(self, session, id_list):
        pass

    def get_es_bulk_insert_documents(self, session, id_list):
        for c in Country.find_all_countries(session):
            es_doc = {
                "_id": c.countryUuid,
                "countryName": c.countryName,
                "countryUuid": c.countryUuid,
                "displayName": c.countryName
            }
            yield es_doc
            for i in c.countryRegions:
                if i.regionName == c.countryName:
                    continue
                es_doc.update({
                    "_id": i.regionUuid,
                    "displayName": f"{i.regionName}, {c.countryName}",
                    "regionUuid": i.regionUuid,
                    "regionName": i.regionName
                })
                yield es_doc

    def get_es_insert_document(self, session, id):
        pass
