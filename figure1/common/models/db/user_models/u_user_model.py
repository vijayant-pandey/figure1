import logging
from typing import Optional
from pydantic.types import UUID as UUID_type
from sqlalchemy.ext.hybrid import hybrid_property

from figure1.common.types import UserTypes
from sqlalchemy_utils import aggregated, observes
from sqlalchemy import Column, Text, Boolean, ForeignKey, Integer, or_, DateTime, func, text
from sqlalchemy.orm import relationship, Session
from sqlalchemy.dialects.postgresql import UUID, ENUM

from figure1.common.types.specialties import StudentType
from figure1.common.types.user_state import OnboardingState
from figure1.exceptions import UserUIDNotFound, UserUUIDNotFound, UserUsernameNotFound, UserEmailNotFound
from figure1.core import HasCreateUpdateDeleteTime, HasCreateTime, Base
from figure1.common.models.db.reference_data_models import Country


class User(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "u_user"
    user_uuid = Column(UUID(as_uuid=True), primary_key=True)
    username = Column(Text, index=True, unique=True)
    user_type = Column(ENUM(UserTypes), default=UserTypes.USER)
    email = Column(Text, nullable=False, unique=True, index=True)
    user_uid = Column(Text, index=True, unique=True, nullable=True)
    first_name = Column(Text, nullable=True)
    last_name = Column(Text, nullable=True)
    legacy_account = Column(Boolean, nullable=True)
    user_profile = relationship('UserProfile', uselist=False)
    user_experience = relationship('UserExperience', uselist=True)
    user_affiliations = relationship('UserAffiliations', uselist=True)
    user_education = relationship('UserEducation', uselist=True)
    user_state = relationship('UserState', backref='user', uselist=False)
    # The columns below here have been moved, however some references remain
    last_seen = Column(DateTime(timezone=True), default=None, nullable=True, index=True)
    onboarding_completed = Column(Boolean, default=False, nullable=True)
    onboarding_interests_completed = Column(Boolean, default=False, nullable=True)
    hidden_from_search = Column(Boolean, default=False, nullable=True)
    sponsored_content_enabled = Column(Boolean, nullable=True)
    last_posted_comment = Column(DateTime, nullable=True)
    comment = relationship('Comment', backref='user')
    approved_comment_count = Column(Integer, default=0)
    deleted_comment_count = Column(Integer, default=0)
    reported_comment_count = Column(Integer, default=0)

    approved_case_count = Column(Integer, default=0)

    cases = relationship("Case",
                         backref='authors',
                         viewonly=True,
                         primaryjoin="(User.user_uuid==CaseAuthor.author_uuid)",
                         secondary='c_case_author')

    follower_count = relationship('UserFollow',
                                  viewonly=True,
                                  foreign_keys=user_uuid,
                                  uselist=True,
                                  primaryjoin='and_(UserFollow.user_uuid==User.user_uuid,'
                                              'UserFollow.deleted_at.is_(None))')

    following_count = relationship('UserFollow',
                                   viewonly=True,
                                   foreign_keys=user_uuid,
                                   primaryjoin='and_(UserFollow.follower_uuid==User.user_uuid,'
                                               'UserFollow.deleted_at.is_(None))')

    primary_specialty = relationship('UserSpecialtyTreeV2',
                                     viewonly=True,
                                     foreign_keys=user_uuid,
                                     primaryjoin='and_(UserSpecialtyTreeV2.user_uuid==User.user_uuid,'
                                                 'UserSpecialtyTreeV2.is_primary.is_(True))')

    @hybrid_property
    def user_groups(self):
        return self.group_member

    @hybrid_property
    def is_student(self):
        return self.primary_specialty.tree.profession.profession_category \
               in (each.value for each in StudentType)

    @aggregated('follower_count', Column(Integer, default=0))
    def user_follower_count(self):
        return func.count('1')

    @aggregated('following_count', Column(Integer, default=0))
    def user_following_count(self):
        return func.count('1')

    @observes('user_uuid')
    def on_new_user(self, user_uuid):
        if not self.user_state:
            u = UserState()
            u.user_uuid = user_uuid
            self.user_state = u

    def as_dict(self):
        if not self.user_type:
            obj = UserTypes.USER.value
        else:
            obj = self.user_type.value
        u = obj.from_orm(self).dict(exclude_none=True)
        return u

    @staticmethod
    def check_for_active_user_conflict(session, user_uid=None, user_uuid=None, email=None, username=None):
        conflict_filters = []
        if user_uuid:
            conflict_filters.append(User.user_uuid == user_uuid)
        if user_uid:
            conflict_filters.append(User.user_uid == user_uid)
        if email:
            conflict_filters.append(func.lower(User.email) == func.lower(email))
        if username:
            conflict_filters.append(func.lower(User.username) == func.lower(username))
        return session.query(User).filter(or_(*conflict_filters)).one_or_none()

    @staticmethod
    def check_for_user_conflict(session, user_uid=None, user_uuid=None, email=None, username=None):
        active_user = User.check_for_active_user_conflict(session=session,
                                                          user_uuid=user_uuid,
                                                          user_uid=user_uid,
                                                          email=email,
                                                          username=username)
        if active_user:
            return active_user

        return None

    @staticmethod
    def get_user_by_uuid(user_uuid, session, raise_exception=False, include_deleted=False) -> Optional['User']:
        if user_uuid is None:
            if raise_exception is True:
                raise ValueError("user_uuid is required and cannot be None")
            return None
        user_filter = []
        user_filter.append(User.user_uuid == user_uuid)
        if not include_deleted:
            user_filter.append(User.deleted_at.is_(None))
        user = session.query(User).filter(*user_filter).one_or_none()
        if not user:
            if raise_exception:
                raise UserUUIDNotFound(user_uuid=user_uuid)
            else:
                return None
        return user

    @staticmethod
    def get_user_by_uid(user_uid, session, raise_exception=False, include_deleted=False):
        if user_uid is None:
            if raise_exception is True:
                raise ValueError("user_uid is required and cannot be None")
            return None
        user_filter = []
        user_filter.append(User.user_uid == user_uid)
        if not include_deleted:
            user_filter.append(User.deleted_at.is_(None))
        user = session.query(User).filter(*user_filter).one_or_none()
        if not user:
            if raise_exception:
                raise UserUIDNotFound(user_uid=user_uid)
        return user

    @staticmethod
    def get_user_by_email(email, session, raise_exception=False, include_deleted=False):
        if email is None:
            if raise_exception is True:
                raise ValueError("email is required and cannot be None")
            return None

        user_filter = []
        user_filter.append(func.lower(User.email) == func.lower(email))
        if not include_deleted:
            user_filter.append(User.deleted_at.is_(None))
        user = session.query(User).filter(*user_filter).one_or_none()
        if not user:
            if raise_exception:
                raise UserEmailNotFound(email=email)
        return user

    @staticmethod
    def get_user_by_username(username, session, raise_exception=True, include_deleted=False):
        if username is None:
            if raise_exception is True:
                raise ValueError("username is required and cannot be None")
            return None
        user_filter = []
        user_filter.append(User.username == username)
        if not include_deleted:
            user_filter.append(User.deleted_at.is_(None))
        user = session.query(User).filter(*user_filter).one_or_none()
        if not user:
            if raise_exception:
                raise UserUsernameNotFound(username=username)
        return user

    @staticmethod
    def get_user_by_uid_as_dict(user_uid, session, raise_exception=False):
        try:
            user = User.get_user_by_uid(user_uid=user_uid, session=session, raise_exception=True)
            return user.as_dict()
        except UserUIDNotFound as e:
            if raise_exception:
                raise
            else:
                logging.error(str(e))
                return None

    @staticmethod
    def get_user_uuid_by_uid(user_uid,
                             session,
                             allow_anonymous=False,
                             raise_exception=False) -> Optional[UUID_type]:
        """
        Gets a user_uuid based on a user_uid.

        If allow_anonymous is True, this will attempt to find the uid in u_anonymous_user if it's not found in u_user.
        :param user_uid:
        :param session:
        :param allow_anonymous:
        :param raise_exception:
        :return:
        """
        try:
            user = User.get_user_by_uid(user_uid=user_uid, session=session, raise_exception=True)
            return user.user_uuid
        except UserUIDNotFound as e:
            if allow_anonymous:
                anon = session.query(AnonymousUser).get(user_uid)
                if anon:
                    return anon.user_uuid
            if raise_exception:
                raise
            else:
                logging.error(str(e))
                return None

    @staticmethod
    def get_users_by_type(user_type: UserTypes, session):
        for u in session.query(User).filter(User.user_type == user_type).all():
            yield u

    def is_user_in_usa(self, session: Session):
        usa = session.query(Country).filter(Country.alpha_3 == 'USA').one_or_none()
        if not usa:
            logging.error("Could not find reference data for USA country")
            return False
        return self.user_profile and str(self.user_profile.country_uuid) == str(usa.country_uuid)


class AnonymousUser(Base, HasCreateUpdateDeleteTime):
    """
    By definition, the users listed here are completely unknown to us - this tracks ungated content.
    """
    __tablename__ = "u_anonymous_user"
    email = Column(Text, index=True, nullable=True)
    user_uid = Column(Text, index=True, unique=True, nullable=False, primary_key=True)
    user_uuid = Column(UUID(as_uuid=True), server_default=text('gen_random_uuid()'))

    @staticmethod
    def get_anonymous_user_by_uid(user_uid, session, raise_exception=False, include_deleted=False):

        user_filter = []
        user_filter.append(AnonymousUser.user_uid == user_uid)
        if not include_deleted:
            user_filter.append(AnonymousUser.deleted_at.is_(None))
        anonymous_user = session.query(AnonymousUser).filter(*user_filter).one_or_none()
        if not anonymous_user:
            if raise_exception:
                raise UserUIDNotFound(user_uid=user_uid)
        return anonymous_user


class AnonymousEmailSubscriber(Base, HasCreateUpdateDeleteTime):
    """
    Models users who have subscribed to email communications but are not yet a normal member of figure 1
    """
    __tablename__ = "u_anonymous_email_subscriber"
    email = Column(Text, index=True, nullable=True, primary_key=True)
    user_uuid = Column(UUID(as_uuid=True), server_default=text('gen_random_uuid()'))


class UserState(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "u_user_state"
    user_uuid = Column(UUID(as_uuid=True), ForeignKey(User.user_uuid), primary_key=True)
    user_uid = Column(Text, index=True, unique=True, nullable=True)
    last_seen = Column(DateTime(timezone=True), default=func.now())
    onboarding_completed = Column(Boolean, default=False, nullable=True)
    onboarding_interests_completed = Column(Boolean, default=False, nullable=True)
    onboarding_state = Column(ENUM(OnboardingState), default=None, nullable=True)
    hidden_from_search = Column(Boolean, default=False, nullable=True)
    iterable_unsubscribed = Column(Boolean, default=False, nullable=True)
    unconfirmed_email = Column(Boolean, default=False, nullable=True)
    sponsored_content_enabled = Column(Boolean, default=True, nullable=True)
    activity_sync_complete = Column(Boolean, default=False, nullable=True)
    block_legacy_migration = Column(Boolean, default=False, nullable=True)
    requires_iterable_sync = Column(Boolean, default=False, nullable=True)
    last_iterable_sync = Column(DateTime(timezone=True))
    last_activity_sync = Column(DateTime(timezone=True))


class UserProfile(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "u_profile"
    user_uuid = Column(UUID(as_uuid=True), ForeignKey(User.user_uuid), primary_key=True)
    user_bio = Column(Text)
    graduation_date = Column(DateTime(timezone=True), default=None)
    country_uuid = Column(UUID(as_uuid=True), ForeignKey(Country.country_uuid))
    state_uuid = Column(UUID(as_uuid=True), ForeignKey(Country.country_uuid))
    practice_hospital = Column(Text)
    practice_location = Column(Text)
    display_name = Column(Text)
    avatar = Column(Text)
    background_image = Column(Text, nullable=True)
    disclosure_text = Column(Text)
    profile_link = Column(Text)
    profile_link_text = Column(Text)
    profile_display_name = Column(Text)
    case_comment_display_name = Column(Text)
    case_feed_enabled = Column(Boolean, default=False)
    case_feed_title = Column(Text)
    synced_at = Column(DateTime(timezone=True))

    def as_dict(self):
        return {
            'userUuid': str(self.user_uuid),
            'userBio': self.user_bio,
            'practiceHospital': self.practice_hospital,
            'practiceLocation': self.practice_location,
            'displayName': self.display_name,
            'avatar': self.avatar,
            'countryUuid': str(self.country_uuid) if self.country_uuid else None,
            'stateUuid': str(self.state_uuid) if self.state_uuid else None,
            'graduationDate': self.graduation_date.strftime('%Y-%m-%d') if self.graduation_date else None
        }


class UserExperienceBase(object):
    location = Column(Text)
    description = Column(Text)
    start_year = Column(Integer, index=True)
    end_year = Column(Integer, index=True)
    is_current = Column(Boolean, default=True)


class UserExperience(Base, UserExperienceBase, HasCreateUpdateDeleteTime):
    __tablename__ = "u_user_experience"
    user_uuid = Column(UUID(as_uuid=True), ForeignKey(User.user_uuid))
    experience_uuid = Column(UUID(as_uuid=True), primary_key=True)

    def as_dict(self):
        return {
            'location': self.location,
            'description': self.description,
            'startYear': self.start_year,
            'endYear': self.end_year,
            'userUuid': str(self.user_uuid),
            'experienceUuid': str(self.experience_uuid),
        }


class UserEducation(Base, UserExperienceBase, HasCreateUpdateDeleteTime):
    __tablename__ = "u_user_education"
    user_uuid = Column(UUID(as_uuid=True), ForeignKey(User.user_uuid))
    education_uuid = Column(UUID(as_uuid=True), primary_key=True)

    def as_dict(self):
        return {
            'location': self.location,
            'description': self.description,
            'startYear': self.start_year,
            'endYear': self.end_year,
            'userUuid': str(self.user_uuid),
            'educationUuid': str(self.education_uuid),
        }


class UserAffiliations(Base, UserExperienceBase, HasCreateUpdateDeleteTime):
    __tablename__ = "u_user_affiliation"
    user_uuid = Column(UUID(as_uuid=True), ForeignKey(User.user_uuid))
    affiliation_uuid = Column(UUID(as_uuid=True), primary_key=True)

    def as_dict(self):
        return {
            'location': self.location,
            'description': self.description,
            'startYear': self.start_year,
            'endYear': self.end_year,
            'userUuid': str(self.user_uuid),
            'affiliationUuid': str(self.affiliation_uuid),
        }


class UserVerificationComms(Base, HasCreateTime):
    __tablename__ = "u_user_comms_verification"
    user_uuid = Column(UUID(as_uuid=True), ForeignKey(User.user_uuid), primary_key=True)
    phone_number = Column(Text)
    is_sms = Column(Boolean, default=False)
    is_push = Column(Boolean, default=False)
    is_email = Column(Boolean, default=False)

    @staticmethod
    def create_or_update(user_uuid, is_sms, is_push, is_email, phone_number, session):
        user_verification_record = session.query(UserVerificationComms) \
            .filter(UserVerificationComms.user_uuid == user_uuid) \
            .one_or_none()

        if not user_verification_record:
            user_verification_record = UserVerificationComms()

        user_verification_record.user_uuid = user_uuid
        user_verification_record.is_sms = is_sms
        user_verification_record.is_push = is_push
        user_verification_record.is_email = is_email
        user_verification_record.phone_number = phone_number
        session.add(user_verification_record)

        try:
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        return user_verification_record
