import logging
import uuid

from sqlalchemy.orm import Session
from figure1.exceptions import UserNotFound
from figure1.exceptions import DuplicateUser
from figure1.common.types import UserAffiliationsDocument
from figure1.common.types import UserExperienceDocument
from figure1.common.types import UserEducationDocument
from figure1.common.types import UserVerificationDocument
from figure1.common.types import VerificationStatus
from figure1.common.types import UserTypes
from figure1.common.types import UpdateUserModel
from figure1.common.types import UserProfessionV2Model
from figure1.common.types import UserSpecialtyTreeV2Model
from figure1.common.types import UserAuthorModel
from figure1.common.types import UserStateDatabaseModel
from figure1.common.types import UserProfileDatabaseModel
from figure1.common.types import UserDatabaseModel
from figure1.common.types import OnboardingState
from figure1.common.types import UserVerificationPhotos

from datetime import datetime
from datetime import timezone
from typing import Optional
from typing import Iterable
from typing import List
from typing import Tuple
from figure1.common.models.db.m_user_verification_tag import UserVerificationTag
from figure1.common.models.db.m_verification_note import VerificationNote
from figure1.common.models.db.reference_data_models import Country
from figure1.common.models.db.reference_data_models import SpecialtyTreeV2
from figure1.common.models.db.user_models import UserInterest
from figure1.common.models.db.user_models import UserFeedSubscription
from figure1.common.models.db.user_models import UserFollow
from figure1.common.models.db.user_models import User
from figure1.common.models.db.user_models import UserExperience
from figure1.common.models.db.user_models import UserEducation
from figure1.common.models.db.user_models import UserAffiliations
from figure1.common.models.db.user_models import UserProfile
from figure1.common.models.db.user_models import UserState
from figure1.common.models.db.user_models import UserSpecialtyTreeV2
from figure1.common.models.db.user_models import UserProfession
from figure1.common.models.db.user_models import UserCustomData
from figure1.exceptions.user import InvalidOnboardingState
from figure1.common.types.elasticsearch import ESUserDocument
from figure1.store import UserDataCache
from figure1.store import UserSponsoredContentStore
from figure1.store import UserUidMap
from figure1.core import managed_session
from .verification import get_user_verification_record
from .verification import create_profession_change_request
from .verification import is_user_verified
from ..models.db import Case
from ..models.db import CaseAuthor
from ..models.db import Comment

logger = logging.getLogger(__name__)


@managed_session
def _get_user_uuid(user_uid, session):
    return User.get_user_uuid_by_uid(raise_exception=True, session=session, user_uid=user_uid)


def user_uuid_from_uid(user_uid) -> Optional[str]:
    """
    Attempts get the uuid from the cache, if it isn't there, then query for it.
    :param user_uid:
    :return: stringified user_uuid or None
    :raises: UserNotFound, UserError
    """
    uid_map = UserUidMap(user_uid)
    user_uuid = uid_map.get_uuid()
    if not user_uuid:
        user_uuid = _get_user_uuid(user_uid)
        user_uuid = uid_map.set_uuid(user_uuid)
    if user_uuid:
        return user_uuid
    return None


