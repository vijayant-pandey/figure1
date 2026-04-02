import logging
import time
from pydantic import BaseModel
from typing import List, Optional
from elasticsearch.exceptions import NotFoundError
from figure1.core import managed_session
from elasticsearch.client.tasks import TasksClient
from figure1.store import TaskLock
from figure1.common.models.db import ElasticSearchQueue, ElasticSearchIndex
from figure1.common.utils import date_utils
from figure1.core import es
from figure1.configuration import app_settings

logger = logging.getLogger('elasticsearch.index')
read_only_logger = logging.getLogger('figure1.read_only_mode')


def _generate_add_action(alias_name, index_name, **kwargs):
    return dict(add=dict(index=index_name, alias=alias_name, **kwargs))


def _generate_remove_action(alias_name, index_name, **kwargs):
    return dict(remove=dict(index=index_name, alias=alias_name, **kwargs))


class BaseIndex:

    def __init__(self):
        self.es_queue = ElasticSearchQueue()
        self.es_index = ElasticSearchIndex()
        self.lock_client = TaskLock(self.index_alias)

    @staticmethod
    def is_valid_index(index_name, index_alias):
        """
        Is a valid index if it exists.
        :param index_name:
        :return:
        """
        if not index_name.startswith(index_alias):
            logger.error("Index name %s does not start with alias %s", index_name, index_alias)
            return False
        try:
            return es.indices.get(index=index_name)

        except NotFoundError:
            return False

    def get_write_index(self):
        """
        If there is more than one index, return the write target, otherwise return the concrete index.

        Returns None if a concrete or write index cannot be found for the alias or if the alias does not exist
        :return:
        """

        self.delete_concrete_alias()

        try:
            idx_dict = es.indices.get_alias(name=self.index_alias)
        except NotFoundError:
            return None
        idx_list = list(idx_dict.keys())
        if not idx_list:
            return None

        if len(idx_list) > 1:
            for idx in idx_list:
                if idx_dict[idx]['aliases'][self.index_alias].get('is_write_index', False):
                    return idx
        else:
            return idx_list.pop()
        return None

    def add_write_index(self, concrete_index):
        if app_settings.read_only_dev_mode:
            read_only_logger.warning(f"READ-ONLY MODE: Blocked add_write_index() operation for {concrete_index}")
            return
            
        logger.info("Adding write index %s to alias %s", concrete_index, self.index_alias)
        alias_actions = []
        prev_write_index = self.get_write_index()
        if prev_write_index:
            alias_actions.append(_generate_remove_action(alias_name=self.index_alias,
                                                         index_name=prev_write_index))
        alias_actions.append(_generate_add_action(index_name=concrete_index,
                                                  alias_name=self.index_alias,
                                                  is_write_index=True))
        es.indices.update_aliases(body=dict(actions=alias_actions))

    def add_filtered_alias(self, index_name, alias_name, alias_filter):
        if app_settings.read_only_dev_mode:
            read_only_logger.warning(f"READ-ONLY MODE: Blocked add_filtered_alias() operation for {alias_name}")
            return
            
        alias_actions = [_generate_add_action(alias_name=alias_name, index_name=index_name, filter=alias_filter)]
        try:
            existing_alias = es.indices.get_alias(name=alias_name)
            for k in existing_alias.keys():
                if k == index_name:
                    continue
                else:
                    alias_actions.append(_generate_remove_action(alias_name=alias_name,
                                                                 index_name=str(k)))
        except NotFoundError:
            logger.debug("No alias %s exists", alias_name)
        body = dict(actions=alias_actions)
        logger.debug("Alias Actions are %s", body)
        es.indices.update_aliases(body=body)

    def remove_index_from_alias(self, concrete_index):
        if app_settings.read_only_dev_mode:
            read_only_logger.warning(f"READ-ONLY MODE: Blocked remove_index_from_alias() operation for {concrete_index}")
            return
            
        logger.info("Removing index %s from alias %s", concrete_index, self.index_alias)
        alias_actions = [_generate_remove_action(alias_name=self.index_alias, index_name=concrete_index)]
        es.indices.update_aliases(body=dict(actions=alias_actions))

    def delete_concrete_alias(self):
        """
        If the defined alias is a concrete index, delete it. Otherwise do nothing.
        :return:
        """
        if app_settings.read_only_dev_mode:
            read_only_logger.warning(f"READ-ONLY MODE: Blocked delete_concrete_alias() operation for {self.index_alias}")
            return

        if es.indices.exists_alias(name=self.index_alias):
            return
        if es.indices.exists(index=self.index_alias):
            logger.info("Alias appears to be concrete, deleting")
            es.indices.delete(index=self.index_alias)
            return

    def handle_mapping_change(self):
        if not es.indices.exists_alias(name=self.index_alias):
            logger.info("No concrete index exists for this alias - returning")
            return False

        alias_list = es.indices.get_alias(name=self.index_alias)
        if len(alias_list.keys()) != 1:
            for a in alias_list.keys():
                if alias_list[a]['aliases'][self.index_alias].get('is_write_index') is False:
                    logger.info("Removing non-write index %s", a)
                    self.remove_index_from_alias(a)

        recheck_alias_list = es.indices.get_alias(name=self.index_alias)

        if len(recheck_alias_list.keys()) != 1:
            logger.error("Index alias must have exactly one concrete alias to continue")
            return

        existing_primary_index = self.get_write_index()

        temp_index = self._create_elasticsearch_index(index_suffix='temp')

        self.add_write_index(temp_index)

        logger.info("Created temporary write index %s", temp_index)

        new_index = self._create_elasticsearch_index()

        logger.info("Created new index %s", new_index)
        logger.info("Starting main reindex...")
        task_id = self.reindex(existing_primary_index, new_index).get('task')
        tc = TasksClient(es)
        task = tc.get(task_id=task_id)
        logger.info("Created re-indexing task %s", task)
        while not task.get('completed'):
            logger.debug("Task progress %s", task)
            time.sleep(30)
            logger.info("Main reindex finished")
            task = tc.get(task_id=task_id)
        logger.info("Task complete %s", task)
        self.remove_index_from_alias(existing_primary_index)
        self.remove_index_from_alias(temp_index)
        self.add_write_index(new_index)

        logger.info("Updated aliases, now %s", es.indices.get_alias(name=self.index_alias))
        logger.info("Reindexing updates")

        task_id = self.reindex(temp_index, new_index).get('task')
        task = tc.get(task_id=task_id)
        logger.info("Started task %s", task)
        while not task.get('completed'):
            logger.debug("Task progress %s", task)
            time.sleep(30)
            task = tc.get(task_id=task_id)
            logger.info("Update reindex finished")
        logger.info("Finished reindex %s", task)
        logger.info("Reindexing updates complete")
        logger.info("Deleting previous index")
        es.indices.delete(index=temp_index)
        es.indices.delete(index=existing_primary_index)

    def _create_elasticsearch_index(self, index_suffix=None):
        mapping_data = self.index_map_data
        mapping_data.update({
            "settings": {
                "index": {
                    "number_of_shards": 3,
                    "number_of_replicas": 1
                }
            }
        })
        if index_suffix:
            idx_name = "%s-%s-%s" % (self.index_alias, str(int(date_utils.utc_now_timestamp())), index_suffix)
        else:
            idx_name = "%s-%s" % (self.index_alias, str(int(date_utils.utc_now_timestamp())))
        idx_match = "%s-*" % self.index_alias
        idx_template_name = "%s-template" % self.index_alias
        es.indices.put_template(name=idx_template_name, body={
            "index_patterns": [idx_match, self.index_alias],
            **mapping_data,
        })
        if es.indices.exists(index=idx_name):
            if es.count(index=idx_name).get('count') == 0:
                logger.info("Index %s exists - deleting", idx_name)
                es.indices.delete(index=idx_name)
            else:
                logger.error("Index exists, but there are documents, will not delete")

        es.indices.create(index=str(idx_name))
        self.index_name = str(idx_name)
        return str(idx_name)

    def create_elasticsearch_index(self):
        return self._create_elasticsearch_index()

    def create_index(self, session, skip_queue=False):
        if app_settings.read_only_dev_mode:
            read_only_logger.warning(f"READ-ONLY MODE: Blocked create_index() operation for {self.index_alias}")
            return

        self._create_elasticsearch_index()

        session.query(ElasticSearchQueue).filter(ElasticSearchQueue.index_alias == self.index_alias).delete()
        session.commit()
        self.es_index.create(index_alias=self.index_alias, index_name=self.index_name, session=session)
        logger.info(f"Created index {self.index_name} for alias {self.index_alias}")
        if not skip_queue:
            session.query(ElasticSearchQueue).filter(ElasticSearchQueue.index_alias == self.index_alias).delete()
            session.commit()
            self.create_queue_items(session=session)

    def refresh_index(self, session, es):
        active_index = self.get_write_index()
        if not active_index:
            logger.info("No write index found for alias %s", self.index_alias)
            return {'error': 'No active index found in elasticsearch, create index first'}
        self.index_name = active_index
        self.es_queue.remove_complete(session=session)
        queue_size = self.es_queue.get_queue_size(index_name=self.index_name, session=session)
        if queue_size:
            logger.info("Items are in the queue after completed items removed,"
                         " this probably means another process is updating elasticsearch")
            return {'error': 'Unexpected queue state'}
        logger.info("Creating case queue")
        self.create_queue_items(session=session)

    def reindex(self, from_index, to_index):
        body = {
            "source": {
                "index": from_index
            },
            "dest": {
                "index": to_index
            }
        }
        return es.reindex(body=body,
                          request_timeout=1800,
                          wait_for_completion=False,
                          requests_per_second=300)

    def switch_active_index(self, index_name):
        existing_index = self.get_write_index()
        if existing_index == index_name:
            logger.info("Index exists, and is linked to the correct alias, nothing to do")
        elif existing_index:
            logger.info("Removing existing write index target from alias %s", existing_index)
            self.remove_index_from_alias(existing_index)
        logger.info("Adding write target %s", index_name)
        self.add_write_index(index_name)
        self.index_name = index_name

    def get_active_index(self, session=None):
        return self.get_write_index()

    def get_queue_size(self, index_name, session=None):
        return self.es_queue.get_queue_size(index_name=index_name, session=session)

    def set_indexed(self, case_id_list, index_name, session=None):
        if app_settings.read_only_dev_mode:
            read_only_logger.warning(f"READ-ONLY MODE: Blocked set_indexed() operation for {index_name}")
            return 0
            
        self.es_queue.update_indexed(index_alias=self.index_alias,
                                     index_name=index_name,
                                     case_id_list=case_id_list,
                                     session=session)

        qs = self.es_queue.get_queue_size(index_name=index_name, session=session)
        if not qs:
            self.es_queue.remove_complete(session=session)
            i = session.query(ElasticSearchIndex) \
                .filter(ElasticSearchIndex.index_alias == self.index_alias) \
                .filter(ElasticSearchIndex.index_name == index_name) \
                .one_or_none()
            if i:
                i.is_complete = True
                session.add(i)
            session.commit()
        return qs

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


