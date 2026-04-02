import uuid

from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

from figure1.core import Base, managed_session, HasCreateUpdateDeleteTime
from .c_legacy_case_model import LegacyCase


class TaggingAssignment(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "c_tagging_assignment"

    assignment_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    case_uuid = Column(UUID(as_uuid=True), ForeignKey(LegacyCase.case_uuid))
    reviewer_uid = Column(String)

    @staticmethod
    @managed_session
    def create(case_uuid, reviewer_uid, session=None):
        a = TaggingAssignment()
        a.assignment_uuid = uuid.uuid4()
        a.case_uuid = case_uuid
        a.reviewer_uid = reviewer_uid
        session.add(a)
        return a

    def as_dict(self):
        return {
            u'assignmentUuid': str(self.assignment_uuid),
            u'uuid': str(self.assignment_uuid),
            u'caseUuid': str(self.case_uuid),
            u'reviewerId': str(self.reviewer_uid),
        }
