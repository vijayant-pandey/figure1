import csv
import json
import logging
import os
import uuid
from pydantic.types import UUID

from figure1.common.types import SchoolReferenceDocument
from figure1.exceptions import ReferenceDataReadError
from typing import Iterator

logger = logging.getLogger(__name__)


def _get_path(filename):
    path = os.path.join(os.path.dirname(__file__), filename)
    if os.path.exists(path):
        return path
    else:
        logger.error(f"Path {path} cannot be found")
        return None


def _load_json(path):
    with open(path, mode='r') as fp:
        try:
            return json.load(fp)
        except json.JSONDecodeError as json_error:
            logger.error(f"Failed to load json file {path}")


def _load_csv(path):
    data = []
    with open(path, mode='r') as fp:
        for row in csv.reader(fp):
            data.append(list((v.strip() for v in row)))
    return data


class SpecialtyData:
    @staticmethod
    def load_specialties(filename=None):
        """

        :param filename:
        :return:
        """
        if not filename:
            filename = 'specialties.csv'
        path = _get_path(filename=filename)
        return _load_csv(path) if path else None


class SchoolData:
    @staticmethod
    def load_all_schools() -> Iterator[SchoolReferenceDocument]:
        """
        No filename argument is taken here because both NA schools and international schools are returned. The
        filenames are assumed to be the defaults.
        Reference Data errors are logged, but not considered fatal.

        :return: Iterator[SchoolReferenceDocument]
        """
        try:
            for s in SchoolData.load_schools():
                yield s
            for i in SchoolData.load_international_schools():
                yield i
        except ReferenceDataReadError as re:
            logger.error("Failed to read data %s", re)

    @staticmethod
    def load_schools(filename: str = None, international: bool = False) -> Iterator[SchoolReferenceDocument]:
        """
        Data Example for CAN/US schools - should be 8 elements
        Rush Medical College,USA,United States,Illinois,Physician,,Physician,7275dbe6-7416-4352-b2d9-ebf3d580cc0d
        International School example - should be 7 elements
        Spinghar Institute Of Higher Education,AFG,Afghanistan,Nangarhar,,Physician,7275dbe6-7416-4352-b2d9-ebf3d580cc0d

        This yields an iterator of schools that returns a dict for every school. The dicts for international and NA
        schools is the same, this function normalizes them into the same structure.

        :param filename: str
        :param international: bool
        :return: Iterator[dict]

        """
        if not filename:
            filename = 'schoolsV2.csv'
        path = _get_path(filename=filename)
        for school in _load_csv(path):
            if international:
                if len(school) != 7:
                    raise ReferenceDataReadError(
                        msg="Invalid row length %d for row %s" % (len(school), ",".join(school)))
            else:
                if len(school) != 8:
                    raise ReferenceDataReadError(
                        msg="Invalid row length %d for row %s" % (len(school), ",".join(school)))
            school_name = school.pop(0)
            country_alpha3 = school.pop(0)
            country_name = school.pop(0)
            region_name = school.pop(0)
            if not international:
                specialty_name_1 = school.pop(0)
            school_abbrev = school.pop(0)
            profession_name = school.pop(0)
            profession_uuid = uuid.UUID(school.pop(0), version=4)

            yield {
                'school_name': school_name,
                'country_alpha3': country_alpha3,
                'country_name': country_name,
                'region_name': region_name,
                'school_abbrev': school_abbrev,
                'profession_name': profession_name,
                'profession_uuid': profession_uuid,
            }

    @staticmethod
    def load_international_schools(filename=None) -> Iterator[SchoolReferenceDocument]:
        """
        This function parses international schools, exceptions should be handled by caller. This should be used if there
        is an additional file or a different file from default to read in.
        :param filename:
        :return: Iterator[dict]
        """
        if not filename:
            filename = 'international_schools.csv'
        for school in SchoolData.load_schools(filename=filename, international=True):
            yield school


class CommunicationActivityGroupData:
    @staticmethod
    def load_activity_groups(filename=None):
        if not filename:
            filename = 'communications_groups.json'
        path = _get_path(filename=filename)
        return _load_json(path) if path else None


class LabelData:
    @staticmethod
    def load_labels(filename=None):
        if not filename:
            filename = 'labels.csv'
        path = _get_path(filename=filename)
        return _load_csv(path) if path else None


class LegacySpecialtyMigrationData:
    @staticmethod
    def load_mappings():
        filename = 'legacy_specialty_migration.json'
        path = _get_path(filename=filename)
        return _load_json(path) if path else None


class StandaloneEmailData:
    @staticmethod
    def load_standalone_emails():
        filename = "standalone_emails.json"
        path = _get_path(filename=filename)
        return _load_json(path) if path else None
