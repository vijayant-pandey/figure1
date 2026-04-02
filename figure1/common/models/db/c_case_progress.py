from datetime import datetime, timezone
from pydantic import Field, BaseModel, validator
from sqlalchemy import Column, ForeignKey, Integer, DateTime
from sqlalchemy.dialects.postgresql import UUID
from typing import Dict, Any, Optional

from figure1.core import Base, HasCreateUpdateTime
from .c_case_model import Case


class CaseProgressModel(BaseModel):
    userUuid: str = Field(alias='user_uuid')
    caseUuid: str = Field(alias='case_uuid')
    contentPosition: int = Field(alias='content_position')
    completedAt: Optional[datetime] = Field(alias='completed_at')

    class Config:
        orm_mode = True
        extra = 'ignore'
        validate_assignment = True

    @validator('userUuid', 'caseUuid', pre=True)
    def stringify_uuid(cls, value):
        return str(value)


class CaseProgress(Base, HasCreateUpdateTime):
    __tablename__ = "c_case_progress"

    case_uuid = Column(UUID(as_uuid=True), ForeignKey(Case.case_uuid), primary_key=True)
    user_uuid = Column(UUID(as_uuid=True), primary_key=True)
    content_position = Column(Integer)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    def as_dict(self) -> Dict[str, Any]:
        return self.as_object().dict()

    def as_object(self) -> CaseProgressModel:
        return CaseProgressModel.from_orm(self)

    @staticmethod
    def create_or_update(user_uuid,
                         case_uuid,
                         session,
                         is_complete=None,
                         content_position=None,
                         skip_commit=False):
        cp = session.query(CaseProgress).get((case_uuid, user_uuid))
        if not cp:
            cp = CaseProgress()

        cp.user_uuid = user_uuid
        cp.case_uuid = case_uuid
        if is_complete is not None:
            cp.completed_at = datetime.now(timezone.utc) if is_complete else None
        if content_position:
            cp.content_position = content_position

        session.add(cp)

        if skip_commit:
            return cp

        try:
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        return cp
