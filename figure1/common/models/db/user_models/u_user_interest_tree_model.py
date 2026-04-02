import uuid
from typing import List, Set
from pydantic import ValidationError
from sqlalchemy import Column, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from figure1.core import Base, HasCreateUpdateDeleteTime
from figure1.common.models.db.reference_data_models.r_specialty_model import SpecialtyModel
from .u_user_model import User
from figure1.common.types import UserInterestV2Model


class UserInterest(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "u_user_interest"
    user_uuid = Column(UUID(as_uuid=True), ForeignKey(User.user_uuid), primary_key=True)
    interest_uuid = Column(UUID(as_uuid=True), primary_key=True)
    specialty = relationship("SpecialtyV2",
                             primaryjoin="remote(SpecialtyV2.specialty_uuid)=="
                                         "foreign(UserInterest.interest_uuid)")

    @staticmethod
    def _normalize_uuid(uuid_):
        if not isinstance(uuid_, uuid.UUID):
            try:
                return uuid.UUID(uuid_)
            except Exception:
                return None
        return uuid_

    @staticmethod
    def get_user_entry(user_uuid, session) -> List[UserInterestV2Model]:
        specialty_list = []
        for u in UserInterest._get_user_entry(user_uuid=user_uuid, session=session):
            try:
                specialty = SpecialtyModel.from_orm(u.specialty)
            except ValidationError:
                continue
            specialty_list.append(UserInterestV2Model.parse_obj(specialty.dict()))
        return specialty_list

    @staticmethod
    def _get_user_entry(user_uuid, session):
        return session.query(UserInterest).filter(UserInterest.user_uuid == user_uuid,
                                                  UserInterest.deleted_at.is_(None)).all()

    @staticmethod
    def add(user_uuid: str, specialty_uuid: Set, session):
        """
        The users interests are stored as a list of specialty_uuids, this method adds to the list, it does not
        remove exist entries. If there is no entry for the user, a new entry is created.
        :param user_uuid:
        :param specialty_uuid:
        :param session:
        :return:
        """
        specialty_set = set()
        if isinstance(specialty_uuid, list):
            for s in specialty_uuid:
                specialty_set.add(s)
        elif isinstance(specialty_uuid, set):
            specialty_set = specialty_uuid
        else:
            specialty_set.add(specialty_uuid)

        for s in specialty_set:
            ui = UserInterest()
            ui.user_uuid = user_uuid
            ui.interest_uuid = s
            ui.deleted_at = None
            session.merge(ui)

        session.flush()

    @staticmethod
    def remove(user_uuid, specialty_uuid: Set, session):
        specialty_set = set()
        if isinstance(specialty_uuid, list):
            for s in specialty_uuid:
                specialty_set.add(s)
        elif isinstance(specialty_uuid, set):
            specialty_set = specialty_uuid
        else:
            specialty_set.add(specialty_uuid)

        for each_uuid in specialty_set:
            each_interest = session.query(UserInterest)\
                                   .filter(UserInterest.user_uuid == user_uuid,
                                           UserInterest.interest_uuid == each_uuid)\
                                   .one_or_none()

            if each_interest:
                each_interest.mark_deleted()
                session.add(each_interest)

        session.flush()

    @staticmethod
    def replace(user_uuid: str, specialty_uuid: Set, session):
        """
        When passed one or more specialty_uuids, the user's entry is replaced with this list. There is no attempt made
        to preserve existing entries. If there is no entry a new one is created.
        :param user_uuid:
        :param specialty_uuid:
        :param session:
        :return:
        """

        user = UserInterest._get_user_entry(user_uuid=user_uuid, session=session)
        if user:
            for u in user:
                u.mark_deleted()
                session.add(u)
        session.flush()

        return UserInterest.add(user_uuid=user_uuid, specialty_uuid=specialty_uuid, session=session)

    @staticmethod
    def create(user_uuid: str, specialty_uuid: Set, session):
        """
        Given a list of specialty uuids, a new entry is created in this table for the user. If the user already has
        an entry, nothing is changed.

        :param user_uuid:
        :param specialty_uuid:
        :param session:
        :return:
        """
        UserInterest.replace(user_uuid=user_uuid, specialty_uuid=specialty_uuid, session=session)

    def as_object(self):
        return UserInterestV2Model.from_orm(self)

    def as_dict(self):
        return self.as_object().dict()
