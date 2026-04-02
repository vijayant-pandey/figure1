import csv
import logging

import re
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import Session

from figure1.core import managed_session
from figure1.common.models.db import LegacySpecialty, LegacySpecialtyType, LegacySpecialtyProfession, SpecialtyV2, \
    SpecialtyTreeV2, ProfessionV2


def _create_label(label=None):
    """
    Strip all whitespace characters and lowercase.
    :param label:
    :return:
    """
    label = re.sub(r'\s+', repl="", string=label)
    return label.lower()


@managed_session
def upload_specialty_mapping(filename: str, session: Session):
    with open(filename, mode='r', newline='') as file:
        reader = csv.reader(file)
        for line in reader:
            legacy_profession = line.pop(0)
            legacy_specialty = line.pop(0)
            pro_category = line.pop(0)
            pro_profession = _create_label(line.pop(0))
            pro_specialty = _create_label(line.pop(0))
            pro_subspecialty = _create_label(line.pop(0))

            ls = session.query(LegacySpecialty) \
                .join(LegacySpecialtyProfession,
                      LegacySpecialtyProfession.profession_uuid == LegacySpecialty.profession_uuid) \
                .join(LegacySpecialtyType, LegacySpecialtyType.type_uuid == LegacySpecialty.type_uuid) \
                .filter(LegacySpecialtyProfession.name == legacy_profession,
                        LegacySpecialtyType.name == legacy_specialty) \
                .first()

            if not ls:
                logging.warning(f"Legacy profession error: {legacy_profession}, {legacy_specialty}")

            profession = session.query(ProfessionV2).filter(ProfessionV2.label == pro_profession).first()
            specialty = session.query(SpecialtyV2).filter(SpecialtyV2.label == pro_specialty).first()
            subspecialty = session.query(SpecialtyV2).filter(SpecialtyV2.label == pro_subspecialty).first()

            tree = session.query(SpecialtyTreeV2) \
                .filter(SpecialtyTreeV2.profession == profession,
                        SpecialtyTreeV2.specialty == specialty,
                        SpecialtyTreeV2.subspecialty == subspecialty) \
                .one_or_none()

            if not tree:
                logging.warning(f"failed to find pro mapping for legacy specialty: "
                                f"{legacy_profession}/{legacy_specialty}")
            else:
                ls.pro_tree_uuid = tree.specialty_uuid

        try:
            session.commit()
        except DatabaseError as e:
            session.rollback()
            logging.error(f"Failed to save specialty migration data: {e}")
            raise
