import uuid
from typing import Optional, Tuple, Any
from sqlalchemy import Column, String, Boolean, ARRAY, ForeignKey, Integer, or_, func
from sqlalchemy.orm import relationship, backref
from sqlalchemy.dialects.postgresql import UUID
from figure1.core import Base, HasCreateUpdateTime, HasCreateUpdateDeleteTime
from .user_models import User
from .c_case_model import Case


class MeshTerms(Base, HasCreateUpdateTime):
    """
    This is the original mesh terms table with some of the original columns removed. This table is intended to be a
    single entry to get the list of mesh terms for a given case as well as track the approver and any changes made.

    In practice, this table is a little redundant, however the original was so deeply embedded that I didn't want to
    take the risk of breaking something at the moment.

    The CaseMeshTerms is a many to many mapping of case_uuid to mesh terms, there is an entry for every term associated
    with a given case, so a case with 5 mesh terms would have 5 rows in the table. When a term is deleted, it is a soft
    delete, this helps to track which mesh terms tend to be deleted.

    """
    __tablename__ = "c_mesh_terms"
    case_uuid = Column(ForeignKey(Case.case_uuid), primary_key=True, index=True, unique=True)
    approved_terms = Column(ARRAY(String), default=[])
    approver_uid = Column(String)
    moderator_uuid = Column(ForeignKey(User.user_uuid), nullable=True)
    case = relationship("Case", backref=backref('mesh_terms', uselist=False), uselist=False)

    def as_dict(self):
        return {
            'caseUuid': str(self.case_uuid),
            'approvedTerms': self.approved_terms,
            'approverId': self.approver_uid
        }

    def elasticsearch_dict(self):
        return {
            'caseUuid': str(self.case_uuid),
            'approvedTerms': self.approved_terms
        }


class CaseMeshTerms(Base, HasCreateUpdateDeleteTime):
    """
    This table is a many-to-many mapping of case_uuids to term ids. For every term that is mapped to a case, there
    is one entry in this table. When a term is deleted from a case, it is not removed, the deleted date is simply
    filled in.

    """

    __tablename__ = 'c_case_mesh_terms'
    case_uuid = Column(UUID(as_uuid=True), primary_key=True)
    mesh_term_type = Column(String, nullable=True)
    mesh_term_id = Column(ForeignKey('p_public_mesh_terms.mesh_term_id'), primary_key=True)
    moderator_uuid = Column(ForeignKey(User.user_uuid), nullable=True)
    term = relationship("PublicMeshTerms",
                        primaryjoin="and_(CaseMeshTerms.mesh_term_id==PublicMeshTerms.mesh_term_id,"
                                    "PublicMeshTerms.is_active.is_(True))",
                        backref='case_mesh_terms')

    @staticmethod
    def _case_filter(case_uuid, mesh_term_type='PROBLEM') -> Tuple[bool, ...]:
        """
        Internal use, return a filter tuple to filter out deleted terms and filter for case_uuid
        """
        if mesh_term_type == 'ALL':
            return CaseMeshTerms.case_uuid == case_uuid, \
                   CaseMeshTerms.deleted_at.is_(None)

        return CaseMeshTerms.case_uuid == case_uuid, CaseMeshTerms.deleted_at.is_(None), or_(
            CaseMeshTerms.mesh_term_type == mesh_term_type, CaseMeshTerms.mesh_term_type.is_(None))

    @staticmethod
    def get_mesh_terms_for_case(case_uuid, session, mesh_term_type='PROBLEM'):
        """
        Returns an iterator of preferred terms for a given case. Inactive terms are skipped
        """
        mt = session.query(CaseMeshTerms) \
            .filter(*CaseMeshTerms._case_filter(case_uuid, mesh_term_type=mesh_term_type))
        for t in mt.all():
            if t.term:
                yield t.term.preferred_label

    @staticmethod
    def get_mesh_ids_for_case(case_uuid, session):
        """
        This does not skip inactive terms.
        """
        for term_id in session.query(CaseMeshTerms.mesh_term_id) \
                .filter(*CaseMeshTerms._case_filter(case_uuid, mesh_term_type='ALL')).all():
            yield term_id[0]

    @staticmethod
    def _delete_term(term_id, case_uuid, moderator_uuid, session):
        mesh_entry = session.query(CaseMeshTerms) \
            .filter(CaseMeshTerms.case_uuid == case_uuid, CaseMeshTerms.mesh_term_id == term_id) \
            .one_or_none()
        if mesh_entry:
            mesh_entry.mark_deleted()
            if moderator_uuid:
                mesh_entry.moderator_uuid = moderator_uuid
            session.add(mesh_entry)
        session.flush()

    @staticmethod
    def _add_term(term_id, case_uuid, moderator_uuid, session, mesh_term_type):
        case_mesh_terms_entry = CaseMeshTerms()
        case_mesh_terms_entry.case_uuid = case_uuid
        case_mesh_terms_entry.mesh_term_id = term_id
        case_mesh_terms_entry.moderator_uuid = moderator_uuid
        case_mesh_terms_entry.mesh_term_type = mesh_term_type
        return session.merge(case_mesh_terms_entry)

    @staticmethod
    def mark_terms_deleted(case_uuid, term_ids, moderator_uuid, session):
        if isinstance(term_ids, list):
            for t in term_ids:
                CaseMeshTerms._delete_term(t, case_uuid, moderator_uuid, session)
            session.flush()
        elif isinstance(term_ids, str):
            CaseMeshTerms._delete_term(term_ids, case_uuid, moderator_uuid, session)
        else:
            return None

    @staticmethod
    def add_new_terms(case_uuid, term_ids, moderator_uuid, session, mesh_term_type=None):
        if isinstance(term_ids, list):
            for t in term_ids:
                CaseMeshTerms._add_term(t, case_uuid, moderator_uuid, session, mesh_term_type)
        elif isinstance(term_ids, str):
            CaseMeshTerms._add_term(term_ids, case_uuid, moderator_uuid, session, mesh_term_type)
        session.flush()


