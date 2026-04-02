import logging
import requests
import csv
from sqlalchemy import or_
from tempfile import NamedTemporaryFile
from figure1.common.models.db import PublicSpecialtyTaxonomy, \
    SpecialtyTaxonomyMap, \
    SpecialtyV2, \
    ProfessionV2, \
    SpecialtyTreeV2
from figure1.core import managed_session
from figure1.common.types import PublicTaxonomyModel

logger = logging.getLogger(__name__)


class TaxonomyMatchException(Exception):
    pass


class SpecialtyNotFound(TaxonomyMatchException):
    pass


class SpecialtyMapExists(TaxonomyMatchException):
    pass


def _generate_class_instance(row):
    public_specialty_taxonomy = PublicSpecialtyTaxonomy()
    for k, v in row.items():
        setattr(public_specialty_taxonomy, k, v)
    return public_specialty_taxonomy


@managed_session
def update_public_specialty_taxonomy(version=210, session=None):
    taxonomy_url = f"https://www.nucc.org/images/stories/CSV/nucc_taxonomy_{version}.csv"
    data = requests.get(url=taxonomy_url)

    if data.status_code >= 400:
        logger.error("Error or file not found")
        return {"Error": data.status_code}

    elif data.content:
        with NamedTemporaryFile(mode="w+t") as buff:
            buff.write(data.text)
            buff.seek(0)
            reader = csv.DictReader(buff,
                                    fieldnames=["code",
                                                "grouping",
                                                "classification",
                                                "specialization",
                                                "definition",
                                                "notes",
                                                "display_name",
                                                "section"], lineterminator='\r\n')
            for row in reader:
                if reader.line_num <= 1:
                    logger.info("Skip header line")
                    continue
                else:
                    session.merge(_generate_class_instance(row))
    return {"success": "public taxonomy updated"}


def _find_profession_by_name(profession_name):
    profession = ProfessionV2.q.filter(ProfessionV2.name == profession_name).first()
    if profession:
        return profession.as_object()
    return None


def _find_specialty_by_name(specialty_name):
    specialty = SpecialtyV2.q.filter(SpecialtyV2.name == specialty_name,
                                     or_(SpecialtyV2.specialty_type == 'specialty',
                                         SpecialtyV2.specialty_type == 'subspecialty'))
    if specialty.count() == 1:
        return specialty.first().as_object()
    elif specialty.count() > 1:
        logger.error("More than one specialty found")
        raise Exception
    return None


def _get_map_definitions(tree_uuid, taxonomy_code):
    csv_row = []
    tree = SpecialtyTreeV2.q.filter(SpecialtyTreeV2.specialty_uuid == tree_uuid).one_or_none()
    tax = PublicSpecialtyTaxonomy.q.filter(PublicSpecialtyTaxonomy.code == taxonomy_code).one_or_none()

    if tax:
        csv_row.extend([tax.code, tax.grouping, tax.classification, tax.specialization])
    if tree:
        tree_object = tree.as_object()
        if tree_object.profession:
            csv_row.append(tree_object.profession.professionName)
        else:
            csv_row.append('None')
        if tree_object.specialty:
            csv_row.append(tree_object.specialty.specialtyName)
        else:
            csv_row.append('None')
        if tree_object.subspecialty:
            csv_row.append(tree_object.subspecialty.specialtyName)
        else:
            csv_row.append('None')

    return csv_row


@managed_session
def run_tax_map(session=None):
    q = session.query(PublicSpecialtyTaxonomy.code)
    logger.info("Running %s users", q.count())
    count = 0
    total_count = q.count()
    for i in q.all():
        logger.info("Running Taxonomy number %s", i[0])
        try:
            tree = link_taxonomy(i[0])
            s = SpecialtyTaxonomyMap()
            s.taxonomy_code = i[0]
            s.specialty_tree_uuid = tree.treeUuid
            session.add(s)
            count += 1
        except TaxonomyMatchException:
            logger.error("No tree found")
        logger.info("Finished %s", i[0])
    logger.info("Found %s trees out of %s", count, total_count)


@managed_session
def map_tree_uuid(taxonomy_code, tree_uuid, session=None, force=False):
    if SpecialtyTaxonomyMap.q.get(taxonomy_code) and force is False:
        logger.error("Taxonomy %s is already mapped")
        raise SpecialtyMapExists
    s = SpecialtyTaxonomyMap()
    s.taxonomy_code = taxonomy_code
    s.specialty_tree_uuid = tree_uuid
    session.merge(s)


