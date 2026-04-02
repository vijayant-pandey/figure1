import uuid
import re

from sqlalchemy import Column, String, Text, Boolean, Integer
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declared_attr
from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any
from figure1.core import Base, HasCreateUpdateDeleteTime
from figure1.common.types import ProfessionModel, SpecialtyModel, SpecialtyTreeModel


class SpecialtyBaseV2(Base, HasCreateUpdateDeleteTime):
    """
    This is the root class for the specialty table. Each row in this table is made unique by the combination of
    specialty_type and specialty_uuid. This means that there can be multiples of the same specialty_uuid
    as long as the specialty_type is different. The result of this structure is that tree_uuids are not separate from
    specialty_uuids in the table, however because you query through a class instance, you would only get tree results
    for example that have the specialty_type of tree.

    This class should never be directly written too, any data that is can only have the base_specialty_uuid and
    specialty_type.

    """
    __tablename__ = 'r_specialty_v2'
    specialty_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    specialty_type = Column(Text, primary_key=True)
    __mapper_args__ = {
        'polymorphic_on': specialty_type
    }


class ProfessionV2(SpecialtyBaseV2):
    """
    A profession is the most general level of categorization, in general, each entry encompasses a range of specialties.
    In general, it is the profession which is associated with a specific school, though this isn't universally the case.

    To create a profession entry, instantiate this class with a specialty_uuid. It will be given a specialty_type of
    profession. This is all that is required, however, it is quite likely that some further description will prove
    helpful, the in addition to the standard name/label columns, profession also has a profession_category column
    associated with it. This column is used to handle things like otherHCP is more properly a category of professions
    rather than a profession on its own.

    Extracting data is best done by calling as_object, however compatibility with functions expecting dicts can be had
    by calling as_dict().

    """
    profession_category = Column(Text, nullable=True, index=True)

    @declared_attr
    def name(cls):
        return SpecialtyBaseV2.__table__.c.get("name", Column(Text))

    @declared_attr
    def label(cls):
        return SpecialtyBaseV2.__table__.c.get("label", Column(Text))

    __mapper_args__ = {
        'polymorphic_identity': 'profession'
    }

    def as_dict(self) -> Dict[str, Any]:
        return self.as_object().dict()

    def as_object(self) -> ProfessionModel:
        return ProfessionModel.from_orm(self)


class SpecialtyV2(SpecialtyBaseV2):
    """
    Specialties are the middle ground of categorization, they are typically considered as part of a given profession.

    """

    @declared_attr
    def name(cls):
        return SpecialtyBaseV2.__table__.c.get("name", Column(Text))

    @declared_attr
    def label(cls):
        return SpecialtyBaseV2.__table__.c.get("label", Column(Text))

    @declared_attr
    def is_valid_case_tag(cls):
        return SpecialtyBaseV2.__table__.c.get("is_valid_case_tag", Column(Boolean))

    @declared_attr
    def is_valid_interest(cls):
        return SpecialtyBaseV2.__table__.c.get("is_valid_interest", Column(Boolean))

    __mapper_args__ = {
        'polymorphic_identity': 'specialty'
    }

    def as_dict(self) -> Dict[str, Any]:
        return self.as_object().dict()

    def as_object(self) -> SpecialtyModel:
        return SpecialtyModel.from_orm(self)


class SpecialtyTreeV2(SpecialtyBaseV2):
    """
    A specialty tree entry is created by linking a profession and optionally, a specialty and subspecialty. A tree
    entry is used to generate a profession/specialty/subspecialty hierarchy.
    When an instance is returned, it is recommended to use the as_object() method which will unpack the relationships,
    while not including the unpopulated keys.

    In order for the relationships to work, the uuids for profession, specialty, and subspecialty must already exist
    in the table with the correct discriminator types ( profession, specialty, subspecialty ). These uuids are not
    checked directly, however the tree object will not be correctly populated as it is populated with a self-join.

    """
    profession = relationship("ProfessionV2",
                              viewonly=True,
                              sync_backref=False,
                              primaryjoin="remote(ProfessionV2.specialty_uuid)=="
                                          "foreign(SpecialtyTreeV2.profession_uuid)")
    specialty = relationship("SpecialtyV2",
                             viewonly=True,
                             sync_backref=False,
                             primaryjoin="remote(SpecialtyV2.specialty_uuid)=="
                                         "foreign(SpecialtyTreeV2.specialty_v2_uuid)")
    subspecialty = relationship("SpecialtyV2",
                                viewonly=True,
                                sync_backref=False,
                                primaryjoin="remote(SpecialtyV2.specialty_uuid)=="
                                            "foreign(SpecialtyTreeV2.subspecialty_uuid)")

    profession_uuid = Column(UUID(as_uuid=True), nullable=True)
    specialty_v2_uuid = Column(UUID(as_uuid=True), nullable=True)
    subspecialty_uuid = Column(UUID(as_uuid=True), nullable=True)

    display_order = Column(Integer, nullable=True)
    onboarding_display_label = Column(Text, nullable=True)
    profile_display_label = Column(Text, nullable=True)
    case_comment_display_label = Column(Text, nullable=True)

    __mapper_args__ = {
        'polymorphic_identity': 'tree'
    }

    def as_dict(self) -> Dict[str, Any]:
        """
        Returns the SpecialtyTreeModel serialized to a dictionary.
        :return:
        """
        return self.as_object().dict()

    def as_object(self) -> SpecialtyTreeModel:
        """
        Get the object with resolved joins if available. This is recommended as it resolves all of the joins into
        a model which can then be manipulated.
        :return:
        """
        return SpecialtyTreeModel.from_orm(self)
