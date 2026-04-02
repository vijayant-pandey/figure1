import logging

from figure1.configuration import es_settings
from elasticsearch import helpers
from figure1.core import managed_session, celery_app
from sqlalchemy.sql.functions import coalesce
from sqlalchemy.sql.expression import func, text
from sqlalchemy.exc import IntegrityError
from figure1.common.models.db import LegacyCase, MeshTerms, LegacyUser, Country, LegacySpecialty, \
    Media, ElasticSearchQueue, PromotionMethods, LegacyComment

from ..base import BaseIndex, MappingData
from ..tasks import ElasticsearchTaskBase

logger = logging.getLogger('elasticsearch.index.legacy_cases')


@celery_app.task(bind=True, base=ElasticsearchTaskBase, name='figure1.backend.legacy_case.refresh')
def refresh_legacy_case_index(self):
    sync_es = LegacyCaseIndex()
    e = sync_es.refresh_index(es=self.es_client, session=self.session)
    if e:
        return e
    task_case_id_list = []
    count = 0
    for c in sync_es.get_queue_items(session=self.session):
        task_case_id_list.append(c)
        if not count % 1000:
            legacy_case_list_update.apply_async(kwargs={'case_id_list': task_case_id_list, 'bulk_refresh': True})
            task_case_id_list = []
        count += 1
    legacy_case_list_update.apply_async(kwargs={'case_id_list': task_case_id_list, 'bulk_refresh': True})


@celery_app.task(bind=True, base=ElasticsearchTaskBase, name='figure1.backend.legacy_case.create')
def create_legacy_case_index(self):
    sync_es = LegacyCaseIndex()
    sync_es.create_index(session=self.session)
    idx = sync_es.index_name
    run_bulk_updates.apply_async(kwargs={'index_name': idx})
    run_bulk_updates.apply_async(kwargs={'index_name': idx})
    run_bulk_updates.apply_async(kwargs={'index_name': idx})
    run_bulk_updates.apply_async(kwargs={'index_name': idx})


@celery_app.task(bind=True, base=ElasticsearchTaskBase, name='figure1.backend.legacy_case.bulk_insert')
def run_bulk_updates(self, index_name):
    sync_es = LegacyCaseIndex()
    while True:
        sync_es.index_name = index_name
        bulk_update = helpers.bulk(self.es_client,
                                   actions=sync_es.get_es_bulk_insert_documents(id_list=[], session=self.session),
                                   index=index_name,
                                   stats_only=True,
                                   max_retries=5,
                                   chunk_size=200)
        remaining = sync_es.get_queue_size(index_name=index_name, session=self.session)
        logger.info(f"Remaining {remaining}")
        if not bulk_update[0]:
            logger.info("Nothing processed, exiting")
            break
        if not remaining:
            sync_es.switch_active_index(index_name=index_name)
            return {'processed': bulk_update[0], 'errors': bulk_update[1], 'remaining': remaining}
        logging.info({'processed': bulk_update[0], 'errors': bulk_update[1], 'remaining': remaining})


@celery_app.task(bind=True, base=ElasticsearchTaskBase, name='figure1.backend.legacy_case.bulk_update')
def legacy_case_list_update(self, case_id_list=[], bulk_refresh=False):
    sync_es = LegacyCaseIndex()
    idx = sync_es.get_active_index(session=self.session)
    if not idx:
        logger.error('No active index found')
        return {'error': 'No active index found'}
    sync_es.index_name = idx['index_name']
    for case_uuid in case_id_list:
        sync_es.update_case(case_uuid=case_uuid, elasticsearch_client=self.es_client, session=self.session)
    if bulk_refresh:
        remaining = sync_es.set_indexed(case_id_list=case_id_list,
                                        index_name=sync_es.index_name,
                                        session=self.session)
        return {'remaining': remaining}


@celery_app.task(bind=True, base=ElasticsearchTaskBase, name='figure1.backend.legacy_case.update_promotions')
def update_promotions(self):
    sync_es = LegacyCaseIndex()
    sync_es.add_promotions(elasticsearch_client=self.es_client)


