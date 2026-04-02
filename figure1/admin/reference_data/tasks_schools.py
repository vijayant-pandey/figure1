import logging
import pycountry
import re
import json
from pycountry import Subdivision
from typing import Iterator, Optional, TypedDict
from fuzzywuzzy import fuzz
from uuid import UUID
from google.api_core.exceptions import InvalidArgument
from figure1.common.models.db import Country

from figure1.admin.reference_data.model_methods import get_country_from_name, \
    get_subdivision_from_name, \
    get_country_from_alpha_3
from figure1.core import FirebaseTaskBase, celery_app
from figure1.common.models.db import School, ProfessionV2
from figure1.common.models.data import SchoolData

from figure1.common.elasticsearch import create_new_public_school_index

logger = logging.getLogger(__name__)


class SchoolDocument(TypedDict, total=False):
    """
    This really only has a use in this context because it is a transition to pushing into the schools table.

    """
    school_country_uuid: UUID
    school_region_uuid: Optional[UUID]
    school_profession_uuid: Optional[UUID]
    school_abbreviation: Optional[str]
    school_country: str
    school_region_name: Optional[str]
    school_name: str
    profession_name: str


def create_label(label=None):
    """
    Strip all whitespace characters and lowercase.
    :param label:
    :return:
    """
    label = re.sub(r'\s+', repl="", string=label)
    remove_prefix = re.sub(r'otherhcp-', repl="", string=label.lower())
    return remove_prefix


@celery_app.task(bind=True, base=FirebaseTaskBase, name='figure1.backend.initialize_schools')
def initialize_schools(self, clean=None):
    if clean:
        logger.error("Dropping data before loading")
        drop_schools(session=self.session)
    logger.info("Saving schools to postgres...")
    load_schools(session=self.session)
    logger.info("Starting task to re-index elasticsearch")
    create_new_public_school_index.delay()
    # _sync_schools(fs_client=self.fs_client, session=self.session)
    logging.info("Done updating schools")


def drop_schools(session):
    logger.error("Deleting data from schools")
    for i in session.query(School).all():
        i.profession_tree_uuid = []
        i.country_or_region_uuid = []
        session.add(i)
        session.flush()
    session.commit()
    logger.error("Data deleted")


def save_schools(session) -> Iterator[SchoolDocument]:
    """
    Reference School Data
    'school_name': school_name,
    'country_alpha3': country_alpha3,
    'country_name': country_name,
    'region_name': region_name,
    'school_abbrev': school_abbrev,
    'profession_name': profession_name,
    'profession_uuid': profession_uuid,

    """

    for school in SchoolData.load_all_schools():
        country_alpha_3 = school.get('country_alpha3')
        country_name = school.get('country_name')
        country: Optional[Country] = None
        sub_division: Subdivision

        if country_alpha_3:
            country = get_country_from_alpha_3(alpha_3=country_alpha_3, session=session)
        if country_name and not country:
            country = get_country_from_name(name=country_name, session=session)
        if not country:
            logger.error("Failed to find country for alpha code %s or country name %s", country_alpha_3, country_name)
            continue

        school_doc: SchoolDocument = {
            'school_name': school.get('school_name', ""),
            'school_abbreviation': school.get('school_abbrev', ""),
            'school_country': country.name,
            'school_country_uuid': country.country_uuid,
            'school_profession_uuid': school.get('profession_uuid'),
            'profession_name': school.get('profession_name'),
        }

        if not school.get('region_name'):
            logger.error("No region name for school %s", school)
            yield school_doc
            continue

        else:
            school_region_name = school.get('region_name', "")

        max_score = 0
        best_match: Subdivision
        subdiv: Subdivision

        for subdiv in pycountry.subdivisions.get(country_code=country.code):
            score = fuzz.ratio(subdiv.name.lower(), school_region_name.lower())
            if score > max_score:
                max_score = score
                best_match = subdiv
        if max_score >= 90:
            logger.debug("Subdivision %s matched %s in country %s with score %d",
                         best_match.name, school_region_name, country.name, max_score)
            sub_division = get_subdivision_from_name(country_uuid=country.country_uuid, name=best_match.name,
                                                     session=session)
            if sub_division:
                school_doc.update({'school_region_name': sub_division.name,
                                   'school_region_uuid': sub_division.country_uuid, })
        else:
            logger.debug("Could not find any match for %s, looked in country code %s", school_region_name,
                         country.name)
        yield school_doc


