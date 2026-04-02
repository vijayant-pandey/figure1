from sqlalchemy import Column, Text
from sqlalchemy.dialects.postgresql import UUID

from figure1.core import Base, HasCreateUpdateDeleteTime


class RawSpecialtyMap(Base, HasCreateUpdateDeleteTime):
    """
    These tables should never be used except for importing data. They are temporary holding tables that essentially
    just store data straight out of the csv.

    The raw specialty map data takes an existing specialty and renames it and all of its references to a new specialty.

    """
    __tablename__ = "raw_specialty_map"

    pk = Column(UUID(as_uuid=True), primary_key=True)
    existing_specialty_name = Column(Text, nullable=True)
    existing_specialty_uuid = Column(UUID(as_uuid=True), nullable=True)
    new_specialty_name = Column(Text, nullable=True)
    new_specialty_uuid = Column(UUID(as_uuid=True), nullable=True)