class UserDocument:

    @staticmethod
    def _get_user_by_uid(user_uid, session):
        return User.get_user_by_uid(user_uid=user_uid, session=session, raise_exception=True, include_deleted=True)

    @staticmethod
    def _get_user_by_uuid(user_uuid, session):
        return User.get_user_by_uuid(user_uuid=user_uuid, session=session, raise_exception=True, include_deleted=True)

    @staticmethod
    def _get_user_specialties(user_uuid, session=None) -> Iterable[UserSpecialtyTreeV2Model]:
        return UserSpecialtyTreeV2.get(user_uuid=user_uuid, session=session)

    @staticmethod
    def _get_primary_user_specialty(user_uuid, session) -> UserSpecialtyTreeV2:
        return UserSpecialtyTreeV2.get_primary(user_uuid=user_uuid, session=session)

    @staticmethod
    def _get_user_profession(user_uuid, session=None) -> Optional[UserProfessionV2Model]:
        return UserProfession.get(user_uuid=user_uuid, session=session)

    @staticmethod
    def _get_user_custom_fields(user_uuid, session):
        return UserCustomData.get(user_uuid=user_uuid, session=session)

    @staticmethod
    def _get_user_interests(user_uuid, session=None):
        ui = UserInterest.get_user_entry(user_uuid=user_uuid, session=session)
        return ui if ui else None

    @staticmethod
    def _get_user_country_data(country_uuid, session=None):
        c = session.query(Country).filter(Country.country_uuid == country_uuid).one_or_none()
        return c.as_object() if c else None

    @staticmethod
    def _get_user_verification(user_uuid=None, session=None) -> Tuple[UserVerificationDocument, List]:
        """
        :param user_uuid:
        :param session:
        :return:
        """
        archived = []
        verification = UserVerificationDocument(verificationStatus=VerificationStatus.UNKNOWN)

        def get_verification_record(v):
            verification_doc = UserVerificationDocument.from_orm(v)
            verification_photos = UserVerificationPhotos.from_orm(v)
            verification_doc.verificationPhoto = verification_photos.verificationPhoto

            if verification_doc.license:
                if verification_doc.license.licenseCountryUuid:
                    verification_doc.license.licenseCountry = Country.get_name_for_uuid(
                        verification_doc.license.licenseCountryUuid)
                if verification_doc.license.licenseStateUuid:
                    verification_doc.license.licenseState = Country.get_name_for_uuid(
                        verification_doc.license.licenseStateUuid)

            if verification_doc.npi:
                if verification_doc.npi.npiCountryUuid:
                    verification_doc.npi.npiCountry = Country.get_name_for_uuid(verification_doc.npi.npiCountryUuid)
                if verification_doc.npi.npiStateUuid:
                    verification_doc.npi.npiState = Country.get_name_for_uuid(verification_doc.npi.npiStateUuid)
            logger.debug("Returning verification object %s", verification_doc.dict())
            return verification_doc

        res = get_user_verification_record(user_uuid=user_uuid,
                                           verification_status='all',
                                           session=session)

        if isinstance(res, list):
            for record in res:
                if record.verification_status == VerificationStatus.ARCHIVED:
                    archived.append(get_verification_record(record))
                else:
                    verification = get_verification_record(record)
            return verification, archived
        return UserVerificationDocument(verificationStatus=VerificationStatus.UNKNOWN), []

    @staticmethod
    def _get_user_subscribed_topics(user_uuid, session=None):
        return list(UserFeedSubscription.get_subscribed_feeds(user_uuid=user_uuid, session=session))

    @staticmethod
    def _get_admin_verification_notes(user_uuid, session):
        notes = []
        for c in session.query(VerificationNote) \
                .filter(VerificationNote.user_uuid == user_uuid) \
                .order_by(VerificationNote.created_at) \
                .all():
            notes.append(c.as_firestore_dict(session=session))
        return notes

    @staticmethod
    def _get_admin_verification_tags(user_uuid, session):
        tags = []
        for c in session.query(UserVerificationTag) \
                .filter(UserVerificationTag.user_uuid == user_uuid,
                        UserVerificationTag.deleted_at.is_(None)) \
                .order_by(UserVerificationTag.created_at) \
                .all():
            tags.append(c.as_firestore_dict())
        return tags

    @staticmethod
    def get_deleted_user(user_uuid, session):
        return session.query(User).get(user_uuid)

    @staticmethod
    def user_detail(user_uid=None, user_uuid=None, session=None):

        if user_uid:
            u = UserDocument._get_user_by_uid(user_uid=user_uid, session=session)
        elif user_uuid:
            u = UserDocument._get_user_by_uuid(user_uuid=user_uuid, session=session)
        else:
            raise UserNotFound(msg='No user id passed', return_code=404)
        if u.user_type:
            user_type = u.user_type.value
        else:
            user_type = UserTypes.USER.value

        profile_overrides = user_type.from_orm(u.user_profile)

        user_base = UserDatabaseModel.from_orm(u)
        logger.debug("User base %s", user_base.dict())
        user_profile = UserProfileDatabaseModel.from_orm(u.user_profile)
        logger.debug("User profile %s", user_profile.dict())
        user_state = UserStateDatabaseModel.from_orm(u.user_state)
        logger.debug("User State %s", user_state.dict())
        user = user_type.parse_obj({**user_state.dict(),
                                    **user_profile.dict(),
                                    **user_base.dict(),
                                    **profile_overrides.dict(include={'userType',
                                                                      'canEdit',
                                                                      'isPartner',
                                                                      'caseFeedEnabled',
                                                                      'disclosureText',
                                                                      'backgroundImage',
                                                                      'caseCommentDisplayName',
                                                                      'profileDisplayName'})})
        user_uuid = user.userUuid
        logger.debug("Full user object is %s", user.dict())
        if user.countryUuid is not None:
            user.country = UserDocument._get_user_country_data(country_uuid=user_profile.countryUuid,
                                                               session=session)

        user_specialties = UserDocument._get_user_specialties(user_uuid=user_uuid, session=session)
        primary_user_specialty = UserDocument._get_primary_user_specialty(user_uuid=user_uuid, session=session)

        if primary_user_specialty:
            user.primarySpecialty = primary_user_specialty
            if not user.caseCommentDisplayName:
                user.caseCommentDisplayName = primary_user_specialty.caseCommentDisplayName
            if not user.profileDisplayName:
                user.profileDisplayName = primary_user_specialty.profileDisplayName

            if hasattr(primary_user_specialty, 'onboardingDisplayName'):
                user.onboardingDisplayName = primary_user_specialty.onboardingDisplayName

            if primary_user_specialty.tree.profession:
                user.professionName = primary_user_specialty.tree.profession.professionName
                user.professionUuid = primary_user_specialty.tree.profession.professionUuid
            if primary_user_specialty.tree.specialty:
                user.specialtyName = primary_user_specialty.tree.specialty.specialtyName
            if primary_user_specialty.tree.subspecialty:
                user.subspecialtyName = primary_user_specialty.tree.subspecialty.specialtyName
        else:
            user_profession = UserDocument._get_user_profession(user_uuid=user_uuid, session=session)
            if user_profession:
                if user_profession.profession:
                    user.professionName = user_profession.profession.professionName
                    user.professionUuid = user_profession.profession.professionUuid
                elif user_profession.professionTree:
                    user.professionName = user_profession.professionTree.profession.professionName
                    user.professionUuid = user_profession.professionTree.profession.professionUuid

        if user_specialties:
            user.secondarySpecialties = [x.dict() for x in user_specialties]

        user_interests = UserDocument._get_user_interests(user_uuid=user_uuid, session=session)
        user.isVerified = is_user_verified(user_uuid=user_uuid, session=session)
        verification, archivedVerification = UserDocument._get_user_verification(user_uuid=user_uuid, session=session)
        user.archivedVerification = archivedVerification
        user.verification = verification

        if verification.professionChangeRequest:
            profession_tree_uuid = verification.professionChangeRequest.professionTreeUuid
            if verification.professionChangeRequest.requestResolved is True:
                user.professionChangeRequest = {}
            else:
                tree = session.query(SpecialtyTreeV2) \
                    .filter(SpecialtyTreeV2.specialty_uuid == profession_tree_uuid,
                            SpecialtyTreeV2.specialty_type == 'tree') \
                    .one_or_none()
                if tree is not None:
                    user.professionChangeRequest = tree.as_object()
                else:
                    logger.error("Unable to find tree entry for %s", profession_tree_uuid)
        user.interests = user_interests

        user.activityCount = 0
        approved_comment_count = Comment.get_comment_count(user_uuid=user.userUuid, include_anonymous=False)\
            .get('approved_comment_count', 0)
        user.approvedCommentCount = approved_comment_count
        user.activityCount += user.approvedCommentCount

        if user.approvedCaseCount:
            user.activityCount += user.approvedCaseCount
        if not user.displayName:
            user.displayName = user.username

        return user.dict()

    @staticmethod
    def get_compact_user_data(user_uid=None, user_uuid=None, session=None, use_cache=True, is_anonymous=False):
        """
        If a user_uuid is passed in, it is cached(use_cache=True) if it hasn't already been.
        These cache keys expire in 1 hour.
        If is_anonymous is passed in as True, do not cache.
        :param user_uid:
        :param user_uuid:
        :param session:
        :param use_cache:
        :return:
        """
        cache = None
        if use_cache and user_uuid:
            cache = UserDataCache(user_uuid=user_uuid)
            cached_user = cache.get_compact_user_data()
            if cached_user:
                logger.debug("Returning cached user for user %s", user_uuid)
                if is_anonymous:
                    return UserAuthorModel.parse_obj({**cached_user, "is_anonymous": is_anonymous}).dict()
                return cached_user
        user_detail = UserDocument.user_detail(user_uid=user_uid, user_uuid=user_uuid, session=session)
        author_model = UserAuthorModel.parse_obj({**user_detail, "is_anonymous": is_anonymous}).dict()
        author_model.update({'treeUuid': user_detail.get("primarySpecialty", {}).get("treeUuid"),
                             'tree': user_detail.get("primarySpecialty", {}).get("tree")})
        if is_anonymous is True:
            return author_model

        if not cache:
            cache = UserDataCache(user_uuid=user_uuid)
        cache.write_compact_user_data(data=author_model)
        return author_model

    @staticmethod
    def get_user_target_data(user_uid, session):
        """
        This is used to get a user's targetting data, this happens inline with feed generation, so it needs to be
        as fast as possible.

        :param user_uid:
        :param session:
        :return:
        """
        user_uuid = user_uuid_from_uid(user_uid)
        if user_uuid:
            user_target_data = UserSponsoredContentStore(user_uuid=user_uuid)
        else:
            raise UserNotFound
        tg = user_target_data.get_user_target()
        if tg:
            return tg

        tree_set = set()
        for ss in UserDocument._get_user_specialties(user_uuid=user_uuid, session=session):
            if ss.tree.treeUuid:
                tree_set.add(ss.tree.treeUuid)

        primary_user_specialty = UserDocument._get_primary_user_specialty(user_uuid=user_uuid, session=session)
        if primary_user_specialty:
            if primary_user_specialty.tree.treeUuid:
                tree_set.add(primary_user_specialty.tree.treeUuid)

        user_target_data.set_user_target(targetTree=list(tree_set))
        profile = session.query(UserProfile.country_uuid) \
            .filter(UserProfile.user_uuid == user_uuid) \
            .one_or_none()
        if profile:
            country_uuid = profile[0]
            if country_uuid:
                user_target_data.set_user_target(targetCountry=str(country_uuid))

        user_target_data.set_user_target(targetIsVerified=is_user_verified(user_uuid=user_uuid, session=session))

        return user_target_data.get_user_target()

    @staticmethod
    def get_public_profile(user_uuid, session):
        """
        This returns the public profile as the top level with the unfiltered profile object under the 'profile'
        key. This should be exported with public_profile_exclude_keys in order to filter out what should not
        be published into firestore.
        :param user_uuid:
        :param session:
        :return: UserPublicProfileDocument
        """

        return UserDocument.user_detail(user_uuid=user_uuid, session=session)

    @staticmethod
    def get_full_profile(user_uuid, session):
        """
        Return the full profile of a user, the public profile is under the 'public' key.
        :param user_uuid:
        :param session:
        :return: UserProfileDocument
        """
        return UserDocument.user_detail(user_uuid=user_uuid, session=session)

    @staticmethod
    def elasticsearch_user_detail(user_uid=None, user_uuid=None, session=None) -> ESUserDocument:
        u = UserDocument.user_detail(user_uid=user_uid, user_uuid=user_uuid, session=session)
        verification = u.get('verification', {})
        u.update({**verification})

        es_doc = ESUserDocument(**u)

        if verification.get('verificationFlaggedForReview', False):
            verification.update({'verificationStatus': VerificationStatus.REVIEW_REQUIRED.value})
            es_doc.verificationStatus = VerificationStatus.REVIEW_REQUIRED.value

        user_custom_data = UserDocument._get_user_custom_fields(user_uuid=user_uuid, session=session)
        if user_custom_data:
            if user_custom_data.custom_school:
                es_doc.userCustomSchool = user_custom_data.custom_school
            if user_custom_data.custom_specialty:
                es_doc.userCustomSpecialty = user_custom_data.custom_specialty

        es_doc.madeForYouSpecialties = UserDocument.get_made_for_you_specialties(user_uuid=user_uuid, session=session)
        es_doc.verificationNotes = UserDocument._get_admin_verification_notes(user_uuid=user_uuid, session=session)
        es_doc.verificationTags = UserDocument._get_admin_verification_tags(user_uuid=user_uuid, session=session)

        return es_doc

    @staticmethod
    @managed_session
    def get_made_for_you_specialties(user_uuid, session):
        """
        user specialties at this point is a fallback that will rarely work if there are no interests. This is because
        when specialties are added, they are also added to the interests list.

        :param user_uuid:
        :param session:
        :return:
        """
        mfy_specialties = set()
        us = UserDocument._get_user_specialties(user_uuid=user_uuid, session=session)
        user_interests = UserDocument._get_user_interests(user_uuid=user_uuid, session=session)
        if user_interests:
            for i in user_interests:
                mfy_specialties.add(i.interestUuid)
        if us:
            for user_specialties in us:
                if user_specialties.tree.specialty:
                    mfy_specialties.add(user_specialties.tree.specialty.specialtyUuid)
                if user_specialties.tree.subspecialty:
                    mfy_specialties.add(user_specialties.tree.subspecialty.specialtyUuid)
        return list(mfy_specialties)