class LegacyCaseIndex(BaseIndex):
    _index_alias = es_settings.legacy_cases_alias
    _index_name = None

    def __init__(self):
        super().__init__()
        self.user_cache = {}

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
    def index_alias(self):
        return self._index_alias

    @property
    def index_map_data(self):
        return MappingData.legacy_case_map_data

    def create_queue_items(self, session=None):
        for c in session.query(LegacyCase.case_uuid).all():
            try:
                self.es_queue.create(case_uuid=c.case_uuid,
                                     index_name=self.index_name,
                                     index_alias=self.index_alias,
                                     session=session)
            except IntegrityError as ie:
                logger.error("Failed to insert")
                raise ie
        session.commit()

    def get_queue_items(self, session):
        for c in session.query(ElasticSearchQueue) \
                .filter(ElasticSearchQueue.index_alias == self.index_alias) \
                .filter(ElasticSearchQueue.indexed.is_(False)) \
                .filter(ElasticSearchQueue.index_name == self.index_name) \
                .with_for_update(skip_locked=True).limit(1000):
            yield c

    def add_promotions(self, elasticsearch_client):
        for case in PromotionMethods().get_all_cases():
            if elasticsearch_client.exists(index=self.index_alias, id=case, doc_type="_doc"):
                promo_list = PromotionMethods().get_promotions_by_case(case_id=case)
                elasticsearch_client.update(index=self.index_alias, id=case, body={'doc': {'promotions': promo_list}})
            else:
                logger.error("Unable to find case in elasticsearch %s", case)
                continue

    def update_case(self, case_uuid, elasticsearch_client, session):
        case = self.get_es_insert_document(id=case_uuid, session=session)
        if not case:
            return None
        if elasticsearch_client.exists(index=self.index_name, id=case_uuid, doc_type="_doc"):
            elasticsearch_client.delete(index=self.index_name, id=case_uuid, doc_type="_doc")
        elasticsearch_client.create(index=self.index_name, id=case_uuid, doc_type="_doc", body=case)

    def generate_comment_metadata(self, comment_list):
        comment_meta = {}
        cml = []
        for c in comment_list:
            type_uuid = c.get('typeUuid')
            user_uuid = c.get('userUuid')
            if not type_uuid:
                continue
            if type_uuid in comment_meta:
                comment_meta[type_uuid]['type_count'] += 1
            else:
                comment_meta[type_uuid] = {'type_count': 1}

            if 'user_count' in comment_meta[type_uuid]:
                if user_uuid not in comment_meta[type_uuid]['user_count']:
                    comment_meta[type_uuid]['user_count'].append(user_uuid)
            else:
                comment_meta[type_uuid]['user_count'] = []
                comment_meta[type_uuid]['user_count'].append(user_uuid)

        for key in comment_meta.keys():
            cml.append({'typeUuid': key,
                        'total_count': comment_meta[key]['type_count'],
                        'unique_user_count': len(comment_meta[key]['user_count'])
                        })
        return cml

    def get_comments(self, session=None, case_uuid=None):
        comment_list = []
        for comment in session.query(LegacyComment).filter(LegacyComment.case_uuid == case_uuid).all():
            if not comment:
                break
            comment_dict = comment.elasticsearch_dict()
            user_uuid = comment_dict.get('userUuid')
            if user_uuid:
                if user_uuid not in self.user_cache:
                    u = session.query(LegacyUser).filter(LegacyUser.user_uuid == comment.user_uuid).one_or_none()
                    if u:
                        speciality = session.query(LegacySpecialty).filter(
                            LegacySpecialty.specialty_uuid == u.specialty_uuid).one_or_none()
                        u = u.elasticsearch_dict()
                        if speciality:
                            u.update(speciality.elasticsearch_dict())
                        self.user_cache[user_uuid] = u
                        comment_dict.update(self.user_cache[user_uuid])
                else:
                    comment_dict.update(self.user_cache[user_uuid])
            comment_list.append(comment_dict)
        return comment_list

    def get_image_url(self, case_uuid=None, session=None):
        img = session.query(Media) \
            .filter(Media.display_order == 0) \
            .filter(Media.type == 'IMAGE') \
            .filter(Media.case_uuid == case_uuid) \
            .one_or_none()
        if img:
            img = img.as_dict()
            return img['url']
        else:
            return ""

    @managed_session
    def _fetch_case(self, case_uuid, session=None):
        case = session.query(LegacyCase, LegacyUser, Country, LegacySpecialty,
                             func.coalesce(MeshTerms.approved_terms, MeshTerms.caption_terms,
                                           MeshTerms.comment_terms)) \
            .join(MeshTerms, LegacyCase.case_uuid == MeshTerms.case_uuid) \
            .join(LegacyUser, LegacyCase.user_uuid == LegacyUser.user_uuid) \
            .join(Country, LegacyUser.targetable_country_uuid == Country.country_uuid) \
            .join(LegacySpecialty, LegacyUser.specialty_uuid == LegacySpecialty.specialty_uuid) \
            .filter(LegacyCase.case_uuid == case_uuid).first()
        if case:
            case_dict = case[0].elasticsearch_dict()
            case_dict.update(case[1].elasticsearch_dict())
            case_dict.update(case[2].elasticsearch_dict())
            case_dict.update(case[3].elasticsearch_dict())
            comments = self.get_comments(case_uuid=case_dict['caseUuid'], session=session)
            comment_meta = self.generate_comment_metadata(comments)

            image_url = self.get_image_url(case_uuid=case_dict['caseUuid'], session=session)
            case_dict['mesh_terms'] = case[4]
            case_dict['mesh_terms_text'] = case[4]
            case_dict.update({'comments': comments,
                              'image_url': image_url,
                              'comment_meta': comment_meta})
            return case_dict
        return None

    def get_es_bulk_insert_documents(self, session, id_list):
        case_list = self.get_queue_items(session=session)
        if not case_list:
            return []
        for c in case_list:
            case = self._fetch_case(case_uuid=c.case_uuid, session=session)
            session.query(ElasticSearchQueue) \
                .filter(ElasticSearchQueue.case_uuid == c.case_uuid) \
                .filter(ElasticSearchQueue.index_alias == c.index_alias) \
                .filter(ElasticSearchQueue.index_name == self.index_name) \
                .update({'indexed': True})
            if case:
                case.update({'_type': '_doc', '_id': case['caseUuid']})

                yield case
            else:
                continue
        session.commit()

    def get_es_insert_documents(self, id_list, session=None):
        for case_id in id_list:
            case = self._fetch_case(case_uuid=case_id, session=session)
            if case:
                yield case
            else:
                continue

    def get_es_insert_document(self, id, session=None):
        return self._fetch_case(case_uuid=id, session=session)
