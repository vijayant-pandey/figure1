from sqlalchemy import Column
from sqlalchemy import ForeignKey
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID

from figure1.common.models.db import ProfessionV2
from figure1.common.models.db import SpecialtyTreeV2
from figure1.core import Base
from figure1.core import HasCreateUpdateDeleteTime


class CmeCertificateTemplate(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "c_cme_certificate_template"

    case_uuid = Column(UUID(as_uuid=True), ForeignKey('c_case.case_uuid'), primary_key=True)
    profession_uuid = Column(UUID(as_uuid=True), primary_key=True)
    path = Column(String)
    filename = Column(String)

    @staticmethod
    def create_or_update(case_uuid, profession_uuid, path, filename, session, skip_commit=False):
        is_profession_uuid = None
        actual_profession_uuid = None
        is_tree_uuid = session.query(SpecialtyTreeV2) \
            .filter(SpecialtyTreeV2.specialty_uuid == profession_uuid) \
            .one_or_none()
        if is_tree_uuid:
            actual_profession_uuid = is_tree_uuid.profession.specialty_uuid
        else:
            is_profession_uuid = session.query(ProfessionV2).filter(ProfessionV2.specialty_uuid == profession_uuid)
            if not is_profession_uuid:
                return None
            else:
                actual_profession_uuid = profession_uuid

        c = session.query(CmeCertificateTemplate).get((case_uuid, actual_profession_uuid))
        if not c:
            c = CmeCertificateTemplate()
            c.case_uuid = case_uuid
            c.profession_uuid = actual_profession_uuid

        c.path = path
        c.filename = filename
        session.add(c)
        session.flush()
        return c

    def as_dict(self):
        return {
            'caseUuid': str(self.case_uuid),
            'professionUuid': str(self.profession_uuid),
            'path': self.path,
            'filename': self.filename
        }
