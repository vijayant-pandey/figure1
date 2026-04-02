import logging
from figure1.core import managed_session
from figure1.common.helpers.groups import GroupManagement
from figure1.common.types.elasticsearch import GroupIndex
from elasticsearch.exceptions import ElasticsearchException
from elasticsearch_dsl import Index
from figure1.configuration import es_settings
from figure1.core import es

logger = logging.getLogger('elasticsearch.index.groups_index')


class GroupIndexSetup:
    setup_complete = False

    @classmethod
    def group_index_startup(cls):
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

        group_index = Index(es_settings.groups_alias, using=es)
        group_index.settings(number_of_shards=3, number_of_replicas=1)
        group_index.document(GroupIndex)
        try:
            group_index.save()
        except ElasticsearchException:
            logger.exception("Failed to write index, delete and rebuild")
            group_index.delete()
            group_index.save()
        cls.setup_complete = True


@managed_session
def generate_groups_index(session):
    GroupManagement.refresh_all_elasticsearch_groups(session=session)


if es.ping():
    logger.info("Setting up group index")
    GroupIndexSetup.group_index_startup()
else:
    logger.error("No active elasticsearch connection found")