@managed_session
def delete_taxonomy_map(taxonomy_code, session=None):
    session.query(SpecialtyTaxonomyMap).filter(SpecialtyTaxonomyMap.taxonomy_code == taxonomy_code).delete()


@managed_session
def get_taxonomy_map(taxonomy_number=None, session=None):
    """
    Generator that returns zip objects of the form (fieldname, fieldvalue)
    """

    fieldnames = ["code",
                  "grouping",
                  "classification",
                  "specialization",
                  "ProfessionName",
                  "SpecialtyName",
                  "SubspecialtyName"]
    if taxonomy_number:
        tax = SpecialtyTaxonomyMap.q.get(taxonomy_number)
        if tax:
            row = _get_map_definitions(tree_uuid=str(tax.specialty_tree_uuid),
                                       taxonomy_code=tax.taxonomy_code)
            yield zip(fieldnames, row)
    else:
        for i in SpecialtyTaxonomyMap.q.all():
            row = _get_map_definitions(tree_uuid=str(i.specialty_tree_uuid),
                                       taxonomy_code=i.taxonomy_code)
            yield zip(fieldnames, row)


def link_taxonomy(taxonomy_number):
    if SpecialtyTaxonomyMap.q.get(taxonomy_number):
        logger.error("Taxonomy %s is already mapped")
        raise SpecialtyMapExists

    taxonomy = PublicSpecialtyTaxonomy.q.get(taxonomy_number)
    if not taxonomy:
        logger.error("Cannot find taxonomy number %s", taxonomy_number)
        raise TaxonomyMatchException

    taxonomy_model: PublicTaxonomyModel = taxonomy.as_object()
    q = SpecialtyTreeV2.q.filter(SpecialtyTreeV2.specialty_type == 'tree')
    if taxonomy_model.grouping == 'Allopathic & Osteopathic Physicians':
        physician = _find_profession_by_name('Physician')
        if physician:
            taxonomy_model.profession = physician
            q = q.filter(SpecialtyTreeV2.profession_uuid == physician.professionUuid)
        else:
            raise SpecialtyNotFound

    elif taxonomy_model.grouping == 'Physician Assistants & Advanced Practice Nursing Providers':
        if taxonomy_model.classification:
            profession = _find_profession_by_name(taxonomy_model.classification)
            if profession:
                q = q.filter(SpecialtyTreeV2.profession_uuid == profession.professionUuid)
                if taxonomy_model.specialization:
                    specialty = _find_specialty_by_name(taxonomy_model.specialization)
                    if specialty:
                        taxonomy_model.specialty = specialty
                        q = q.filter(SpecialtyTreeV2.specialty_v2_uuid == specialty.specialtyUuid)
                    else:
                        raise SpecialtyNotFound
                else:
                    q = q.filter(SpecialtyTreeV2.specialty_v2_uuid.is_(None))
                tree = q.first()
                if tree:
                    logger.info("Got tree %s", tree.as_dict())
                    return tree.as_object()
                else:
                    logger.error("No tree uuid found, used query %s", q)
                    raise SpecialtyNotFound

    else:
        profession = _find_profession_by_name(taxonomy_model.grouping)
        logger.info("Tried to find %s", taxonomy_model.grouping)
        if profession:
            taxonomy_model.profession = profession
            q = q.filter(SpecialtyTreeV2.profession_uuid == profession.professionUuid)
        else:
            raise SpecialtyNotFound

    if taxonomy_model.classification:
        specialty = _find_specialty_by_name(taxonomy_model.classification)
        if specialty:
            taxonomy_model.specialty = specialty
            q = q.filter(SpecialtyTreeV2.specialty_v2_uuid == specialty.specialtyUuid)
        else:
            raise SpecialtyNotFound
        if taxonomy_model.specialization:
            sub_specialty = _find_specialty_by_name(taxonomy_model.specialization)
            if sub_specialty:
                taxonomy_model.subspecialty = sub_specialty
                q = q.filter(SpecialtyTreeV2.subspecialty_uuid == sub_specialty.specialtyUuid)
            else:
                raise SpecialtyNotFound
        else:
            q = q.filter(SpecialtyTreeV2.subspecialty_uuid.is_(None))
            logger.error("No specialization for this taxonomy entry")
    else:
        q = q.filter(SpecialtyTreeV2.specialty_v2_uuid.is_(None))
        logger.error("No classification for this taxonomy entry")
    logger.info("Built up model %s", taxonomy_model.json())
    tree = q.first()
    if tree:
        logger.info("Got tree %s", tree.as_dict())
        return tree.as_object()
    else:
        logger.error("No tree uuid found, used query %s", q)
        raise SpecialtyNotFound
