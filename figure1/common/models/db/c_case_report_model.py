from sqlalchemy import Column, ForeignKey, Text, Index
from sqlalchemy.dialects.postgresql import UUID

from figure1.core import Base, HasCreateUpdateDeleteTime, managed_session
from .c_case_model import Case
from .user_models import User


class CaseReport(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "c_case_report"
    case_uuid = Column(UUID(as_uuid=True), ForeignKey(Case.case_uuid), primary_key=True)
    user_uuid = Column(UUID(as_uuid=True), ForeignKey(User.user_uuid), primary_key=True)
    text = Column(Text, default="", nullable=False)
    __table_args__ = (Index('idx_c_case_report_case_uuid_user_uuid',
                            'case_uuid',
                            'user_uuid',
                            unique=True),)

    @staticmethod
    def create(case_uuid, user_uuid, text, skip_commit=False, session=None):
        cr = session.query(CaseReport) \
            .filter(CaseReport.case_uuid == case_uuid,
                    CaseReport.user_uuid == user_uuid) \
            .one_or_none()
        if cr:
            return cr

        cr = CaseReport()
        cr.case_uuid = case_uuid
        cr.user_uuid = user_uuid
        cr.text = text

        session.add(cr)

        return cr

    def as_dict(self):
        return {
            'caseUuid': str(self.case_uuid),
            'userUuid': self.user_uuid,
            'text': self.text,
        }
