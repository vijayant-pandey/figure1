import logging
from sqlalchemy import Column, ForeignKey, Index, Enum, func
from sqlalchemy.dialects.postgresql import UUID

from figure1.core import Base, HasCreateUpdateDeleteTime
from figure1.common.models.db import Case
from .user_models import User
from figure1.common.types.case import Reaction


class CaseReaction(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "c_case_reaction"
    case_uuid = Column(UUID(as_uuid=True), ForeignKey(Case.case_uuid), primary_key=True)
    user_uuid = Column(UUID(as_uuid=True), ForeignKey(User.user_uuid), primary_key=True)
    case_reaction = Column(Enum(Reaction), nullable=True, index=True)
    __table_args__ = (Index('idx_c_case_reaction_case_uuid_user_uuid',
                            'case_uuid',
                            'user_uuid',
                            unique=True),)

    @staticmethod
    def set_reaction(case_uuid, user_uuid, reaction: Reaction, session):
        case_reaction = CaseReaction()
        case_reaction.case_uuid = case_uuid
        case_reaction.user_uuid = user_uuid
        case_reaction.case_reaction = reaction.name
        return session.merge(case_reaction)

    @staticmethod
    def unset_reaction(case_uuid, user_uuid, session):
        session.query(CaseReaction) \
            .filter(CaseReaction.case_uuid == case_uuid, CaseReaction.user_uuid == user_uuid) \
            .delete()

    @staticmethod
    def get_reaction_counts(case_uuid, session):
        reaction_counts = {}
        for reaction in Reaction.__members__:
            c = session.query(func.count(CaseReaction.user_uuid)) \
                .filter(CaseReaction.case_reaction == reaction,
                        CaseReaction.case_uuid == case_uuid).scalar()
            reaction_counts.update({Reaction[reaction].value: c})
        return reaction_counts

    @staticmethod
    def get_case_reactions(case_uuid, session):
        """
        Returns a dict in the form of
        {
        'reactionEnumValue': [list of user_uuids who have reacted]
        }
        Each enum value has an entry, but may be an empty list
        :param case_uuid:
        :param session:
        :return:
        """
        reactions = {}
        for reaction in Reaction.__members__:
            reactions.update({Reaction[reaction].value: []})
        for r in session.query(CaseReaction).filter(CaseReaction.case_uuid == case_uuid).all():
            cr = r.case_reaction.value
            if cr in reactions:
                reactions[cr].append(str(r.user_uuid))
            else:
                reactions.update({cr: [str(r.user_uuid)]})
        return reactions

    def as_dict(self):
        return {
            'caseUuid': str(self.case_uuid),
            'userUuid': str(self.user_uuid),
            'updatedAt': self.updated_at,
            'caseReaction': self.case_reaction.name,
        }
