from pydantic import BaseModel
from enum import Enum

from sqlalchemy import Column, Text, ForeignKey, DateTime, String, func
from sqlalchemy.orm import validates
from sqlalchemy.dialects.postgresql import UUID

from figure1.core import Base, HasCreateUpdateDeleteTime
from figure1.common.models.db import User


class InvalidAggregationException(Exception):
    pass


class AggregateEventTypes(BaseModel):
    name: str
    default_schedule: str


class AggregateEvents(Enum):
    """
    SUMMARY_BY_CASE_AUTHOR contains
    """
    SUMMARY_BY_CASE_AUTHOR = AggregateEventTypes(name='summaryByCaseAuthor',
                                                 default_schedule='0 12 * * FRI')


class UserScheduledAggregations(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "u_user_scheduled_aggregations"

    user_uuid = Column(UUID(as_uuid=True),
                       ForeignKey(User.user_uuid),
                       primary_key=True)

    event_name = Column(Text, nullable=False, primary_key=True)
    event_schedule = Column(String, nullable=False)
    last_run_date = Column(DateTime(timezone=True))

    @validates('event_name')
    def check_valid_event_name(self, key, value):
        if isinstance(value, AggregateEvents):
            return value.name.upper()
        if value.upper() not in AggregateEvents.__members__.keys():
            raise InvalidAggregationException
        return value.upper()
