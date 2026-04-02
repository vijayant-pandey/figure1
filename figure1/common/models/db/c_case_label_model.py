import logging

from sqlalchemy import Column, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

from figure1.core import Base, HasCreateUpdateDeleteTime, managed_session
from .c_case_model import Case
from .reference_data_models import Label


class CaseLabel(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "c_case_label"
    case_uuid = Column(UUID(as_uuid=True), ForeignKey(Case.case_uuid), primary_key=True)
    label_uuid = Column(UUID(as_uuid=True), ForeignKey(Label.label_uuid), primary_key=True)

    @staticmethod
    @managed_session
    def create(case_uuid, label_uuid, skip_commit=False, session=None):
        label = session.query(Label).get(label_uuid)
        cl = session.query(CaseLabel).get({'case_uuid': case_uuid, 'label_uuid': label_uuid})
        if cl:
            cl.deleted_at = None
            return cl

        if not label:
            logging.warning(f'Could not add invalid label {label_uuid} to case {case_uuid}')
            return label

        cl = CaseLabel()
        cl.case_uuid = case_uuid
        cl.label_uuid = label_uuid
        session.add(cl)

        if skip_commit:
            return cl
        try:
            session.commit()
        except Exception:
            session.rollback()
            raise
        return cl

    @staticmethod
    def delete(case_uuid, label_uuid, session, skip_commit=False):
        cl = session.query(CaseLabel).get({'case_uuid': case_uuid, 'label_uuid': label_uuid})
        if not cl:
            return None

        cl.mark_deleted()

        if skip_commit:
            return cl
        try:
            session.commit()
        except Exception:
            session.rollback()
            raise
        return cl

    def as_dict(self):
        return {
            'caseUuid': str(self.case_uuid),
            'labelUuid': str(self.label_uuid),
        }
