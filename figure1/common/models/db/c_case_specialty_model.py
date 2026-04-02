import logging
from typing import Dict, Any
from sqlalchemy import Column, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID

from pydantic import BaseModel, validator, Field
from figure1.core import Base, HasCreateUpdateDeleteTime
from .c_case_model import Case
from figure1.common.models.db import SpecialtyV2
from figure1.common.types import SpecialtyModel

logger = logging.getLogger('database.case_specialty')


class CaseSpecialtyV2Model(BaseModel):
    caseUuid: str = Field(alias='case_uuid')
    specialtyUuid: str = Field(alias='specialty_uuid')
    specialty: SpecialtyModel

    class Config:
        orm_mode = True

    @validator('specialtyUuid', 'caseUuid', pre=True)
    def stringify_uuid(cls, value):
        return str(value)


class CaseSpecialtyV2(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "c_case_specialty"
    case_uuid = Column(UUID(as_uuid=True), ForeignKey(Case.case_uuid), primary_key=True)
    specialty_uuid = Column(UUID(as_uuid=True), primary_key=True)
    specialty = relationship("SpecialtyV2",
                             primaryjoin="remote(SpecialtyV2.specialty_uuid)=="
                                         "foreign(CaseSpecialtyV2.specialty_uuid)")

    @staticmethod
    def create(case_uuid, specialty_uuid, session):
        cs = session.query(CaseSpecialtyV2).get([case_uuid, specialty_uuid])
        if cs:
            if cs.deleted_at is None:
                return cs
            cs.deleted_at = None
            session.add(cs)
            session.flush()
            return cs

        specialty: SpecialtyV2 = session.query(SpecialtyV2).get([specialty_uuid, 'specialty'])
        if not specialty:
            logger.error("Invalid specialty uuid %s", specialty_uuid)
            return None

        if not specialty.is_valid_case_tag:
            logger.error("Specialty %s is not valid for case tagging", specialty_uuid)
        else:
            cs = CaseSpecialtyV2()
            cs.case_uuid = case_uuid
            cs.specialty_uuid = specialty_uuid
            session.add(cs)
        session.flush()
        return cs

    def as_object(self):
        return CaseSpecialtyV2Model.from_orm(self)

    def as_dict(self) -> Dict[str, Any]:
        return self.as_object().dict()