class UserManagement:

    def __init__(self,
                 session,
                 user_uid=None,
                 user_uuid=None,
                 email=None,
                 username=None,
                 is_new_user=False,
                 is_admin_created=False,
                 include_deleted=False):
        self.user = None

        try:
            if email:
                self.user = User.get_user_by_email(email=email,
                                                   session=session,
                                                   include_deleted=include_deleted)
            elif user_uid:
                self.user = User.get_user_by_uid(user_uid=user_uid,
                                                 session=session,
                                                 raise_exception=True,
                                                 include_deleted=include_deleted)
            elif user_uuid:
                self.user = User.get_user_by_uuid(user_uuid=user_uuid,
                                                  session=session,
                                                  raise_exception=True,
                                                  include_deleted=include_deleted)
            elif username:
                self.user = User.get_user_by_username(username=username,
                                                      session=session,
                                                      raise_exception=True,
                                                      include_deleted=include_deleted)
            else:
                raise UserNotFound(msg="No user uid or uuid passed")
        except UserNotFound as e:
            if is_admin_created:
                pass
            elif is_new_user:
                self.user_uid = user_uid
            else:
                raise UserNotFound(msg="Cannot find existing user and should not create new user")
        self.session = session

    def _unpack_exp(self, data: list):
        for exp in data:
            yield exp.dict(exclude_none=True)

    def add_admin_user(self, email, username, user_type: UserTypes):
        if self.user:
            raise DuplicateUser(msg="Duplicate user", return_code=409)

        u = User()
        u.email = email
        u.user_type = user_type
        u.username = username
        u.user_uuid = uuid.uuid4()

        u.user_profile = UserProfile()

        self.user = self.session.merge(u)
        self.session.flush()

    def add_user(self, first_name, last_name, email, user_uuid=None, legacy=False,
                 user_type: UserTypes = UserTypes.USER):
        if self.user and legacy is not True:
            return {
                'error': f'User already exists',
                'code': 409
            }

        u = User()
        u.user_uid = self.user_uid
        u.first_name = first_name
        u.last_name = last_name
        u.email = email
        u.legacy_account = legacy
        u.user_type = user_type
        if not user_uuid:
            u.user_uuid = uuid.uuid4()
        else:
            u.user_uuid = user_uuid

        u.user_profile = UserProfile()
        u.user_profile.user_uuid = u.user_uuid
        u.user_profile.display_name = f"{first_name} {last_name}"

        self.user = self.session.merge(u)
        self.session.commit()
        return {
            'success': 'User created'
        }

    def add_legacy_user(self,
                        email,
                        user_uuid,
                        created_at,
                        user_type: UserTypes = UserTypes.USER):
        u = User()
        u.user_uid = None
        u.email = email
        u.legacy_account = True
        u.user_type = user_type
        u.user_uuid = user_uuid
        u.created_at = created_at,

        self.session.add(u)
        self.session.flush()
        self.user = u
        return {
            'success': 'User created'
        }

    def add_user_profile(self, first_name, last_name, display_name=None):
        profile = UserProfile()
        if display_name:
            profile.display_name = display_name
        elif first_name and last_name:
            profile.display_name = f"{first_name} {last_name}"
        profile.user_uuid = self.user.user_uuid
        self.session.add(profile)
        self.session.flush()
        return profile

    def add_user_experience(self, data: list):
        for exp in self._unpack_exp(data=data):
            if exp.get('experienceUuid'):
                continue
            current_experience = UserExperience()
            current_experience.experience_uuid = uuid.uuid4()
            current_experience.user_uuid = self.user.user_uuid
            add = self.set_user_experience(experience=current_experience, expdata=exp)
            self.session.add(add)
        self.session.flush()

    def add_user_education(self, data: list):
        for exp in self._unpack_exp(data=data):
            if exp.get('educationUuid'):
                continue
            education = UserEducation()
            education.education_uuid = uuid.uuid4()
            education.user_uuid = self.user.user_uuid
            add = self.set_user_education(education=education, edudata=exp)
            self.session.add(add)
        self.session.flush()

    def add_user_affiliations(self, data: list):
        for exp in self._unpack_exp(data=data):
            if exp.get('affiliationUuid'):
                continue
            affiliation = UserAffiliations()
            affiliation.affiliation_uuid = uuid.uuid4()
            affiliation.user_uuid = self.user.user_uuid
            add = self.set_user_affilation(affiliation=affiliation, afdata=exp)
            self.session.add(add)
        self.session.flush()

    def update_user_experience(self, data: list):
        for exp in self._unpack_exp(data=data):
            if not exp.get('experienceUuid'):
                continue
            current_experience = self.session.query(UserExperience) \
                .filter(UserExperience.experience_uuid == exp['experienceUuid']) \
                .one_or_none()
            if not current_experience:
                logging.error(f"Unable to find experience id {exp['experienceUuid']}")
                continue
            update = self.set_user_experience(experience=current_experience, expdata=exp)
            self.session.add(update)
        self.session.commit()

    def update_user_education(self, data: list):
        for exp in self._unpack_exp(data=data):
            if not exp.get('educationUuid'):
                continue
            education = self.session.query(UserEducation) \
                .filter(UserEducation.education_uuid == exp['educationUuid']) \
                .one_or_none()
            if not education:
                logging.error(f"Unable to find education id {exp['educationUuid']}")
                continue
            update = self.set_user_education(education=education, edudata=exp)
            self.session.add(update)
        self.session.commit()

    def update_user_affiliation(self, data: list):
        for exp in self._unpack_exp(data=data):
            if not exp.get('affiliationUuid'):
                continue
            affiliation = self.session.query(UserAffiliations) \
                .filter(UserAffiliations.affiliation_uuid == exp['affiliationUuid']) \
                .one_or_none()
            if not affiliation:
                logging.error(f"Unable to find affiliation id {exp['affiliationUuid']}")
                continue
            update = self.set_user_affilation(affiliation=affiliation, afdata=exp)
            self.session.add(update)
        self.session.commit()

    def set_custom_data(self, data: UpdateUserModel):
        """
        Update user custom data table, takes an update user model
        :param data:
        :return:
        """
        UserCustomData.create(user_uuid=self.user.user_uuid,
                              custom_school=data.custom_school,
                              custom_specialty=data.custom_specialty,
                              session=self.session)
        self.session.flush()

    def set_user_experience(self, experience: UserExperience, expdata: dict) -> UserExperience:
        experience.start_year = expdata.get('startYear')
        experience.location = expdata.get('location')
        experience.description = expdata.get('description')
        if expdata.get('endYear'):
            experience.end_year = expdata['endYear']
            experience.is_current = False
        else:
            experience.is_current = True
        return experience

    def set_user_education(self, education: UserEducation, edudata: dict) -> UserEducation:
        education.start_year = edudata.get('startYear')
        education.location = edudata.get('location')
        education.description = edudata.get('description')
        if edudata.get('endYear'):
            education.end_year = edudata.get('endYear')
            education.is_current = False
        else:
            education.is_current = True
        return education

    def set_user_affilation(self, affiliation: UserAffiliations, afdata: dict) -> UserAffiliations:
        affiliation.start_year = afdata.get('startYear')
        affiliation.location = afdata.get('location')
        affiliation.description = afdata.get('description')
        if afdata.get('endYear'):
            affiliation.end_year = afdata.get('endYear')
            affiliation.is_current = False
        else:
            affiliation.is_current = True
        return affiliation

    def set_last_seen(self):
        self.user.last_seen = datetime.now(tz=timezone.utc)
        self.session.add(self.user)

    def set_interests(self, interests: list):
        """
        This replaces any interests that already exist with the interests passed in.
        :param interests:
        :return:
        """
        UserInterest.replace(user_uuid=self.user.user_uuid, specialty_uuid=interests, session=self.session)

    def remove_non_primary_specialties(self):
        non_primary_specialties = self.session.query(UserSpecialtyTreeV2) \
            .filter(UserSpecialtyTreeV2.user_uuid == self.user.user_uuid,
                    UserSpecialtyTreeV2.is_primary.is_(False))

        user_interests_to_remove = []
        for each in non_primary_specialties.all():
            each = each.as_object()
            if each.tree.specialty:
                if each.tree.specialty.isValidInterest:
                    user_interests_to_remove.append(each.tree.specialty.specialtyUuid)

            if each.tree.subspecialty:
                if each.tree.subspecialty.isValidInterest:
                    user_interests_to_remove.append(each.tree.subspecialty.specialtyUuid)

        UserInterest.remove(user_uuid=self.user.user_uuid,
                            specialty_uuid=user_interests_to_remove,
                            session=self.session)
        non_primary_specialties.delete()
        self.session.flush()

    def set_specialties(self, specialties: list):
        self.remove_non_primary_specialties()

        for tree_uuid in specialties:
            st = UserSpecialtyTreeV2.create(user_uuid=self.user.user_uuid,
                                            tree_uuid=tree_uuid,
                                            session=self.session)
            if st.tree.specialty:
                if st.tree.specialty.isValidInterest:
                    UserInterest.add(user_uuid=self.user.user_uuid,
                                     specialty_uuid=[st.tree.specialty.specialtyUuid],
                                     session=self.session)
            if st.tree.subspecialty:
                if st.tree.subspecialty.isValidInterest:
                    UserInterest.add(user_uuid=self.user.user_uuid,
                                     specialty_uuid=[st.tree.subspecialty.specialtyUuid],
                                     session=self.session)
        self.session.flush()

    def set_primary_specialty(self, specialty, check_verify=True):
        if check_verify:
            if UserSpecialtyTreeV2.change_requires_verification(user_uuid=self.user.user_uuid,
                                                                tree_uuid=specialty,
                                                                session=self.session):
                existing_primary_specialty_tree = UserSpecialtyTreeV2.get_primary(user_uuid=self.user.user_uuid,
                                                                                  session=self.session)
                create_profession_change_request(user_uuid=self.user.user_uuid,
                                                 current_profession_uuid=existing_primary_specialty_tree.treeUuid,
                                                 requested_profession_uuid=specialty,
                                                 session=self.session)

        ps = UserSpecialtyTreeV2.create_primary(user_uuid=self.user.user_uuid,
                                                tree_uuid=specialty,
                                                session=self.session,
                                                check_verify=check_verify)
        if ps is None:
            return

        if ps.tree.specialty:
            if ps.tree.specialty.isValidInterest:
                UserInterest.add(user_uuid=self.user.user_uuid,
                                 specialty_uuid=[ps.tree.specialty.specialtyUuid],
                                 session=self.session)
        if ps.tree.subspecialty:
            if ps.tree.subspecialty.isValidInterest:
                UserInterest.add(user_uuid=self.user.user_uuid,
                                 specialty_uuid=[ps.tree.subspecialty.specialtyUuid],
                                 session=self.session)
        self.session.flush()

    def replace_specialty(self, specialty_uuid):
        self.session.query(UserSpecialtyTreeV2) \
            .filter(UserSpecialtyTreeV2.user_uuid == self.user.user_uuid,
                    UserSpecialtyTreeV2.is_primary.isnot(True)) \
            .delete()
        self.session.flush()
        UserSpecialtyTreeV2.create(user_uuid=self.user.user_uuid,
                                   tree_uuid=specialty_uuid,
                                   session=self.session)

    def get_user_experience(self):
        exp = self.session.query(UserExperience).filter(UserExperience.user_uuid == self.user.user_uuid).all()
        for e in exp:
            yield UserExperienceDocument.from_orm(e)

    def get_user_education(self):
        exp = self.session.query(UserEducation).filter(UserEducation.user_uuid == self.user.user_uuid).all()
        for e in exp:
            yield UserEducationDocument.from_orm(e)

    def get_user_affiliations(self):
        exp = self.session.query(UserAffiliations).filter(UserAffiliations.user_uuid == self.user.user_uuid).all()
        for e in exp:
            yield UserAffiliationsDocument.from_orm(e)

    def delete_user_affiliations(self, affiliationUuids=None):
        if affiliationUuids and isinstance(affiliationUuids, list):
            for ex in affiliationUuids:
                self.session.query(UserAffiliations).filter(UserAffiliations.affiliation_uuid == ex).delete()
        elif affiliationUuids and isinstance(affiliationUuids, str):
            self.session.query(UserEducation).filter(UserAffiliations.affiliation_uuid == affiliationUuids).delete()
        elif not affiliationUuids:
            self.session.query(UserAffiliations).filter(UserAffiliations.user_uuid == self.user.user_uuid).delete()
        else:
            logger.error("Instructions unclear, nothing to do")
        self.session.flush()

    def delete_user_education(self, educationUuids=None):
        if educationUuids and isinstance(educationUuids, list):
            for ex in educationUuids:
                self.session.query(UserEducation).filter(UserEducation.education_uuid == ex).delete()
        elif educationUuids and isinstance(educationUuids, str):
            self.session.query(UserEducation).filter(UserEducation.education_uuid == educationUuids).delete()
        elif not educationUuids:
            self.session.query(UserEducation).filter(UserEducation.user_uuid == self.user.user_uuid).delete()
        else:
            logger.error("Instructions unclear, nothing to do")
        self.session.flush()

    def delete_user_experience(self, experienceUuids=None):
        if experienceUuids and isinstance(experienceUuids, list):
            for ex in experienceUuids:
                self.session.query(UserExperience).filter(UserExperience.experience_uuid == ex).delete()
        elif experienceUuids and isinstance(experienceUuids, str):
            self.session.query(UserExperience).filter(UserExperience.experience_uuid == experienceUuids).delete()
        elif not experienceUuids:
            self.session.query(UserExperience).filter(UserExperience.user_uuid == self.user.user_uuid).delete()
        else:
            logger.error("Instructions unclear, nothing to do")
        self.session.flush()

    def delete_user(self):
        self.user.mark_deleted()
        self.user.hidden_from_search = True
        self.user.user_state.mark_deleted()
        self.user.user_state.hidden_from_search = True
        self.session.add(self.user)
        self.session.add(self.user.user_state)
        self.session.flush()

    def get_followers(self):
        return UserFollow.get_user_followers(session=self.session, user_uuid=self.user.user_uuid)

    def get_following(self):
        return UserFollow.get_user_following(session=self.session, user_uuid=self.user.user_uuid)

    def get_user_meta(self):
        user_meta = self.session.query(UserProfile).get(self.user.user_uuid)
        if not user_meta:
            user_meta = self.add_user_profile(first_name=self.user.first_name, last_name=self.user.last_name)
        return user_meta

    def get_user_email(self):
        return self.user.email

    def set_user_type(self, user_type: UserTypes):
        self.user.user_type = user_type
        self.session.add(self.user)
        self.session.flush()

    def set_user_flags(self, flag, state: bool):
        us = UserState()
        us.user_uuid = self.user.user_uuid
        if flag == 'sponsored_content_enabled':
            us.sponsored_content_enabled = state
            self.user.sponsored_content_enabled = state
        if flag == 'onboarding_completed':
            us.onboarding_completed = state
            self.user.onboarding_completed = state
        if flag == 'onboarding_interests_completed':
            us.onboarding_interests_completed = state
            self.user.onboarding_interests_completed = state
        if flag == 'hidden_from_search':
            us.hidden_from_search = state
            self.user.hidden_from_search = state
        self.session.merge(us)
        self.session.add(self.user)
        self.session.flush()

    def set_user_email(self, email: str):
        self.user.email = email
        self.session.add(self.user)
        self.session.flush()

    def update_user_profile(self, profile_update: UpdateUserModel):
        if not isinstance(profile_update, UpdateUserModel):
            raise ValueError("Update user profile requires an UpdateUserModel instance")
        user_meta = self.get_user_meta()
        u = profile_update.dict(exclude_unset=True)
        logger.debug("Updating profile with: %s", profile_update.json(indent=2))
        for k, v in u.items():
            if hasattr(user_meta, k):
                setattr(user_meta, k, v)
                logger.debug("Set item %s to %s", k, v)
        self.session.add(user_meta)
        self.session.flush()

    def update_username(self, username):
        self.user.username = username
        self.session.add(self.user)
        self.session.flush()

    def update_first_name(self, first_name):
        self.user.first_name = first_name
        self.session.add(self.user)
        self.session.flush()

    def update_last_name(self, last_name):
        self.user.last_name = last_name
        self.session.add(self.user)
        self.session.flush()

    def set_onboarding_state(self, onboarding_state: OnboardingState):
        us = UserState()
        us.user_uuid = self.user.user_uuid
        us.onboarding_state = onboarding_state
        self.session.merge(us)
        self.session.flush()


