import logging
from pydantic import ValidationError
from sqlalchemy.orm import Query
from sqlalchemy import desc
from elasticsearch_dsl.exceptions import ValidationException
from elasticsearch import helpers
from celery import group, chain
from figure1.common.models.db import User
from figure1.common.helpers import UserDocument
from figure1.exceptions import UserNotFound
from figure1.configuration import es_settings
from figure1.core import celery_app
from figure1.store import IndexQueue
from ..base import BaseIndex
from ..tasks import ElasticsearchTaskBase
from figure1.common.types.elasticsearch import ESUserDocument

users_index_alias = es_settings.users_alias
logger = logging.getLogger('figure1.elasticsearch.index.users')


@celery_app.task(bind=True, base=ElasticsearchTaskBase, name='figure1.backend.users.startup')
def user_startup(self):
    sync_es = UserIndex()
    index_name = sync_es.get_active_index(session=self.session)
    logging.info(f"Checking index name {index_name}")
    if index_name:
        logging.info("Active index exists, nothing to do")
    else:
        logging.info("No index name found, generating new index")
        create_new_user_index.delay()


@celery_app.task(bind=True, base=ElasticsearchTaskBase, name='figure1.backend.users.create')
def create_new_user_index(self, workers=8, force_new=False):
    sync_es = UserIndex()
    idx_name = None
    i = IndexQueue(index_alias=users_index_alias, index_name=None)
    active = i.find_active_queue_key()
    logger.info("Active list is %s", active)
    for active_queue in active:
        if force_new:
            logger.info("New index creation forced")
            i.delete_queue_key(active_queue)
            continue

        if i.get_queue_count(active_queue) == 0:
            logger.info("No items in %s queue, deleting", active_queue)
            i.delete_queue_key(active_queue)
            continue

        idx_name = active_queue.split(':')[2]
        logger.info("Active queue is %s", active_queue)
        if UserIndex.is_valid_index(idx_name, users_index_alias):
            i.index_name = idx_name
            logger.info("Continuing rebuild of index %s - %s remaining", idx_name, i.get_queue_count(active_queue))
            idx_name = idx_name
            break
        else:
            logger.error("Invalid index name %s", idx_name)
            i.delete_queue_key(active_queue)
            idx_name = None
    if not idx_name:
        idx_name = sync_es.create_elasticsearch_index()
        sync_es.index_name = idx_name
        logger.info("Creating index %s", idx_name)
        sync_es.create_queue_items(session=self.session)

    user_idx_group = []
    try:
        workers = int(workers)
    except TypeError:
        workers = 4

    logger.info("Starting %s workers", workers)
    for i in range(workers):
        user_idx_group.append(run_bulk_updates.si(index_name=idx_name))
    logger.info("index name is %s", idx_name)

    return group(*user_idx_group).apply_async()


@celery_app.task(bind=True, base=ElasticsearchTaskBase, name='figure1.backend.users.switch_index')
def switch_elasticsearch_index(self, index_name):
    sync_es = UserIndex(index_name=index_name)
    sync_es.index_name = index_name
    sync_es.switch_active_index(index_name=index_name)
    i = IndexQueue(index_alias=sync_es.index_alias, index_name=index_name)
    i.delete_queue_key()


@celery_app.task(bind=True, base=ElasticsearchTaskBase, name='figure1.backend.users.refresh')
def refresh_users_index(self):
    """
    Creates a new index and copies the user data over. There are five steps to this process.
    1. Create two new indexes with the new mapping, one is used to capture writes, and the other is the new
    target index
    2. Set the alias write target to the index used for capturing writes.
    3. Reindex data from the original index to the new target index.
    4. Change the write target to the new target index, write the changes to the new target index.
    5. Write the changes from the temporary write target to the new target index, delete the temporary index.

    :param self:
    :return:
    """
    sync_es = UserIndex()
    sync_es.handle_mapping_change()


@celery_app.task(bind=True, base=ElasticsearchTaskBase, name='figure1.backend.users.bulk_insert')
def run_bulk_updates(self, index_name):
    sync_es = UserIndex(index_name=index_name)
    processed = {'Ok': 0}
    logger.info("Starting update for index %s", index_name)
    for ok, action in helpers.streaming_bulk(self.es_client,
                                             actions=sync_es.get_es_bulk_insert_documents(id_list=[],
                                                                                          session=self.session),
                                             index=index_name,
                                             max_retries=1,
                                             chunk_size=200):
        if ok:
            processed['Ok'] += 1

    logger.info("Finished processing %s documents", processed['Ok'])


def create_new_users_index():
    """
    Create and return a new concrete index.
    """
    return UserIndex(create_index=True).index_name


class UserIndex(BaseIndex):
    index_alias = users_index_alias
    index_name = None

    def __repr__(self):
        return f"UserIndex:<index_alias:{self.index_alias},index_name:{self.index_name}>"

    def __init__(self, index_name=None, create_index=False):
        super().__init__()
        if create_index:
            self.index_name = self.create_elasticsearch_index()

        elif not index_name:
            self.index_name = self.get_write_index()
        else:
            self.index_name = index_name

    @property
    def index_map_data(self):
        """
        This is a little ugly, but I'm not sure how else to access the mapping from the index document
        :return:
        """
        idx_map = ESUserDocument._doc_type.mapping.to_dict()
        return {'mappings': idx_map}

    def create_queue_items(self, session):

        i = IndexQueue(index_alias=self.index_alias, index_name=self.index_name)
        q: Query = session.query(User.user_uuid) \
            .filter(User.deleted_at.is_(None)).order_by(User.created_at.desc())
        full_user_count = q.count()
        logger.info("%s users to process", full_user_count)
        q = q.limit(10000)
        offset = 0
        while True:
            q = q.offset(offset)
            update_list = q.all()
            offset += len(update_list)
            i.write_queue_items([str(x[0]) for x in update_list])
            if len(update_list) <= 0:
                logger.debug("Update complete")
                break
            else:
                logger.debug("Added %s - offset %s - total queue size %s out of %s",
                             len(update_list),
                             offset,
                             i.get_queue_count(),
                             full_user_count)
        logger.info("Wrote %s users to queue %s", i.get_queue_count(), i.index_queue_key)

    def get_es_bulk_insert_documents(self, session, id_list):
        i = IndexQueue(index_alias=self.index_alias, index_name=self.index_name)
        while True:
            u = i.get_next_item()
            if not u:
                logger.debug("No more items")
                break
            try:
                user = self._fetch_user(user_uuid=u, session=session)
            except UserNotFound:
                logger.error("No user found for uuid %s", u)
                continue
            except ValidationException:
                logger.error("User failed elasticsearch document validation")
                continue
            except ValidationError:
                logger.exception("User %s failed to validate", u)
                continue
            user.meta.id = user.userUuid
            yield user.to_dict(include_meta=True)

    def get_es_insert_documents(self, session, id_list):
        pass

    def get_es_insert_document(self, session, id):
        pass

    def _fetch_user(self, user_uuid, session):
        return UserDocument.elasticsearch_user_detail(user_uuid=user_uuid, session=session)
