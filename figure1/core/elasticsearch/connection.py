import logging
from elasticsearch import Elasticsearch, client
from elasticsearch.exceptions import ElasticsearchException, ConnectionError
from figure1.configuration import es_settings
import time

logger = logging.getLogger(__name__)


class InitESConnection:
    es_ = None
    retry_count = 0

    @classmethod
    @property
    def es(cls):
        if cls.es_ is None:
            try:
                cls.es_ = InitESConnection._get_es_connection()
            except ConnectionError:
                logger.error("Max retries exceeded")
                return None
        if cls.es_.ping():
            return cls.es_

    @classmethod
    def _get_es_connection(cls):
        """
        Retry for a maximum of 5 times, the wait time increases between each try to a maximum of 5 seconds
        :return:
        """
        while cls.retry_count < 5:
            try:
                return cls._get_es()
            except ConnectionError as ce:
                logger.error("Caught connection error %s", ce)
                logger.error("Elasticsearch connection retrying in %s seconds", 1 * cls.retry_count)
                time.sleep(1 * cls.retry_count)
                cls.retry_count += 1
        return cls._get_es()

    @classmethod
    def _get_es(cls) -> client:
        max_retry_count = es_settings.connect_retry_count
        retry_wait = es_settings.connect_retry_wait

        elasticsearch_hosts = es_settings.hosts
        elasticsearch_cloud_id = es_settings.cloud_id
        elasticsearch_api_key = es_settings.api_key

        if elasticsearch_cloud_id and elasticsearch_api_key:
            es = Elasticsearch([{"cloud_id": elasticsearch_cloud_id,
                                 "api_key": elasticsearch_api_key
                                 }],
                               retry_on_timeout=True,
                               max_retries=5,
                               maxsize=20,
                               timeout=30)

        else:
            es = Elasticsearch([elasticsearch_hosts])

        es.transport.retry_on_timeout = True
        es.transport.max_retries = max_retry_count
        res = es.info(pretty=True)
        logger.info("Elasticsearch connection info: %s", res)
        return es


es = InitESConnection().es