class OnboardingWorkflow:
    @staticmethod
    def _get_next_state(user: User,
                        is_user_in_usa: bool,
                        current_state: OnboardingState = None) -> Optional[OnboardingState]:
        """
        Determines the next step in the onboarding workflow and returns it.  Recurses until a state is found where
        the user has not met the required conditions to proceed or has completed.
        :return:
        """

        # Terminate once user does not meet requirements to proceed
        if current_state and not current_state.has_required_data(user=user):
            return current_state
        elif current_state and current_state is OnboardingState.COMPLETED:
            return current_state

        # Move to next step
        if current_state is None:
            next_state = OnboardingState.COUNTRY

        elif current_state == OnboardingState.COUNTRY:
            next_state = OnboardingState.USA_INFORMATION if is_user_in_usa else OnboardingState.INFORMATION

        elif current_state == OnboardingState.USA_INFORMATION:
            next_state = OnboardingState.GRAD_DATE

        elif current_state == OnboardingState.INFORMATION:
            next_state = OnboardingState.GRAD_DATE

        elif current_state == OnboardingState.GRAD_DATE:
            next_state = OnboardingState.VERIFICATION

        elif current_state == OnboardingState.VERIFICATION:
            next_state = OnboardingState.USERNAME

        elif current_state == OnboardingState.CONFIRMATION:
            next_state = OnboardingState.USERNAME

        elif current_state == OnboardingState.USERNAME:
            next_state = OnboardingState.COMPLETED

        else:
            raise InvalidOnboardingState(msg=f"Unknown state: {current_state}")

        return OnboardingWorkflow._get_next_state(user=user,
                                                  current_state=next_state,
                                                  is_user_in_usa=is_user_in_usa)

    @staticmethod
    def update_onboarding_state(user_uuid: str, session: Session):
        mgmt = UserManagement(user_uuid=user_uuid, session=session)
        is_user_in_usa = mgmt.user.is_user_in_usa(session=session)
        next_state = OnboardingWorkflow._get_next_state(user=mgmt.user, is_user_in_usa=is_user_in_usa)

        if next_state:
            mgmt.set_onboarding_state(onboarding_state=next_state)

        if next_state == OnboardingState.COMPLETED:
            mgmt.set_user_flags(flag='onboarding_completed', state=True)
