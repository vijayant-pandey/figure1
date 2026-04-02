import uuid
from typing import Dict, Any

from pydantic import Field, BaseModel, validator
from sqlalchemy import Column, Integer, Enum
from sqlalchemy.dialects.postgresql import UUID

from figure1.core import Base, HasCreateUpdateDeleteTime
from figure1.common.types.email import StandaloneEmailKind


class StandaloneEmailModel(BaseModel):
    standaloneEmailUuid: str = Field(alias='standalone_email_uuid')
    iterableCampaignId: int = Field(alias='iterable_campaign_id')
    kind: str = Field(alias='kind')

    class Config:
        orm_mode = True

    @validator('standaloneEmailUuid', pre=True)
    def stringify_uuid(cls, value):
        return str(value)


class StandaloneEmail(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "n_standalone_email"

    standalone_email_uuid = Column(UUID(as_uuid=True), primary_key=True)
    iterable_campaign_id = Column(Integer)
    kind = Column(Enum(StandaloneEmailKind), nullable=False)

    def as_dict(self) -> Dict[str, Any]:
        return self.as_object().dict()

    def as_object(self) -> StandaloneEmailModel:
        return StandaloneEmailModel.from_orm(self)

    @staticmethod
    def create_or_update(kind, iterable_campaign_id, session):
        t = session.query(StandaloneEmail) \
            .filter(StandaloneEmail.kind == kind) \
            .one_or_none()
        if not t:
            t = StandaloneEmail()
            t.standalone_email_uuid = uuid.uuid4()

        t.deleted_at = None
        t.kind = kind
        t.iterable_campaign_id = iterable_campaign_id

        session.add(t)
