import logging
import time

from elasticsearch import helpers
from elasticsearch.client import TasksClient
from figure1.core import celery_app
from figure1.configuration import es_settings
from ..base import BaseIndex
from figure1.common.models.db import ElasticSearchQueue, Comment
from figure1.common.helpers.comment import CommentDetail
from ..tasks import ElasticsearchTaskBase
from .comment_index_schema import CommentMapSchema

comments_index_alias = es_settings.comments_alias
logger = logging.getLogger('elasticsearch.index.comments')


@celery_app.task(bind=True, base=ElasticsearchTaskBase, name='figure1.backend.comments.startup')
def comment_startup(self):
    sync_es = CommentIndex()
    index = sync_es.get_active_index(session=self.session)
    if not index:
        logger.info("No index found, generating new comments index")
        create_new_comment_index.delay()


@celery_app.task(bind=True, base=ElasticsearchTaskBase, name='figure1.backend.comments.create')
def create_new_comment_index(self):
    sync_es = CommentIndex()
    sync_es.create_index(session=self.session, skip_queue=True)
    idx = sync_es.index_name
    run_bulk_updates.apply_async(kwargs={'index_name': idx})


@celery_app.task(bind=True, base=ElasticsearchTaskBase, name='figure1.backend.comments.mapping')
def update_mapping(self):
    sync_es = CommentIndex()
    sync_es.create_index(session=self.session, skip_queue=True)
    new_idx = sync_es.index_name

    reindex_body = {
        "source": {
            "index": comments_index_alias,
            "query": {"match_all": {}},
        },
        "dest": {
            "index": new_idx
        }
    }
    res = self.es_client.reindex(body=reindex_body, wait_for_completion=False)

    tc = TasksClient(self.es_client)
    while True:
        task = tc.get(task_id=res.get('task', {}))
        if task.get('completed') is True:
            sync_es.switch_active_index(index_name=new_idx)
            break
        time.sleep(10)
        logger.info(f"Processing mapping: {task.get('task', {}).get('status')}")


@celery_app.task(bind=True, base=ElasticsearchTaskBase, name='figure1.backend.comments.bulk_insert')
def run_bulk_updates(self, index_name):
    sync_es = CommentIndex()
    sync_es.index_name = index_name

    bulk_update = helpers.bulk(self.es_client,
                               actions=sync_es.get_es_bulk_insert_documents(id_list=[], session=self.session),
                               index=index_name,
                               stats_only=True,
                               max_retries=5,
                               chunk_size=10000)
    logger.info(f"processed: {bulk_update[0]}, errors: {bulk_update[1]}")
    sync_es.switch_active_index(index_name=index_name)

    logger.info(f"Starting comment flagged update")
    flagged_bulk_update = helpers.bulk(self.es_client,
                                       actions=sync_es.update_comment_flags(session=self.session),
                                       index=index_name,
                                       stats_only=True,
                                       max_retries=5,
                                       chunk_size=10000)
    logger.info(f"Flagged update processed: {flagged_bulk_update[0]}, errors: {flagged_bulk_update[1]}")
    logger.info(f"Starting comment reported update")
    reported_bulk_update = helpers.bulk(self.es_client,
                                        actions=sync_es.update_comment_reports(session=self.session),
                                        index=index_name,
                                        stats_only=True,
                                        max_retries=5,
                                        chunk_size=10000)
    logger.info(f"Reported update processed: {reported_bulk_update[0]}, errors: {reported_bulk_update[1]}")

    logger.info(f"Starting case info update")
    case_bulk_update = helpers.bulk(self.es_client,
                                    actions=sync_es.update_case_content(session=self.session),
                                    index=index_name,
                                    stats_only=True,
                                    max_retries=5,
                                    chunk_size=10000)
    logger.info(f"Case update processed: {case_bulk_update[0]}, errors: {case_bulk_update[1]}")

    logger.info(f"Starting user update")
    author_bulk_update = helpers.bulk(self.es_client,
                                      actions=sync_es.update_author_data(session=self.session),
                                      index=index_name,
                                      stats_only=True,
                                      max_retries=5,
                                      chunk_size=10000)
    logger.info(f"User update processed: {author_bulk_update[0]}, errors: {author_bulk_update[1]}")
    logger.info(f"User update complete")


class CommentIndex(BaseIndex):
    index_alias = comments_index_alias
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
        return CommentMapSchema.comment_map_data

    def create_queue_items(self, session):
        session.query(ElasticSearchQueue).filter(ElasticSearchQueue.index_name == self.index_name).delete()
        session.commit()
        return

    def get_queue_items(self, session):
        pass

    def update_author_data(self, session):
        for a in CommentDetail.get_comment_authors(session=session):
            comment_uuid = a.get('commentUuid', None)
            if comment_uuid:
                update_doc = {
                    "_id": comment_uuid,
                    "_op_type": 'update',
                    "doc": {**a}
                }
                yield update_doc

    def update_case_content(self, session):
        for c in CommentDetail.get_comment_content(session=session):
            comment_uuid = c.get('commentUuid', None)
            if comment_uuid:
                update_doc = {
                    "_id": comment_uuid,
                    "_op_type": 'update',
                    "doc": {**c}
                }
                yield update_doc

    def update_comment_flags(self, session):
        for f in CommentDetail.get_comment_flags(session=session):
            comment_uuid = f.get('commentUuid', None)
            if comment_uuid:
                update_doc = {
                    "_id": comment_uuid,
                    "_op_type": 'update',
                    "doc": {**f}
                }
                yield update_doc

    def update_comment_reports(self, session):
        for r in CommentDetail.get_comment_reports(session=session):
            comment_uuid = r.get('commentUuid', None)
            if comment_uuid:
                update_doc = {
                    "_id": comment_uuid,
                    "_op_type": 'update',
                    "doc": {**r}
                }
                yield update_doc

    def get_es_bulk_insert_documents(self, session, id_list):
        for c in session.query(Comment).yield_per(10000).all():
            comment = c.as_dict()
            if comment:
                comment.update({'_id': comment['commentUuid']})
                yield comment
            else:
                continue

    def get_es_insert_documents(self, session, id_list):
        pass

    def get_es_insert_document(self, session, id):
        pass
