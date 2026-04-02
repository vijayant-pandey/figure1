import re
import os
import uuid
import csv
import logging
from sqlalchemy import func

from typing import Optional, Union
from figure1.core import managed_session
from figure1.common.models.db import SpecialtyTreeV2, \
    ProfessionV2, \
    SpecialtyV2, \
    CaseSpecialtyV2, \
    CommunicationSettings

from figure1.common.models.db.archived.case_specialty_v1 import CaseSpecialty
from figure1.common.models.db.reference_data_models.r_communication_preferences_default_settings import \
    SpecialtyCommunicationSettings

logger = logging.getLogger('figure1.migrate_specialties')


def create_label(label=None):
    """
    Strip all whitespace characters and lowercase.
    :param label:
    :return:
    """
    label = re.sub(r'\s+', repl="", string=label)
    return label.lower()


def import_profession(data, session) -> Optional[ProfessionV2]:
    """
    Add profession to table. If it exists in the previous version, then get the uuid, if it exists in this
    version, then return None

    :param data:
    :param session:
    :return:
    """
    if session.query(ProfessionV2).filter(ProfessionV2.label == data.get('label')).one_or_none():
        return None

    p = ProfessionV2()
    p.name = data.get('name')
    p.label = data.get('label')
    p.specialty_uuid = uuid.uuid4()
    return p


def import_specialty(data, session) -> Union[SpecialtyV2, None]:
    """
    Add specialty to table, if it exists on the previous version, then use the same uuid. If it exists in
    this version, then return

    :param data:
    :param session:
    :param is_sub_specialty:
    :return:
    """

    if session.query(SpecialtyV2).filter(SpecialtyV2.label == data.get('label')).one_or_none():
        return None
    p = SpecialtyV2()
    p.name = data.get('name')
    p.label = data.get('label')
    p.is_valid_case_tag = data.get('include_in_tagging')
    p.is_valid_interest = data.get('include_in_interests')
    p.specialty_uuid = uuid.uuid4()
    return p


def handle_specialty_data_line(data_line, session):
    """
    data structure is <name:str>,<depth:int>,<include_in_interests:bool>,<include_in_tagging:bool>
    The bools are in 'YES' or 'NO' form, the depth indicates profession/specialty/subspecialty, so can be 0,1,2

    The label is created by lowercasing and removing all whitespace from the string, this is used for matching to
    ensure there are no duplicates.

    :return:
    """

    # Make sure the line is sane
    if not isinstance(data_line, list):
        raise ValueError(f"Data line is not in expected format {data_line}")
    name = data_line.pop(0)
    depth = int(data_line.pop(0))
    include_in_interests = data_line.pop(0)
    include_in_tagging = data_line.pop(0)

    if create_label(include_in_interests) == 'yes':
        include_in_interests = True
    else:
        include_in_interests = False
    if create_label(include_in_tagging) == 'yes':
        include_in_tagging = True
    else:
        include_in_tagging = False

    label = create_label(name)
    data = dict(include_in_tagging=include_in_tagging,
                include_in_interests=include_in_interests,
                name=name,
                label=label)
    spec = None
    if depth == 0:
        spec = import_profession(data=data, session=session)
    if depth == 1:
        spec = import_specialty(data=data, session=session)
    if depth == 2:
        spec = import_specialty(data=data, session=session)
    if spec:
        session.add(spec)


def _set_default_differential_subscription(specialty_tree_uuid, differential_label, session):
    cs = session.query(CommunicationSettings) \
        .filter(func.lower(func.replace(CommunicationSettings.communication_name, ' ', '')) == differential_label) \
        .one_or_none()

    if not cs:
        return
    comm_setting = SpecialtyCommunicationSettings()
    comm_setting.communication_uuid = cs.communication_uuid
    comm_setting.tree_uuid = specialty_tree_uuid
    comm_setting.communication_default_setting = True
    return session.merge(comm_setting)


def _handle_differential_subscriptions(specialty_uuid, settings, session):
    labels = ['cancer', 'cardiology', 'dermatology', 'emergencymedicine', 'hematology', 'neurology', 'orthopedics',
              'pediatrics', 'primarycare', 'rheumatology']
    for label in labels:
        value = settings.pop(0) == 'TRUE'
        if value:
            _set_default_differential_subscription(specialty_tree_uuid=specialty_uuid,
                                                   differential_label=label,
                                                   session=session)
        else:
            continue


