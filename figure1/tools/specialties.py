import re
import uuid
import csv
import os
import logging
from typing import Optional, List
from pydantic import BaseModel, parse_obj_as, parse_raw_as, validator
from figure1.core import managed_session
from figure1.common.models.db import SpecialtyV2, ProfessionV2, SpecialtyTreeV2
from figure1.exceptions import SpecialtyError

logger = logging.getLogger(__name__)


class DuplicateSpecialty(SpecialtyError):
    pass


class ProfessionUploadCSV(BaseModel):
    profession_category: str
    profession_name: str

    def add_model(self):
        add_profession(profession_name=self.profession_name, profession_category=self.profession_category)


class SpecialtyUploadCSV(BaseModel):
    specialty_name: str
    is_valid_case_tag: bool = False
    is_valid_interest: bool = False

    @validator('is_valid_case_tag', 'is_valid_interest', pre=True)
    def validate_boolean(cls, value):
        if isinstance(value, bool):
            return value
        v = create_label(value)
        if v == 'false':
            return False
        if v == 'true':
            return True
        return False

    def add_model(self):
        add_specialty(specialty_name=self.specialty_name,
                      is_valid_interest=self.is_valid_interest,
                      is_valid_case_tag=self.is_valid_case_tag)


class SpecialtyTreeUploadCSV(BaseModel):
    profession_name: str
    specialty_name: Optional[str]
    subspecialty_name: Optional[str]
    onboarding_display_label: str
    profile_display_label: str
    case_comment_display_label: str

    def add_model(self):
        add_specialty_tree(onboarding_display_label=self.onboarding_display_label,
                           profile_display_label=self.profile_display_label,
                           case_comment_display_label=self.case_comment_display_label,
                           profession_name=self.profession_name,
                           specialty_name=self.specialty_name,
                           sub_specialty_name=self.subspecialty_name)


def create_label(label=None):
    """
    Strip all whitespace characters and lowercase.
    :param label:
    :return:
    """
    label = re.sub(r'\s+', repl="", string=label)
    return label.lower()


def get_valid_categories(session):
    for category in session.query(ProfessionV2.profession_category) \
            .group_by(ProfessionV2.profession_category) \
            .all():
        if category[0]:
            yield category[0]


@managed_session
def add_profession(profession_name, profession_category, session=None, create_category=True):
    profession_label = create_label(profession_name)
    existing = session.query(ProfessionV2).filter(ProfessionV2.label == profession_label).first()
    if existing:
        return existing
    category_list = list(get_valid_categories(session=session))
    logger.debug(category_list)
    try:
        category_index = [create_label(x) for x in category_list].index(create_label(profession_category))
    except ValueError as ve:
        if create_category:
            logger.info("Category invalid - creating it")
            pass
        else:
            raise SpecialtyError(msg="Category is invalid") from ve

    new_profession = ProfessionV2()
    new_profession.specialty_uuid = uuid.uuid4()
    new_profession.name = profession_name
    new_profession.label = profession_label
    if create_category:
        new_profession.profession_category = profession_category
    else:
        new_profession.profession_category = category_list[category_index]
    return session.merge(new_profession)


@managed_session
def add_specialty(specialty_name, is_valid_interest=False, is_valid_case_tag=False, session=None):
    specialty_label = create_label(specialty_name)
    existing = session.query(SpecialtyV2).filter(SpecialtyV2.label == specialty_label).first()
    if existing:
        return existing
    specialty = SpecialtyV2()
    specialty.specialty_uuid = uuid.uuid4()
    specialty.name = specialty_name
    specialty.label = specialty_label
    specialty.is_valid_case_tag = is_valid_case_tag
    specialty.is_valid_interest = is_valid_interest
    return session.merge(specialty)


