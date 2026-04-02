import uuid
import hashlib
import re
from abc import ABC

from typing import TypedDict, MutableSequence, Sequence, Iterable, Mapping, Callable, Tuple
from sqlalchemy import Column, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy import func
from . import Country
from figure1.core import Base, HasCreateUpdateDeleteTime


class SchoolDict(TypedDict):
    schoolUuid: str
    name: str
    countryUuid: MutableSequence[str]
    professionUuid: MutableSequence[str]
    abbreviation: str


class SchoolMapping(Mapping, ABC):
    school_uuid: UUID
    name: str
    school_name_hash: str
    country_or_region_uuid: Sequence[UUID]
    profession_tree_uuid: Sequence[UUID]
    abbreviation: str

    # Callable functions that should be type checked, this is really only functions that return a defined structure
    as_dict: Callable[[], SchoolDict]


class School(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "r_school"

    school_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    name = Column(Text, default="", nullable=True)
    school_name_hash = Column(Text, nullable=False)
    country_or_region_uuid = Column(ARRAY(UUID(as_uuid=True), ForeignKey(Country.country_uuid)), default=[])
    profession_tree_uuid = Column(ARRAY(UUID(as_uuid=True)), default=[])
    abbreviation = Column(Text, nullable=True)

    @staticmethod
    def get_distinct_professions(session):
        for proff in session.query(func.unnest(School.profession_tree_uuid)) \
                .distinct() \
                .all():
            yield proff

    @staticmethod
    def get_schools_by_profession(profession_tree_uuid,
                                  session,
                                  country_or_region_uuid=None) -> Sequence[SchoolMapping]:
        profession_tree_uuid = School._normalize_uuid(profession_tree_uuid)
        country_or_region_uuid = School._normalize_uuid(country_or_region_uuid)
        q = session.query(School)
        if country_or_region_uuid:
            q.filter(School.country_or_region_uuid.contains((country_or_region_uuid,)))

        q.filter(School.profession_tree_uuid.contains((profession_tree_uuid,)))
        return q.all()

    @staticmethod
    def get_schools_by_country_or_region(country_or_region_uuid, session) -> Sequence[Mapping]:
        return session.query(School) \
            .filter(School.country_or_region_uuid == country_or_region_uuid) \
            .all()

    @staticmethod
    def create_or_update(name,
                         country_uuid,
                         subdivision_uuid,
                         abbreviation,
                         session,
                         profession_uuid,
                         skip_commit=False):
        normalized_school_name_hash = School._normalize_and_hash(name)
        school = session.query(School).filter(School.school_name_hash == normalized_school_name_hash).one_or_none()
        if profession_uuid:
            profession_uuid = School._normalize_uuid(profession_uuid)
        if country_uuid:
            country_uuid = School._normalize_uuid(country_uuid)
        if subdivision_uuid:
            subdivision_uuid = School._normalize_uuid(subdivision_uuid)

        if not school:
            school = School()
            school.school_name_hash = normalized_school_name_hash
            school.school_uuid = uuid.uuid4()
            school.profession_tree_uuid = []
            school.country_or_region_uuid = []
            school.name = name

        country_list = set(school.country_or_region_uuid)
        profession_list = set(school.profession_tree_uuid)
        if subdivision_uuid:
            country_list.add(subdivision_uuid)
        if country_uuid:
            country_list.add(country_uuid)
        if profession_uuid:
            profession_list.add(profession_uuid)
        if abbreviation:
            school.abbreviation = abbreviation
        school.country_or_region_uuid = country_list
        school.profession_tree_uuid = profession_list
        session.add(school)
        session.flush()
        return school

    @staticmethod
    def _normalize_and_hash(value):
        v = str(value)
        v_no_spaces = re.sub(r'\s+', '', v)
        v_bytes = v_no_spaces.lower().encode(encoding='utf-8')
        return hashlib.blake2b(v_bytes).hexdigest()

    @staticmethod
    def _normalize_uuid(uuid_):
        if not uuid_:
            return None
        if not isinstance(uuid_, uuid.UUID):
            return uuid.UUID(uuid_)
        return uuid_

    @staticmethod
    def replace_profession(old_profession_uuid, new_profession_uuid, session):
        old_profession_uuid = School._normalize_uuid(old_profession_uuid)
        new_profession_uuid = School._normalize_uuid(new_profession_uuid)
        profession_filter = [School.profession_tree_uuid.contains(old_profession_uuid)]
        for school in session.query(School).filter(*profession_filter).all():
            prof_list = set(school.profession_tree_uuid)
            prof_list.add(new_profession_uuid)
            try:
                prof_list.remove(old_profession_uuid)
            except KeyError:
                pass
            school.profession_tree_uuid = prof_list
            session.add(school)
        session.flush()

    def as_dict(self) -> SchoolDict:
        return {
            'schoolUuid': str(self.school_uuid),
            'name': self.name,
            'countryUuid': [str(x) for x in self.country_or_region_uuid],
            'professionUuid': [str(x) for x in self.profession_tree_uuid],
            'abbreviation': self.abbreviation
        }
