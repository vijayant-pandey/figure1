import logging
import datetime
from elasticsearch.exceptions import RequestError, ConflictError, ElasticsearchException
from figure1.core import es
from figure1.configuration import es_settings

comments_index_alias = es_settings.comments_alias

logger = logging.getLogger(__name__)


def add_or_update_comment(comment_uuid, comment_detail):
    try:
        es.update(index=comments_index_alias,
                  id=comment_uuid,
                  retry_on_conflict=5,
                  doc=comment_detail,
                  doc_as_upsert=True)
    except RequestError as re:
        logger.error("Failed to add or update comment %s, caught error %s", comment_uuid, re)
    except ConflictError as ce:
        logger.error("Caught conflict trying to update comment %s, error %s", comment_uuid, ce)


def delete_comment(comment_uuid):
    try:
        es.delete(index=comments_index_alias, id=comment_uuid)
    except RequestError as re:
        logger.error("Failed to delete case %s, caught error %s", comment_uuid, re)
    except ConflictError as ce:
        logger.error("Caught conflict trying to delete case %s, error %s", comment_uuid, ce)
