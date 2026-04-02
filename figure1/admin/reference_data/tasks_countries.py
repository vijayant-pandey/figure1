import logging

import pycountry
from figure1.admin.reference_data.model_methods import find_all_subdivisions_of_country
from figure1.core import FirebaseTaskBase, celery_app
from figure1.common.models.db import Country


@celery_app.task(bind=True, base=FirebaseTaskBase, name='figure1.backend.initialize_countries')
def initialize_countries(self, clean=None):
    logger = logging.getLogger(__name__)
    logger.info("Saving countries to postgres...")
    _save_countries(session=self.session)
    logger.info("Syncing countries to firestore...")
    _sync_countries(fs_client=self.fs_client, session=self.session)
    logger.info("Done updating countries")


def _save_countries(session):
    logger = logging.getLogger(__name__)
    for country in pycountry.countries:
        country_path = country.alpha_2.lower()
        Country.create_or_update(name=country.name,
                                 code=country.alpha_2,
                                 alpha_3=country.alpha_3,
                                 type='Country',
                                 path_str=country.alpha_2.lower(),
                                 skip_commit=True,
                                 session=session)

        for subdivision in pycountry.subdivisions.get(country_code=country.alpha_2):
            subdivision_code = subdivision.code[subdivision.code.find('-') + 1:]
            if not subdivision.parent:
                path = '.'.join((country_path, subdivision_code.lower()))
            else:
                parent_path = subdivision.parent_code[subdivision.parent_code.find('-') + 1:].lower()
                path = '.'.join((country_path, parent_path, subdivision_code.lower()))

            Country.create_or_update(name=subdivision.name,
                                     code=subdivision_code,
                                     type=subdivision.type,
                                     path_str=path,
                                     skip_commit=True,
                                     session=session)
    try:
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f'Failed to update countries: {e}')


def _sync_countries(fs_client, session):
    batch = fs_client.batch()
    top_level_countries = fs_client.collection('referenceData').document('countriesV2').collection('countries')
    top_level_regions = fs_client.collection('referenceData').document('countriesV2').collection('regions')
    count = 0
    for c in Country.find_all_countries(session):
        doc = top_level_countries.document(c.countryUuid)
        batch.set(doc, c.dict())
        count += 1
        if not count % 500:
            batch.commit()
        # This is currently broken, have to revisit this logic
        # for i in c.regions:
        #     region_doc = top_level_regions.document(i.regionUuid)
        #     batch.set(region_doc, {**i.dict(), **c.dict()})
        #     count += 1
        #     if not count % 500:
        #         batch.commit()
    batch.commit()
