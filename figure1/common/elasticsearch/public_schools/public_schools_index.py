import logging
from elasticsearch import helpers
from figure1.configuration import es_settings
from figure1.common.models.db import School, Country, SpecialtyTreeV2
from figure1.core import celery_app
from ..base import BaseIndex, MappingData
from ..tasks import ElasticsearchTaskBase

schools_alias = es_settings.public_schools_alias
logger = logging.getLogger('elasticsearch.index.public_schools')


@celery_app.task(bind=True, base=ElasticsearchTaskBase, name='figure1.backend.public_schools.startup')
def public_schools_startup(self):
    sync_es = PublicSchools()
    index = sync_es.get_active_index(session=self.session)
    if not index:
        logger.info("No index found, generating new index")
        create_new_public_school_index.delay()


@celery_app.task(bind=True, base=ElasticsearchTaskBase, name='figure1.backend.public_schools.reindex')
def create_new_public_school_index(self):
    sync_es = PublicSchools()
    sync_es.create_index(session=self.session)
    index_name = sync_es.index_name
    bulk_update = helpers.bulk(self.es_client,
                               actions=sync_es.get_es_bulk_insert_documents(id_list=[], session=self.session),
                               index=index_name,
                               stats_only=True,
                               max_retries=5,
                               chunk_size=200)
    logger.info(f"processed: {bulk_update[0]}, errors: {bulk_update[1]}")
    sync_es.switch_active_index(index_name=index_name)


class PublicSchools(BaseIndex):
    index_alias = schools_alias
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
        return MappingData.school_search_data

    def create_queue_items(self, session):
        pass

    def get_queue_items(self, session):
        pass

    def get_es_insert_documents(self, session, id_list):
        pass

    def get_es_bulk_insert_documents(self, session, id_list):
        for school in session.query(School).all():
            school_doc = {
                "_id": str(school.school_uuid),
                "schoolName": school.name,
                "schoolCompletions": [school.name]
            }
            if school.abbreviation:
                school_doc.update({'schoolAbbreviation': school.abbreviation})
                school_doc['schoolCompletions'].append(school.abbreviation)
            profession_uuids = []
            country_or_region_names = []
            country_or_region_uuids = []
            for p in school.profession_tree_uuid:
                tree = session.query(SpecialtyTreeV2).filter(SpecialtyTreeV2.profession_uuid == p,
                                                             SpecialtyTreeV2.specialty_v2_uuid.is_(None),
                                                             SpecialtyTreeV2.subspecialty_uuid.is_(None)) \
                    .one_or_none()
                if tree:
                    t = tree.as_object()
                    profession_uuids.append(t.treeUuid)
                    profession_uuids.append(t.profession.professionUuid)
                else:
                    profession_uuids.append(str(p))
                    logger.error("No tree entry found for profession_uuid %s", str(p))
            school_doc.update({'professions': profession_uuids})
            for c in school.country_or_region_uuid:
                if not c:
                    continue
                country = session.query(Country).get(c)
                if not country:
                    continue
                country_or_region_names.append(country.name)
                country_or_region_uuids.append(str(country.country_uuid))
            school_doc.update({'locationCompletions': country_or_region_names})
            school_doc.update({'countries': country_or_region_uuids})
            yield school_doc

    def get_es_insert_document(self, session, id):
        pass
