import logging
from pydantic import BaseModel, validator, Field
from typing import Optional, Iterable
from sqlalchemy import Column, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from figure1.core import Base, HasCreateUpdateDeleteTime
from figure1.common.models.db.reference_data_models.r_specialty_model import SpecialtyTreeV2
from .u_user_model import User
from figure1.common.types import UserSpecialtyTreeV2Model, UserProfessionV2Model, SpecialtyTreeModel
from figure1.exceptions import InvalidSpecialty, InvalidProfession

logger = logging.getLogger('database.user_specialty_tree')


class UserProfession(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "u_user_profession"
    user_uuid = Column(UUID(as_uuid=True), ForeignKey(User.user_uuid), primary_key=True)
    profession_uuid = Column(UUID(as_uuid=True))
    profession_tree_uuid = Column(UUID(as_uuid=True))
    profession = relationship("ProfessionV2",
                              primaryjoin="remote(ProfessionV2.specialty_uuid)=="
                                          "foreign(UserProfession.profession_uuid)")
    profession_tree = relationship("SpecialtyTreeV2",
                                   primaryjoin="remote(SpecialtyTreeV2.specialty_uuid)=="
                                               "foreign(UserProfession.profession_tree_uuid)")

    @staticmethod
    def create(user_uuid, profession_uuid, session):
        tree_model = None
        profession_uuid_filter = (SpecialtyTreeV2.profession_uuid == profession_uuid,
                                  SpecialtyTreeV2.specialty_v2_uuid.is_(None),
                                  SpecialtyTreeV2.subspecialty_uuid.is_(None))

        profession_tree_filter = (SpecialtyTreeV2.specialty_uuid == profession_uuid)

        profession_uuid_result = session.query(SpecialtyTreeV2).filter(*profession_uuid_filter).one_or_none()
        if profession_uuid_result:
            tree_model: SpecialtyTreeModel = profession_uuid_result.as_object()
            _profession_uuid = tree_model.profession.professionUuid
            _profession_tree_uuid = tree_model.treeUuid
        else:
            profession_tree_result = session.query(SpecialtyTreeV2).filter(profession_tree_filter).one_or_none()
            if profession_tree_result:
                tree_model: SpecialtyTreeModel = profession_tree_result.as_object()
                _profession_uuid = tree_model.profession.professionUuid
                _profession_tree_uuid = tree_model.treeUuid

        if not tree_model:
            logger.error("No matching tree or profession uuid found")
            raise InvalidProfession(msg="Unable to find matching profession_uuid or tree_uuid",
                                    profession_uuid=profession_uuid)

        user_prof = UserProfession()
        user_prof.profession_uuid = _profession_uuid
        user_prof.profession_tree_uuid = _profession_tree_uuid
        user_prof.user_uuid = user_uuid
        user_prof.deleted_at = None
        up = session.merge(user_prof)
        UserSpecialtyTreeV2.create_primary(user_uuid=user_uuid, tree_uuid=_profession_tree_uuid, session=session)
        session.flush()

        return up.as_dict()

    @staticmethod
    def get(user_uuid, session, profession_uuid=None, profession_tree_uuid=None) -> Optional[UserProfessionV2Model]:
        """
        Return the profession object for a user, if specialty is passed in, then that is returned if it exists for
        that user, if profession_uuid is not passed in, then the first match for that user is passed in.
        :param user_uuid:
        :param session:
        :param profession_uuid:
        :param profession_tree_uuid:
        :return: None or UserProfessionV2Model
        """

        up = session.query(UserProfession).filter(UserProfession.user_uuid == user_uuid).one_or_none()
        if up:
            return up.as_object()
        else:
            return None

    def as_object(self):
        return UserProfessionV2Model.from_orm(self)

    def as_dict(self):
        return self.as_object().dict()


class UserSpecialtyTreeV2(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "u_user_specialty_tree_v2"
    user_uuid = Column(UUID(as_uuid=True), ForeignKey(User.user_uuid), primary_key=True)
    tree_uuid = Column(UUID(as_uuid=True), nullable=False, primary_key=True)
    is_primary = Column(Boolean, default=False)
    tree = relationship("SpecialtyTreeV2",
                        primaryjoin="remote(SpecialtyTreeV2.specialty_uuid)=="
                                    "foreign(UserSpecialtyTreeV2.tree_uuid)")

    @staticmethod
    def create(user_uuid, tree_uuid, session) -> Optional[UserSpecialtyTreeV2Model]:
        """
        If a tree uuid exists in the table but isn't a valid one, then we should delete it.
        :param user_uuid:
        :param tree_uuid:
        :param session:
        :return:
        """
        tree: SpecialtyTreeV2 = session.query(SpecialtyTreeV2).get([tree_uuid, 'tree'])
        ex = session.query(UserSpecialtyTreeV2).get((user_uuid, tree_uuid))
        if ex:
            if not tree:
                session.query(UserSpecialtyTreeV2).filter(UserSpecialtyTreeV2.tree_uuid == tree_uuid).delete()
                session.commit()
                raise InvalidSpecialty(msg="Specialty tree uuid not found", specialty_uuid=str(tree_uuid))
            if not tree.specialty:
                session.query(UserSpecialtyTreeV2).filter(UserSpecialtyTreeV2.tree_uuid == tree_uuid).delete()
                session.commit()
                raise InvalidSpecialty(msg="Specialty tree-uuid must not be profession-only",
                                       specialty_uuid=str(tree_uuid))
        else:
            if not tree:
                raise InvalidSpecialty(msg="Specialty tree uuid not found", specialty_uuid=str(tree_uuid))

            if not tree.specialty:
                raise InvalidSpecialty(msg="Specialty tree-uuid must not be profession-only",
                                       specialty_uuid=str(tree_uuid))

        us = UserSpecialtyTreeV2()
        us.user_uuid = user_uuid
        us.tree_uuid = tree_uuid
        ust = session.merge(us)
        session.flush()
        return ust.as_object()

    @staticmethod
    def change_requires_verification(user_uuid, tree_uuid, session):
        """
        Returns True if the user requires re-verification, false if not. Only returns true if there is an existing tree
        and the profession_uuid does not match the requested one
        :param user_uuid:
        :param tree_uuid:
        :param session:
        :return:
        """
        user_specialties_q = session.query(UserSpecialtyTreeV2) \
            .filter(UserSpecialtyTreeV2.is_primary.is_(True),
                    UserSpecialtyTreeV2.user_uuid == user_uuid)
        if user_specialties_q.count() > 1:
            logger.error("User %s has too many primary specialties", user_uuid)
            raise ValueError("User has too many primary specialties")
        primary_entry = user_specialties_q.one_or_none()
        if primary_entry:
            requested_change: SpecialtyTreeV2 = session.query(SpecialtyTreeV2).get([tree_uuid, 'tree'])
            if requested_change.profession_uuid == primary_entry.tree.profession_uuid:
                logger.info("Changing specialty, no need for a change request")
                return False
            else:
                return True
        return False

    @staticmethod
    def create_primary(user_uuid, tree_uuid, session, check_verify=True) -> Optional[UserSpecialtyTreeV2Model]:
        """
        Each user can only have one primary tree_uuid, this function sets all of the is_primary values to false
        for a user except for the passed in tree_uuid.
        :param user_uuid:
        :param tree_uuid:
        :param session:
        :param check_verify: Check if a user requires verification to change or not. Defaults to True
        :return:
        """
        tree: SpecialtyTreeV2 = session.query(SpecialtyTreeV2).get([tree_uuid, 'tree'])
        if not tree:
            logger.error("Invalid tree uuid %s", tree_uuid)
            return None
        if check_verify is True:
            if UserSpecialtyTreeV2.change_requires_verification(user_uuid=user_uuid,
                                                                tree_uuid=tree_uuid,
                                                                session=session):
                return None

        session.query(UserSpecialtyTreeV2) \
            .filter(UserSpecialtyTreeV2.user_uuid == user_uuid, UserSpecialtyTreeV2.is_primary.is_(True)) \
            .delete()

        session.flush()

        ustv2 = UserSpecialtyTreeV2()
        ustv2.user_uuid = user_uuid
        ustv2.tree_uuid = tree_uuid
        ustv2.is_primary = True
        primary_specialty = session.merge(ustv2)
        session.flush()

        return primary_specialty.as_object()

    @staticmethod
    def get(user_uuid, session, specialty_uuid=None) -> Optional[Iterable[UserSpecialtyTreeV2Model]]:
        """
        Return a list of specialties for a user not including the primary specialty. If a specialty_uuid is passed in,
        only return that one.
        :param user_uuid:
        :param session:
        :param specialty_uuid:
        :return: None or UserSpecialtyTreeV2Model
        """
        if specialty_uuid:
            ust = session.query(UserSpecialtyTreeV2).get([user_uuid, specialty_uuid])
            if ust:
                yield ust.as_object()

        for ust in session.query(UserSpecialtyTreeV2) \
                .filter(UserSpecialtyTreeV2.user_uuid == user_uuid, UserSpecialtyTreeV2.is_primary.isnot(True)) \
                .all():
            yield ust.as_object()

    @staticmethod
    def get_primary(user_uuid, session) -> Optional[UserSpecialtyTreeV2Model]:
        """
        Return the users primary specialty
        :param user_uuid:
        :param session:
        :return:
        """
        primary_specialty = session.query(UserSpecialtyTreeV2) \
            .filter(UserSpecialtyTreeV2.user_uuid == user_uuid, UserSpecialtyTreeV2.is_primary.is_(True)) \
            .first()
        return primary_specialty.as_object() if primary_specialty else None

    def as_object(self) -> UserSpecialtyTreeV2Model:
        ust = UserSpecialtyTreeV2Model.from_orm(self)
        if hasattr(ust, 'tree') and ust.tree is not None:
            ust.profileDisplayName = ust.tree.profileDisplayName
            ust.caseCommentDisplayName = ust.tree.caseCommentDisplayName
            ust.onboardingDisplayName = ust.tree.onboardingDisplayName

        return ust

    def as_dict(self):
        return self.as_object().dict(exclude_none=True)