@managed_session
def add_specialty_tree(onboarding_display_label,
                       case_comment_display_label,
                       profile_display_label,
                       profession_name=None,
                       specialty_name=None,
                       sub_specialty_name=None,
                       session=None):
    specialty_uuid = None
    sub_specialty_uuid = None
    profession = session.query(ProfessionV2.specialty_uuid) \
        .filter(ProfessionV2.label == create_label(profession_name)).one_or_none()
    if not profession:
        raise SpecialtyError(msg="No matching profession found")
    profession_uuid = profession[0]

    if specialty_name:
        specialty = session.query(SpecialtyV2.specialty_uuid) \
            .filter(SpecialtyV2.label == create_label(specialty_name)) \
            .one_or_none()
        if not specialty:
            raise SpecialtyError(msg="Specialty name passed, but no match found")
        specialty_uuid = specialty[0]

    if sub_specialty_name:
        sub_specialty = session.query(SpecialtyV2.specialty_uuid) \
            .filter(SpecialtyV2.label == create_label(sub_specialty_name)) \
            .one_or_none()
        if not sub_specialty:
            raise SpecialtyError(msg="Sub Specialty name passed, but no match found")
        sub_specialty_uuid = sub_specialty[0]

    q = session.query(SpecialtyTreeV2).filter(SpecialtyTreeV2.profession_uuid == profession_uuid)
    if specialty_uuid:
        q = q.filter(SpecialtyTreeV2.specialty_v2_uuid == specialty_uuid)
        if sub_specialty_uuid:
            q = q.filter(SpecialtyTreeV2.subspecialty_uuid == sub_specialty_uuid)
    if q.first():
        raise SpecialtyError(msg="Tree with these parameters already exists")

    tree = SpecialtyTreeV2()
    tree.specialty_uuid = uuid.uuid4()
    tree.profession_uuid = profession_uuid
    if specialty_uuid:
        tree.specialty_v2_uuid = specialty_uuid
        if sub_specialty_uuid:
            tree.subspecialty_uuid = sub_specialty_uuid
    tree.profile_display_label = profile_display_label
    tree.case_comment_display_label = case_comment_display_label
    tree.onboarding_display_label = onboarding_display_label

    return session.merge(tree)


def handle_csv_upload(csv_file_path, upload_type):
    if os.path.exists(csv_file_path):
        parsed_list = None
        with open(csv_file_path, mode="r") as csv_fo:
            if upload_type == 'profession':
                parsed_list = parse_obj_as(List[ProfessionUploadCSV],
                                           list(csv.DictReader(csv_fo,
                                                               fieldnames=list(ProfessionUploadCSV.__fields__))))
            if upload_type == 'specialty':
                parsed_list = parse_obj_as(List[SpecialtyUploadCSV],
                                           list(csv.DictReader(csv_fo,
                                                               fieldnames=list(SpecialtyUploadCSV.__fields__))))

            if upload_type == 'tree':
                parsed_list = parse_obj_as(List[SpecialtyTreeUploadCSV],
                                           list(csv.DictReader(csv_fo,
                                                               fieldnames=list(SpecialtyTreeUploadCSV.__fields__))))
        if parsed_list:
            for line in parsed_list:
                try:
                    line.add_model()
                except SpecialtyError:
                    pass
                if upload_type == 'profession':
                    if line.profession_category == 'Other HCP' or line.profession_category == 'Other Student':
                        create_tree_entry = SpecialtyTreeUploadCSV(profession_name=line.profession_name,
                                                                   onboarding_display_label=line.profession_name,
                                                                   case_comment_display_label=line.profession_name,
                                                                   profile_display_label=line.profession_name)
                        try:
                            create_tree_entry.add_model()
                        except SpecialtyError:
                            pass


def handle_json_upload(data, upload_type):
    if upload_type not in ['profession', 'specialty', 'tree']:
        raise SpecialtyError("Invalid upload type")
    parsed_list = None
    if data and isinstance(data, list):
        if upload_type == 'profession':
            parsed_list = parse_obj_as(List[ProfessionUploadCSV], data)
        if upload_type == 'specialty':
            parsed_list = parse_obj_as(List[SpecialtyUploadCSV], data)
        if upload_type == 'tree':
            parsed_list = parse_obj_as(List[SpecialtyTreeUploadCSV], data)
    else:
        raise SpecialtyError("No Data found or incorrect format")

    if parsed_list:
        for line in parsed_list:
            try:
                line.add_model()
            except SpecialtyError:
                pass
            if upload_type == 'profession':
                if line.profession_category == 'Other HCP' or line.profession_category == 'Other Student':
                    create_tree_entry = SpecialtyTreeUploadCSV(profession_name=line.profession_name,
                                                               onboarding_display_label=line.profession_name,
                                                               case_comment_display_label=line.profession_name,
                                                               profile_display_label=line.profession_name)
                    try:
                        create_tree_entry.add_model()
                    except SpecialtyError:
                        pass