class MappingData:
    country_search_data = {
        "mappings": {
            "properties": {
                "countryName": {
                    "type": "text"
                },
                "regionName": {
                    "type": "text"
                },
                "displayName": {
                    "type": "text"
                },
                "countryUuid": {
                    "type": "keyword"
                },
                "regionUuid": {
                    "type": "keyword"
                }
            }
        }
    }
    school_search_data = {
        "mappings": {
            "properties": {
                "schoolCompletions": {
                    "type": "search_as_you_type"
                },
                "locationCompletions": {
                    "type": "search_as_you_type"
                },
                "schoolName": {
                    "type": "text"
                },
                "schoolAbbreviation": {
                    "type": "text"
                },
                "professions": {
                    "type": "keyword"
                },
                "countries": {
                    "type": "keyword"
                }
            }
        }
    }
    search_term_data = {
        "mappings": {
            "properties": {
                "typeAhead": {
                    "type": "completion",
                    "analyzer": "standard"
                }
            }
        }
    }

    specialty_map_data = {
        "mappings": {
            "properties": {
                "treeUuid": {
                    "type": "keyword"
                },
                "professionName": {
                    "type": "text"
                },
                "professionLabel": {
                    "type": "keyword"
                },
                "specialtyName": {
                    "type": "text"
                },
                "specialtyLabel": {
                    "type": "keyword"
                },
                "subSpecialtyName": {
                    "type": "text"
                },
                "subSpecialtyLabel": {
                    "type": "keyword"
                },
                "subSpecialtyCompletion": {
                    "type": "completion"
                },
                "specialtyCompletion": {
                    "type": "completion"
                },
                "professionCompletion": {
                    "type": "completion"
                }
            }
        }
    }

    legacy_case_map_data = {
        "mappings": {
            "properties": {
                "caseUuid": {
                    "type": "keyword"
                },
                "abbreviation": {
                    "type": "keyword"
                },
                "typeUuid": {
                    "type": "keyword"
                },
                "country": {
                    "type": "keyword"
                },
                "countryCode": {
                    "type": "keyword"
                },
                "countryUuid": {
                    "type": "keyword"
                },
                "countryName": {
                    "type": "keyword"
                },
                "image_url": {
                    "type": "keyword"
                },
                "legacyId": {
                    "type": "keyword"
                },
                "username": {
                    "type": "keyword"
                },
                "userUuid": {
                    "type": "keyword"
                },
                "caseState": {
                    "type": "keyword"
                },
                "taggingState": {
                    "type": "keyword"
                },
                "promotions": {
                    "type": "nested",
                    "properties": {
                        "channel_uuid": {
                            "type": "keyword"
                        },
                        "promotion_uuid": {
                            "type": "keyword"
                        },
                        "promotion_name": {
                            "type": "text"
                        },
                        "channel_name": {
                            "type": "text"
                        },
                        "promotion_notes": {
                            "type": "text"
                        },
                        "promotion_publish_date": {
                            "type": "date"
                        },
                        "cases": {
                            "type": "nested",
                            "properties": {
                                "case_notes": {
                                    "type": "text"
                                },
                                "case_id": {
                                    "type": "keyword"
                                },
                                "case_alternate_description": {
                                    "type": "text"
                                },
                                "case_alternate_title": {
                                    "type": "text"
                                },
                                "promotion_uuid": {
                                    "type": "keyword"
                                }
                            }
                        }
                    }
                },
                "mesh_terms": {
                    "type": "keyword"
                },
                "mesh_terms_text": {
                    "type": "text",
                    "analyzer": "english"
                },
                "caption": {
                    "type": "text",
                    "analyzer": "english"
                },
                "title": {
                    "type": "text",
                    "analyzer": "english"
                },
                "likes": {
                    "type": "integer"
                },
                "follows": {
                    "type": "integer"
                },
                "comment_meta": {
                    "type": "nested",
                    "properties": {
                        "typeUuid": {
                            "type": "keyword"
                        },
                        "count": {
                            "type": "integer"
                        }
                    }
                },
                "comments": {
                    "type": "nested",
                    "properties": {
                        "commentUuid": {
                            "type": "keyword"
                        },
                        "language": {
                            "type": "keyword"
                        },
                        "parentId": {
                            "type": "keyword"
                        },
                        "userUuid": {
                            "type": "keyword"
                        },
                        "username": {
                            "type": "keyword"
                        },
                        "typeUuid": {
                            "type": "keyword"
                        },
                        "email": {
                            "type": "keyword"
                        },
                        "caseUuid": {
                            "type": "keyword"
                        },
                        "text": {
                            "type": "text",
                            "analyzer": "english"
                        },
                        "likes": {
                            "type": "integer"
                        },
                        "acceptedAnswer": {
                            "type": "boolean"
                        },
                        "verified": {
                            "type": "boolean"
                        },
                        "label": {
                            "type": "text"
                        }
                    }
                }
            }
        }
    }
