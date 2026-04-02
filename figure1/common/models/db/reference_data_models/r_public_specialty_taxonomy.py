from sqlalchemy import Column, Text, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from figure1.core import Base, HasCreateUpdateTime
from figure1.common.types import PublicTaxonomyModel


class PublicSpecialtyTaxonomy(Base, HasCreateUpdateTime):
    """
    This table should be considered readonly, it is just a database version of the csv file at
    https://www.nucc.org/index.php/code-sets-mainmenu-41/provider-taxonomy-mainmenu-40/csv-mainmenu-57
    The headers in the file are Code,Grouping,Classification,Specialization,Definition,Notes,Display Name,Section
    """
    __tablename__ = 'r_public_specialty_taxonomy'
    code = Column(Text, primary_key=True)
    grouping = Column(Text, nullable=True)
    classification = Column(Text, nullable=True)
    specialization = Column(Text, nullable=True)
    definition = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    display_name = Column(Text, nullable=True)
    section = Column(Text, nullable=True)

    def as_object(self):
        return PublicTaxonomyModel.from_orm(self)

    def as_dict(self):
        return self.as_object().dict()


class SpecialtyTaxonomyMap(Base, HasCreateUpdateTime):
    """
    This table maps taxonomy to our internal specialty tree structure. Each taxonomy should be linked to one tree uuid.
    """

    __tablename__ = 'r_specialty_taxonomy_map'
    taxonomy_code = Column(Text, ForeignKey('r_public_specialty_taxonomy.code'), primary_key=True)
    specialty_tree_uuid = Column(UUID(as_uuid=True), nullable=False)
