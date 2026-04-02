import logging
from figure1.core import celery_app
from elasticsearch.exceptions import ElasticsearchException
from elasticsearch_dsl import Index
from figure1.configuration import es_settings
from figure1.common.types.elasticsearch import CompletionIndex, reindex_mesh_terms, reindex_user_terms
from ..tasks import ElasticsearchTaskBase
from figure1.core import es

logger = logging.getLogger('elasticsearch.index.public_search_terms_v2')


class SearchTermSetup:
    setup_complete = False

    @classmethod
    def search_terms_v2_startup(cls):
        """
        Ensure the index exists and that the mapping is up to date
        :return:
        """
        if cls.setup_complete is True:
            logger.error("Setup complete")
            return
        if not es.ping():
            logger.error("Elasticsearch not connected")
            return

        public_search_terms_index = Index(es_settings.public_search_terms_alias_v2, using=es)
        public_search_terms_index.settings(number_of_shards=3, number_of_replicas=1)
        public_search_terms_index.document(CompletionIndex)
        try:
            public_search_terms_index.save()
        except ElasticsearchException:
            logger.exception("Failed to write index, delete and rebuild")
            public_search_terms_index.delete()
            public_search_terms_index.save()
        cls.setup_complete = True


@celery_app.task(bind=True, base=ElasticsearchTaskBase, name="figure1.backend.public_search_terms_v2.reindex")
def reindex_search_terms_task(self):
    reindex_search_terms()


def reindex_search_terms():
    reindex_mesh_terms(es=es)
    reindex_user_terms(es=es)


if es.ping():
    SearchTermSetup.search_terms_v2_startup()
