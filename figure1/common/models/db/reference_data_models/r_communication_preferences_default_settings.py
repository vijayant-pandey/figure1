import uuid

from sqlalchemy import Column, String, Text, Integer, Boolean, ForeignKey, Enum, func
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, ENUM as pgEnum
from typing import Iterable, Optional

from figure1.core import Base, HasCreateUpdateDeleteTime
from figure1.common.types import CommunicationTypes, \
    CommunicationMethods, \
    SpecialtyCommunicationSettingsModel, \
    ActivityNotificationCategories


class CommunicationGroup(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "r_communication_groups"

    communication_group_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    communication_group_category = Column(pgEnum(ActivityNotificationCategories), nullable=True)
    communication_group_name = Column(Text)
    communication_group_type = Column(Enum(CommunicationTypes))
    communication_group_description = Column(Text)
    communication_group_display_order = Column(Integer, nullable=False)
    communication_group = relationship("CommunicationSettings",
                                       backref='communication_group')

    @staticmethod
    def get_differential_uuid(session):
        g = session.query(CommunicationGroup) \
            .filter(func.lower(func.replace(CommunicationGroup.communication_group_name, ' ', ''))
                    == 'yourdifferentials') \
            .one_or_none()
        return g.communication_group_uuid if g else None


class CommunicationChannel(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "r_communication_channel"

    communication_channel_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    communication_channel_name = Column(Text)
    communication_channel_id = Column(Integer)
    communication_default_setting = Column(Boolean, default=True)

    @staticmethod
    def get_channel_uuids(session):
        for c in session.query(CommunicationChannel.communication_channel_uuid).all():
            yield str(c[0])


class CommunicationSettings(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "r_communication_settings"

    communication_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    communication_method = Column(Enum(CommunicationMethods))
    communication_display_order = Column(Integer, nullable=False)
    communication_group_uuid = Column(UUID(as_uuid=True), ForeignKey(CommunicationGroup.communication_group_uuid))
    communication_channel_uuid = Column(UUID(as_uuid=True), ForeignKey(CommunicationChannel.communication_channel_uuid),
                                        nullable=True)
    communication_enabled = Column(Boolean, default=True)
    communication_default_setting = Column(Boolean, default=True)
    communication_name = Column(String, nullable=False)
    communication_description = Column(Text)
    communication_iterable_message_type = Column(Integer)
    legacy_id = Column(String)

    @staticmethod
    def get_settings_for_channel(session, communication_channel_uuid):
        for s in session.query(CommunicationSettings) \
                .filter(CommunicationSettings.communication_channel_uuid == communication_channel_uuid) \
                .all():
            yield s


class SpecialtyCommunicationSettings(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "r_specialty_communication_settings"
    communication_uuid = Column(UUID(as_uuid=True),
                                ForeignKey(CommunicationSettings.communication_uuid),
                                primary_key=True)
    tree_uuid = Column(UUID(as_uuid=True), nullable=False, primary_key=True)
    communication_default_setting = Column(Boolean, default=True)
    tree = relationship("SpecialtyTreeV2",
                        primaryjoin="remote(SpecialtyTreeV2.specialty_uuid)=="
                                    "foreign(SpecialtyCommunicationSettings.tree_uuid)")
    communication = relationship("CommunicationSettings", backref='specialty_defaults')

    @staticmethod
    def get_setting(tree_uuid, communication_uuid, session) -> Optional[SpecialtyCommunicationSettingsModel]:
        s = session.query(SpecialtyCommunicationSettings).get((communication_uuid, tree_uuid))
        return SpecialtyCommunicationSettingsModel.from_orm(s) if s else None