def handle_tree_data(data_line, session):
    """
    This creates a tree structure from an array passed in from parsing a csv structure. The array is expected to have
    a minimum of 17 elements, any additional elements are ignored.

    The structure is:
    category: str
    profession: str
    specialty: str
    subspecialty: str
    onboarding_display: str
    profile_display: str
    case_comment_display: str
    differential_cancer: bool
    differential_cardiology: bool
    differential_dermatology: bool
    differential_emergencymedicine: bool
    differential_hematology: bool
    differential_neurology: bool
    differential_orthopedics: bool
    differential_pediatrics: bool
    differential_primarycare: bool
    differential_rheumatology: bool

    The category is used initially to for profession selection, in many cases, the profession and category are the same,
    but not in all cases.
    The specialty and subspecialty are optional, but generally it isn't necessary to have a tree entry for just a
    profession.
    The three display fields are friendly names to display for a user in those contexts.

    There is an attempt made to reuse tree_uuids from the previous version of the specialty tree, however if an exact
    match isn't found for the full tree, then a new id is generated.

    :return:
    :param data_line:
    :param session:
    :return:
    """

    if not isinstance(data_line, list):
        raise ValueError(f"Data line is not in expected format {data_line}")

    category = data_line.pop(0)
    profession = data_line.pop(0)
    specialty = data_line.pop(0)
    subspecialty = data_line.pop(0)
    onboarding_display = data_line.pop(0)
    profile_display = data_line.pop(0)
    case_comment_display = data_line.pop(0)
    differential_subscriptions = data_line

    tree = SpecialtyTreeV2()
    tree.case_comment_display_label = case_comment_display
    tree.profile_display_label = profile_display
    tree.onboarding_display_label = onboarding_display
    tree.specialty_uuid = uuid.uuid4()

    duplicate_filter = []

    if subspecialty:
        subspecialty_label = create_label(subspecialty)
        subspec: SpecialtyV2 = session.query(SpecialtyV2).filter(SpecialtyV2.label == subspecialty_label).one()
        tree.subspecialty_uuid = subspec.specialty_uuid
        duplicate_filter.append(SpecialtyTreeV2.subspecialty_uuid == tree.subspecialty_uuid)
    else:
        duplicate_filter.append(SpecialtyTreeV2.subspecialty_uuid.is_(None))

    if specialty:
        specialty_label = create_label(specialty)
        spec: SpecialtyV2 = session.query(SpecialtyV2).filter(SpecialtyV2.label == specialty_label).one()
        tree.specialty_v2_uuid = spec.specialty_uuid
        duplicate_filter.append(SpecialtyTreeV2.specialty_v2_uuid == tree.specialty_v2_uuid)
    else:
        duplicate_filter.append(SpecialtyTreeV2.specialty_v2_uuid.is_(None))

    if profession:
        profession_label = create_label(profession)
        prof: ProfessionV2 = session.query(ProfessionV2).filter(ProfessionV2.label == profession_label).one()
        if not prof.profession_category:
            prof.profession_category = category
            session.add(prof)
        tree.profession_uuid = prof.specialty_uuid
        duplicate_filter.append(SpecialtyTreeV2.profession_uuid == tree.profession_uuid)

    s = session.query(SpecialtyTreeV2).filter(*duplicate_filter).one_or_none()
    if s:
        logger.info("Tree already exists")
        specialty_uuid = s.specialty_uuid
    else:
        session.add(tree)
        specialty_uuid = tree.specialty_uuid

    _handle_differential_subscriptions(specialty_uuid=specialty_uuid,
                                       settings=differential_subscriptions,
                                       session=session)


def update_case_specialties(session):
    logger.info("Setting case specialties")

    def get_specialty(uuid, session):
        specialty = session.query(ProfessionV2).filter(ProfessionV2.specialty_uuid == uuid).one_or_none()
        if specialty:
            logger.error("Profession - not a valid case tag")
            return None
        if not specialty:
            specialty = session.query(SpecialtyV2).filter(SpecialtyV2.specialty_uuid == uuid).one()
        return specialty

    for cs in session.query(CaseSpecialty).filter(CaseSpecialty.specialty_uuid.is_(None)).all():
        s = get_specialty(uuid=cs.specialty_uuid, session=session)
        if not s:
            return None
        if s:
            cs.specialty_v2_uuid = s.specialty_uuid
            session.add(cs)
            session.flush()
        CaseSpecialtyV2.create(case_uuid=cs.case_uuid, specialty_uuid=cs.specialty_uuid, session=session)
    logger.info("Case specialties updated")


@managed_session
def load_specialty_data(filename, session, data_type, apply=False):
    if data_type not in ['specialty', 'tree']:
        return {}
    logger.info("Apply set to %s", apply)
    if os.path.isfile(filename):
        with open(filename, mode='r', newline='') as fn:
            reader = csv.reader(fn)
            for line in reader:
                if data_type == 'specialty':
                    handle_specialty_data_line(data_line=line, session=session)
                elif data_type == 'tree':
                    handle_tree_data(data_line=line, session=session)

                else:
                    print("Unknown data type")
    else:
        return {"Error": f"Filename {filename} is not a file"}
    return


@managed_session
def load_from_database(session, data_type):
    if data_type not in ['specialty_map']:
        return {}
    update_case_specialties(session=session)
    return {'success': 'specialties mapped'}