def load_schools(session):
    label_list = {}

    resident_uuid = session.query(ProfessionV2.specialty_uuid) \
        .filter(ProfessionV2.label == 'medicalresident').one_or_none()
    student_uuid = session.query(ProfessionV2.specialty_uuid) \
        .filter(ProfessionV2.label == 'medicalstudent').one_or_none()
    nurse_practitioner = session.query(ProfessionV2.specialty_uuid) \
        .filter(ProfessionV2.label == 'nursepractitioner').one_or_none()

    for i in session.query(ProfessionV2).all():
        uuid_list = []
        if i.label == 'physician':
            uuid_list.append(str(resident_uuid[0]))
            uuid_list.append(str(student_uuid[0]))
        if i.label == 'registerednurse':
            uuid_list.append(str(nurse_practitioner[0]))
        if i.label == 'dentist':
            label_list.update({'dentistry': [str(i.specialty_uuid)]})
        uuid_list.append(str(i.specialty_uuid))

        label_list.update({i.label: uuid_list})
    logger.info("Using label list %s", json.dumps(label_list))
    for school in save_schools(session=session):
        profession_label = create_label(school.get('profession_name'))
        if profession_label not in label_list.keys():
            logger.error("Profession %s not found in profession label list", profession_label)
        else:
            for u in label_list[profession_label]:
                School.create_or_update(name=school.get('school_name'),
                                        country_uuid=school.get('school_country_uuid'),
                                        subdivision_uuid=school.get('school_region_uuid'),
                                        abbreviation=school.get('school_abbreviation'),
                                        profession_uuid=u,
                                        skip_commit=True,
                                        session=session)
            session.flush()
    session.commit()


def _sync_schools(fs_client, session):
    """
    First get all distinct professions, then filter by country, then by region. This
    should result is a firestore collection that looks like profession -> country -> region.
    Each level has all schools that match to that level

    WARNING - This is currently disabled because some of the documents written are too large. The structure must
    be changed or this will never have complete data.
    """
    return None

    top_level_countries = Country.find_all_countries(session=session)
    for prof in School.get_distinct_professions(session=session):
        specialty_school = fs_client.collection('referenceData') \
            .document('schools_by_profession') \
            .collection(str(prof[0])) \
            .document('schools')
        profession_uuid = str(prof[0])
        firestore_data = {}
        for school in School.get_schools_by_profession(profession_tree_uuid=profession_uuid, session=session):
            firestore_data[str(school.school_uuid)] = school.as_dict()
        try:
            specialty_school.set(firestore_data)
        except InvalidArgument as ia:
            logger.error("Unable to create a schools document for profession %s, error: %s", str(prof[0]), ia)
        for country in top_level_countries:
            """ Add schools by country """
            sp_by_country = fs_client.collection('referenceData') \
                .document('schools_by_profession') \
                .collection(str(prof[0])) \
                .document(country.countryUuid)
            firestore_data = {}
            for school in School.get_schools_by_profession(profession_tree_uuid=profession_uuid,
                                                           country_or_region_uuid=country.countryUuid,
                                                           session=session):
                if not school:
                    continue
                firestore_data[str(school.school_uuid)] = school.as_dict()
            if not firestore_data:
                continue
            try:
                sp_by_country.set(firestore_data)
            except InvalidArgument as ia:
                logger.error("Unable to create a schools document for profession %s, in country %s,  error: %s",
                             str(prof[0]), str(country.countryUuid), ia)
            firestore_data = {}
            if country.countryRegions:
                for region in country.countryRegions:

                    sp_by_country_region = fs_client.collection('referenceData') \
                        .document('schools_by_profession') \
                        .collection(str(prof[0])) \
                        .document(country.countryUuid) \
                        .collection(region.regionUuid) \
                        .document('schools')
                    for region_school in School.get_schools_by_profession(profession_tree_uuid=profession_uuid,
                                                                          country_or_region_uuid=region.regionUuid,
                                                                          session=session):

                        if not region_school:
                            continue
                        firestore_data[str(region_school.school_uuid)] = region_school.as_dict()
                    if not firestore_data:
                        continue
                    try:
                        sp_by_country_region.set(firestore_data)
                    except InvalidArgument as ia:
                        logger.error("Unable to create a schools document for profession %s, in region %s, error: %s",
                                     str(prof[0]), str(region.regionUuid), ia)