class PublicMeshConceptTerms(Base):
    """
    This is joining table to join a concept to all of its associated terms.
    """
    __tablename__ = "p_public_mesh_concept_terms"
    mesh_concept_id = Column(ForeignKey('p_public_mesh_concepts.mesh_concept_id'), primary_key=True)
    mesh_term_id = Column(ForeignKey('p_public_mesh_terms.mesh_term_id'), primary_key=True)
    mesh_preferred_term_id = Column(ForeignKey('p_public_mesh_terms.mesh_term_id'))


class PublicMesh(Base):
    """
    Mesh definitions are the core of the mesh structure, they are what we would recognize as a mesh term, they are
    linked to a PublicMeshTerm which gives potential alternate terms and to a PublicMeshConcept which is a definition
    or description of the mesh term.

    The Identifier for mesh definition always starts with D
    """

    __tablename__ = 'p_public_mesh'
    mesh_id = Column(String, nullable=False, primary_key=True)
    preferredConcept = Column(ForeignKey('p_public_mesh_concepts.mesh_concept_id'))
    preferredTerm = Column(ForeignKey('p_public_mesh_terms.mesh_term_id'))


class PublicMeshConcepts(Base):
    """
    Mesh Concepts are essentially definitions, but describe the term in a broader sense, each can link to one
    preferred term and optionally additional related terms.

    The identifier for concepts always starts with an M
    """
    __tablename__ = 'p_public_mesh_concepts'
    mesh_concept_id = Column(String, nullable=False, primary_key=True)
    scope_note = Column(String, nullable=True)


class PublicMeshTerms(Base):
    """
    Terms are the official definitions of mesh terms found, this entry contains the preferred name and any alternate
    spellings or labels, for example Heart Arrest has and alternate term of Arrest, Heart.

    The is_active flag is meant for internal use, if it is marked False, then it will not show up in new case mesh
    terms

    The identifier for terms always starts with a T
    """
    __tablename__ = 'p_public_mesh_terms'
    mesh_term_id = Column(String, nullable=True, primary_key=True)
    preferred_label = Column(String, nullable=False)
    alternate_label = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)

    @staticmethod
    def find_mesh_terms(mesh_term, session) -> Optional['PublicMeshTerms']:
        """
        Searches for an entry in the terms table, returns the entry or None
        """
        return session.query(PublicMeshTerms) \
            .filter(or_(func.lower(PublicMeshTerms.preferred_label) == mesh_term.lower(),
                        func.lower(PublicMeshTerms.alternate_label) == mesh_term.lower())) \
            .one_or_none()
