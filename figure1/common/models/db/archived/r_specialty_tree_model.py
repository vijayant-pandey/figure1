import uuid

from sqlalchemy import Column, String, Index, func, ForeignKey, Integer, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, remote, foreign
from sqlalchemy_utils import LtreeType, Ltree

from .r_specialty_model_v1 import Specialty
from figure1.core import Base, managed_session, HasCreateUpdateDeleteTime


class SpecialtyTree(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "r_specialty_tree"

    tree_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    specialty_uuid = Column(UUID(as_uuid=True), ForeignKey(Specialty.specialty_uuid), nullable=False)
    name = Column(String(1024), default="", nullable=False, index=True)
    label = Column(String(1024), default="", nullable=False)
    path = Column(LtreeType, nullable=False)
    display_order = Column(Integer)
    registration_hidden = Column(Boolean)
    parent = relationship(
        'SpecialtyTree',
        primaryjoin=remote(path) == foreign(func.subpath(path, 0, -1)),
        backref='children',
        viewonly=True,
        sync_backref=False,
    )
    __table_args__ = (
        Index('ix_specialties_path', path, postgresql_using="gist"),
    )

    @staticmethod
    def create_or_update(specialty_uuid,
                         tree_uuid,
                         name,
                         label,
                         path_str,
                         session,
                         registration_hidden,
                         display_order=None,
                         skip_commit=False):
        path = Ltree(path_str)

        existing_item = session.query(SpecialtyTree) \
            .filter(SpecialtyTree.tree_uuid == tree_uuid) \
            .one_or_none()
        if existing_item:
            if existing_item.name != name:
                existing_item.name = name
            if existing_item.display_order != display_order:
                existing_item.display_order = display_order
            if existing_item.registration_hidden != registration_hidden:
                existing_item.registration_hidden = registration_hidden
            return existing_item

        s = SpecialtyTree()
        s.tree_uuid = tree_uuid
        s.specialty_uuid = specialty_uuid
        s.name = name
        s.label = label
        s.path = path
        s.display_order = display_order
        s.registration_hidden = registration_hidden

        session.add(s)

        if skip_commit:
            return s

        try:
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        return s

    def as_dict(self):
        return {
            'treeUuid': str(self.tree_uuid),
            'specialtyUuid': str(self.specialty_uuid),
            'name': self.name,
            'label': self.label,
            'path': str(self.path),
            'displayOrder': self.display_order,
            'depth': len(self.path) - 1,
        }
