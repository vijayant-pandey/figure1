import enum
import uuid

from sqlalchemy import Column, String, Integer, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Session

from figure1.core import Base, HasCreateTime


class Publications(Base):
    __tablename__ = "p_public_publications"

    pub_med_id = Column(String, primary_key=True)
    title = Column(String, nullable=True)


class CasePublications(Base, HasCreateTime):
    __tablename__ = "c_case_publications"

    case_uuid = Column(UUID(as_uuid=True), primary_key=True)
    pub_med_id = Column(ForeignKey('p_public_publications.pub_med_id'), primary_key=True)
    display_order = Column(Integer)

    publication = relationship("Publications")

    @staticmethod
    def create(case_uuid: UUID, display_order: int, pub_med_id: str, session: Session) -> dict:
        """
        Returns the updated entry as a dictionary

        :param case_uuid: Case uuid as either a string or uuid
        :type case_uuid: uuid

        :param display_order: The order in which to show the publication for a case
        :type display_order: int

        :param pub_med_id: The pubmed id
        :type pub_med_id: str

        :param session: The database session to use
        :type session: Session

        :return:
        """
        entry = Publications()
        entry.case_uuid = case_uuid
        entry.display_order = display_order
        entry.pub_med_id = pub_med_id
        updated_entry = session.merge(entry)
        return updated_entry.as_dict()

    def as_dict(self):
        return dict(url=f'https://www.ncbi.nlm.nih.gov/pubmed/{self.pub_med_id}',
                    caseUuid=str(self.case_uuid),
                    displayOrder=self.display_order,
                    pubMedId=self.pub_med_id,
                    title=self.publication.title)
