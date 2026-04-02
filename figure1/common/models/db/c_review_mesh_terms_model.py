import uuid

from sqlalchemy import Column, String, Boolean, ARRAY, Index, Integer
from sqlalchemy.dialects.postgresql import UUID

from figure1.core import Base, HasCreateUpdateDeleteTime


class ReviewMeshTerms(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "c_review_mesh_terms"
    mesh_review_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    case_uuid = Column(UUID)
    reviewed_terms = Column(ARRAY(String), nullable=False)
    reviewer_uid = Column(String)
    flagged = Column(Boolean, default=False)
    rating = Column(Integer, nullable=True)
    specialty_uuids = Column(ARRAY(UUID(as_uuid=True)))
    __table_args__ = (Index('idx_reviewer_terms', 'reviewer_uid', 'case_uuid', unique=True),)

    def as_dict(self):
        return {
            u'meshReviewUuid': str(self.mesh_review_uuid),
            u'uuid': str(self.mesh_review_uuid),
            u'caseUuid': str(self.case_uuid),
            u'reviewerId': str(self.reviewer_uid),
            u'terms': self.reviewed_terms,
            u'flagged': self.flagged,
            u'rating': self.rating,
            u'specialtyUuids':
                list(map(lambda s: str(s), self.specialty_uuids)) if self.specialty_uuids else []
        }
