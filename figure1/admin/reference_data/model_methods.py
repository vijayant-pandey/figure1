import logging
from sqlalchemy import func
from typing import Optional
from figure1.core import managed_session
from figure1.common.models.db import Country, \
    LegacySpecialty, \
    LegacySpecialtyType, \
    LegacySpecialtyProfession, \
    School, \
    Label, \
    SpecialtyV2, \
    SpecialtyTreeV2, \
    ProfessionV2

from figure1.common.models.db.m_user_verification_tag import VerificationTag

logger = logging.getLogger(__name__)


def get_country_from_name(name, session=None) -> Optional[Country]:
    if not name:
        return None

    return session.query(Country). \
        filter(Country.name == name,
               func.nlevel(Country.path) == 1). \
        one_or_none()


def get_country_from_alpha_3(alpha_3, session=None) -> Optional[Country]:
    if not alpha_3:
        return None

    return session.query(Country). \
        filter(Country.alpha_3 == alpha_3,
               func.nlevel(Country.path) == 1). \
        one_or_none()


def get_subdivision_from_name(country_uuid, name, session=None):
    if not name:
        return None

    country = session.query(Country) \
        .filter(Country.country_uuid == country_uuid).one()

    return session.query(Country). \
        filter(Country.path.descendant_of(country.path),
               Country.name == name,
               func.nlevel(Country.path) != 1, func.nlevel(Country.path) < 3). \
        one_or_none()


def find_all_subdivisions_of_country(country_uuid, session=None, supported_country_code=None):
    country = session.query(Country).get(country_uuid)
    if not country:
        return None
    country_filter = [Country.path.descendant_of(country.path),
                      func.nlevel(Country.path) != 1]
    if supported_country_code:
        if country.code != supported_country_code:
            return None
        country_filter.append(Country.code == supported_country_code)
    return session.query(Country) \
        .filter(*country_filter) \
        .all()


def find_provincial_subdivisions(country_uuid, session):
    country = session.query(Country) \
        .filter(Country.country_uuid == country_uuid).one()

    return session.query(Country) \
        .filter(Country.path.descendant_of(country.path),
                func.nlevel(Country.path) == 2) \
        .all()


def get_legacy_specialty(profession_name, type_name, session=None):
    if not profession_name or not type_name:
        return None

    s = session.query(LegacySpecialty). \
        join(LegacySpecialtyProfession, LegacySpecialtyProfession.profession_uuid == LegacySpecialty.profession_uuid). \
        join(LegacySpecialtyType, LegacySpecialtyType.type_uuid == LegacySpecialty.type_uuid). \
        filter(LegacySpecialtyProfession.name == profession_name, LegacySpecialtyType.name == type_name). \
        one_or_none()
    if s:
        return s

    s2 = session.query(LegacySpecialty). \
        join(LegacySpecialtyProfession, LegacySpecialtyProfession.profession_uuid == LegacySpecialty.profession_uuid). \
        join(LegacySpecialtyType, LegacySpecialtyType.type_uuid == LegacySpecialty.type_uuid). \
        filter(LegacySpecialtyProfession.name == profession_name, LegacySpecialtyType.name == 'Custom'). \
        one_or_none()
    return s2


def find_all_legacy_specialties_joined(session):
    return session.query(LegacySpecialty,
                         LegacySpecialtyProfession.name.label('profession'),
                         LegacySpecialtyType.name.label('type')). \
        join(LegacySpecialtyProfession, LegacySpecialtyProfession.profession_uuid == LegacySpecialty.profession_uuid). \
        join(LegacySpecialtyType, LegacySpecialtyType.type_uuid == LegacySpecialty.type_uuid). \
        all()


@managed_session
def find_all_legacy_specialty_types(session=None):
    return session.query(LegacySpecialtyType).all()


def get_tagging_specialties(session):
    for s in session.query(SpecialtyV2).filter(SpecialtyV2.is_valid_case_tag.is_(True)).all():
        yield s.as_object()


def get_interests_specialties(session):
    for s in session.query(SpecialtyV2).filter(SpecialtyV2.is_valid_interest.is_(True)).all():
        yield s.as_dict()


def get_registration_professions(session):
    for p in session.query(ProfessionV2).all():
        yield p.as_object()


def get_registration_specialties(session, profession_uuid):
    for t in session.query(SpecialtyTreeV2).filter(SpecialtyTreeV2.profession_uuid == profession_uuid).all():
        t_object = t.as_object()
        if not t_object.onboardingDisplayName:
            continue
        yield t_object


def get_registration_subspecialties(session, specialty_uuid, profession_uuid):
    for ss in session.query(SpecialtyTreeV2).filter(SpecialtyTreeV2.specialty_v2_uuid == specialty_uuid,
                                                    SpecialtyTreeV2.profession_uuid == profession_uuid).all():
        ss_object = ss.as_object()
        if not ss_object.onboardingDisplayName:
            continue
        yield ss_object


@managed_session
def get_all_schools(session=None):
    return session.query(School).all()


def get_public_labels(session):
    return session.query(Label) \
        .filter(Label.is_public.is_(True)) \
        .all()


def get_all_verification_tags(session):
    return session \
        .query(VerificationTag) \
        .filter(VerificationTag.deleted_at.is_(None)) \
        .all()
