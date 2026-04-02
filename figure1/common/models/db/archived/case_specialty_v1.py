import logging
from sqlalchemy import Column, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from figure1.core import Base, HasCreateUpdateDeleteTime
from ..c_case_model import Case
from .r_specialty_model_v1 import Specialty


class CaseSpecialty(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "c_case_specialty_v1"
    case_uuid = Column(UUID(as_uuid=True), ForeignKey(Case.case_uuid), primary_key=True)
    specialty_uuid = Column(UUID(as_uuid=True), ForeignKey(Specialty.specialty_uuid), primary_key=True)
    specialty_v2_uuid = Column(UUID(as_uuid=True))

    @staticmethod
    def create(case_uuid, specialty_uuid, skip_commit=False, session=None):
        cs = session.query(CaseSpecialty) \
            .filter(CaseSpecialty.case_uuid == case_uuid,
                    CaseSpecialty.specialty_uuid == specialty_uuid) \
            .one_or_none()
        if cs:
            cs.deleted_at = None
            return cs

        s = session.query(Specialty) \
            .filter(Specialty.specialty_uuid == specialty_uuid) \
            .one_or_none()
        if not s:
            logging.warning(f'Could not add invalid specialty {specialty_uuid} to case {case_uuid}')
            return cs

        cs = CaseSpecialty()
        cs.case_uuid = case_uuid
        cs.specialty_uuid = specialty_uuid
        session.add(cs)

        if skip_commit:
            return cs

        try:
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        return cs

    def as_dict(self):
        return {
            'caseUuid': str(self.case_uuid),
            'specialtyUuid': str(self.specialty_uuid),
        }
