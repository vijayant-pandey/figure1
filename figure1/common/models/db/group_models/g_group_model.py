from typing import Optional
from sqlalchemy import Column, Boolean, String, Integer, ForeignKey, Enum, func
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID

from figure1.common.types.groups import GroupTypes
from figure1.core import Base, HasCreateUpdateDeleteTime
from figure1.exceptions.user import GroupUUIDNotFound, GroupFilterUUIDNotFound


class Groups(Base, HasCreateUpdateDeleteTime):
    """
    Central table to store groups, an entry must exist here for all groups.
    """
    __tablename__ = 'g_groups'
    group_uuid = Column(UUID(as_uuid=True), primary_key=True)
    group_name = Column(String, nullable=False, unique=True)
    group_label = Column(String, nullable=False)
    group_description = Column(String, nullable=True)
    group_active = Column(Boolean, default=False)
    group_avatar = Column(String, nullable=True)
    group_type = Column(Enum(GroupTypes), nullable=False)
    is_public = Column(Boolean, default=False)
    group_creator_uuid = Column(UUID(as_uuid=True), ForeignKey('u_user.user_uuid', ondelete='SET NULL'), nullable=True)
    creator = relationship('User', uselist=False, foreign_keys=group_creator_uuid)

    @staticmethod
    def get_all_groups(session):
        for group in session.query(Groups).all():
            yield group

    @staticmethod
    def get_group_by_uuid(group_uuid, session):
        return session.query(Groups).get(group_uuid)

    @staticmethod
    def get_members_by_group_uuid(group_uuid, session):
        group = session.query(Groups).filter(Groups.group_uuid == group_uuid).one_or_none()
        if not group:
            raise GroupUUIDNotFound(group_uuid=group_uuid, msg="Failed to find group.")

        for each in group.members:
            yield each

    @staticmethod
    def get_group_cases_by_group_uuid(group_uuid, session):
        group = session.query(Groups).filter(Groups.group_uuid == group_uuid).one_or_none()
        if not group:
            raise GroupUUIDNotFound(group_uuid=group_uuid, msg="Failed to find group.")

        for each in group.case:
            yield each


class GroupMember(Base, HasCreateUpdateDeleteTime):
    """
    Link a user_uuid to a group_uuid.
    """
    __tablename__ = 'g_group_members'
    user_uuid = Column(UUID(as_uuid=True), ForeignKey('u_user.user_uuid'), primary_key=True)
    group_uuid = Column(UUID(as_uuid=True), ForeignKey('g_groups.group_uuid'), primary_key=True)
    user = relationship('User', backref='group_member')
    group = relationship('Groups', backref='members')

    @hybrid_property
    def is_creator(self):
        return bool(self.group.group_creator_uuid and self.user_uuid == self.group.group_creator_uuid)

    @staticmethod
    def get_by_user_and_group(group_uuid, user_uuid, session) -> Optional['GroupMember']:
        return session.query(GroupMember) \
            .filter(GroupMember.group_uuid == group_uuid,
                    GroupMember.user_uuid == user_uuid,
                    GroupMember.deleted_at.is_(None)) \
            .one_or_none()


class GroupMemberFilter(Base, HasCreateUpdateDeleteTime):
    """
    Store a list of potential members to check when a new member signs up. This table is linked to the groups table,
    but nothing else. This is to allow for filtering on as many as fields as possible.
    The user_uuid field indicates that this user has been claimed.

    """
    __tablename__ = 'g_group_member_filter'
    group_filter_uuid = Column(UUID(as_uuid=True), primary_key=True)
    group = relationship("Groups", uselist=False, backref='group_member_filter')
    group_uuid = Column(UUID(as_uuid=True), ForeignKey('g_groups.group_uuid'))
    user_first_name = Column(String, nullable=True)
    user_last_name = Column(String, nullable=True)
    user_email = Column(String, nullable=True)
    user_npi = Column(Integer, nullable=True)
    user_uuid = Column(UUID(as_uuid=True), nullable=True)
    tree_uuid = Column(UUID(as_uuid=True), nullable=True)
    country_uuid = Column(UUID(as_uuid=True), nullable=True)
    inviter_uuid = Column(UUID(as_uuid=True), ForeignKey('u_user.user_uuid'), nullable=True)
    inviter = relationship('User', uselist=False, foreign_keys=inviter_uuid)

    @staticmethod
    def get_all_group_member_filters_by_email(session, email):
        return session.query(GroupMemberFilter) \
            .filter(func.lower(GroupMemberFilter.user_email) == func.lower(email)) \
            .all()

    @staticmethod
    def get_by_uuid(session, uuid):
        group_filter = session.query(GroupMemberFilter).get(uuid)
        if not group_filter:
            raise GroupFilterUUIDNotFound(group_filter_uuid=uuid, return_code=404)
        return group_filter

    @staticmethod
    def get_by_group_and_user_uuid(session, group_uuid, user_uuid):
        return session.query(GroupMemberFilter) \
            .filter(GroupMemberFilter.group_uuid == group_uuid, GroupMemberFilter.user_uuid == user_uuid) \
            .one_or_none()
