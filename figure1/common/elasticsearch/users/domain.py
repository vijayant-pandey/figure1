import logging
from elasticsearch.exceptions import RequestError, ConflictError
from figure1.core import es
from figure1.configuration import es_settings
from figure1.common.types.elasticsearch import ESUserDocument

users_index_alias = es_settings.users_alias

logger = logging.getLogger(__name__)


def delete_es_user(user_uuid):
    try:
        es.delete(index=users_index_alias, id=user_uuid)
    except RequestError as re:
        logger.error("Failed to delete case %s, caught error %s", user_uuid, re)
    except ConflictError as ce:
        logger.error("Caught conflict trying to delete case %s, error %s", user_uuid, ce)


def add_or_update_user(user_uuid, user_detail: ESUserDocument) -> ESUserDocument:
    if not isinstance(user_detail, ESUserDocument):
        raise ValueError("User detail must be an ESUserDocument instance")
    user_detail.meta.id = str(user_uuid)
    try:
        user_detail.save(index=users_index_alias, using=es)
    except AttributeError:
        logger.exception("Failed to update user %s with error", user_detail.to_dict())
    return user_detail
