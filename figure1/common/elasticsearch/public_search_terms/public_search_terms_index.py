import logging
import time
from elasticsearch.client import TasksClient
from figure1.configuration import es_settings
from figure1.core import celery_app
from ..base import BaseIndex, MappingData
from ..tasks import ElasticsearchTaskBase

case_index_alias = es_settings.cases_alias
search_terms_alias = es_settings.public_search_terms_alias
logger = logging.getLogger('elasticsearch.index.public_search_terms')


@celery_app.task(bind=True, base=ElasticsearchTaskBase, name='figure1.backend.public_search_terms.startup')
def search_term_index_startup(self):
    sync_es = PublicSearchTerms()
    index = sync_es.get_active_index(session=self.session)
    if not index:
        logger.info("No index found, generating new index")
        sync_es.create_index(session=self.session)
        create_new_search_term_index.delay()


@celery_app.task(bind=True, base=ElasticsearchTaskBase, name='figure1.backend.public_search_terms.reindex')
def create_new_search_term_index(self):
    sync_es = PublicSearchTerms()
    sync_es.create_index(session=self.session)
    idx = sync_es.index_name
    tc = TasksClient(self.es_client)
    task = self.es_client.reindex(body={
        "source": {
            "index": case_index_alias,
            "_source": ["meshTerms"],
            "query": {
                "term": {
                    "caseState": {
                        "value": "APPROVED"
                    }
                }
            }
        },
        "dest": {
            "index": idx
        },
        "script": {
            "lang": "painless",
            "source": """
      ArrayList m = [];
      Map tm  = ['input': []];
      if ( ctx._source['meshTerms'] != null ){
        for ( i in ctx._source['meshTerms'] ) {
          if (i != null){
           tm.input.add(i);
          }
        }
      }
      ctx._source.remove('meshTerms');
      ctx._source['typeAhead'] = tm;
      """
        }
    }, wait_for_completion=False)

    while tc.get(task['task'])['completed'] is not True:
        logger.info("Creating search term index")
        time.sleep(10)
    logger.info(f"Completed reindex - {tc.get(task['task'])['task']}")
    sync_es.switch_active_index(index_name=idx)
    update_user_typeahead.apply_async(kwargs={'target_index_name': idx})


@celery_app.task(bind=True,
                 base=ElasticsearchTaskBase,
                 name='figure1.backend.public_search_terms.add_user_terms')
def update_user_typeahead(self, target_index_name):
    add_search_terms(source_index=es_settings.users_alias,
                     target_index_name=target_index_name,
                     source_fields=['username',
                                    'displayName',
                                    'professionName',
                                    'specialtyName',
                                    'subspecialtyName'],
                     es_client=self.es_client)


# TODO Should filter source by updated date to minimize required updates
def add_search_terms(target_index_name, source_index, source_fields, es_client):
    if not isinstance(source_fields, list):
        logger.error("source fields must be a list")
        return None

    reindex_body = {
        "source": {
            "index": source_index,
            "_source": source_fields,
            "query": {
                "term": {
                    "userHiddenFromSearch": {
                        "value": "false"
                    }
                }
            }
        },
        "dest": {
            "index": target_index_name
        },
        "script": {
            "lang": "painless",
            "source": f"""
                  ArrayList m = [];
                  Map tm  = ['input': []];
                  for ( i in {source_fields} ) {{
                    if (ctx._source[i] != null){{
                        tm.input.add(ctx._source[i]);
                    }}
                  }}
            ctx._source['typeAhead'] = tm"""
        }
    }
    task = es_client.reindex(body=reindex_body, wait_for_completion=False, requests_per_second=1000)

    logger.info("Started search term update elasticsearch task %s", task)


class PublicSearchTerms(BaseIndex):
    index_alias = search_terms_alias
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
            i = ai.get('index_name')
            if i:
                return i
            return None
        return self._index_name

    @property
    def index_map_data(self):
        return MappingData.search_term_data

    def create_queue_items(self, session):
        pass

    def get_queue_items(self, session):
        pass

    def get_es_bulk_insert_documents(self, session, id_list):
        pass

    def get_es_insert_documents(self, session, id_list):
        pass

    def get_es_insert_document(self, session, id):
        pass
