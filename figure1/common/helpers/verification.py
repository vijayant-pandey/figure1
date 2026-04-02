import datetime
import logging
import uuid
from datetime import timedelta
from datetime import timezone
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy.orm import make_transient
from sqlalchemy.orm.query import Query

from figure1.core import es
from figure1.common.models.db import ProfessionChangeRequest
from figure1.common.models.db import LegacyUser
from figure1.common.models.db import UserLicense
from figure1.common.models.db import UserNPI
from figure1.common.models.db import UserVerification
from figure1.common.models.db import UserVerificationTag
from figure1.common.models.db import VerificationNote
from figure1.common.types import VerificationStatus
from figure1.common.types import VerificationType
from figure1.common.types.elasticsearch import ESUserDocument
from figure1.configuration import es_settings
from figure1.core import managed_session
from figure1.exceptions import UserError

logger = logging.getLogger(__name__)


def update_user_tags(user_uuid, tags):
    """
    :param user_uuid: User uuid to apply the tags too
    :param tags: List of tuples of the form [tag_uuid, tag_name]
    :type tags: List[Tuple]
    :return:
    """
    users_index_alias = es_settings.users_alias
    doc = ESUserDocument(userUuid=user_uuid)
    es_doc = doc.get(index=users_index_alias, using=es, id=str(user_uuid))
    if es_doc is not None:
        if not isinstance(tags, list) or len(tags) == 0:
            es_doc.verificationTags = None
        else:
            es_doc.verificationTags = tags
        es_doc.save(index=users_index_alias, using=es, refresh=True)


def get_user_verification_record(user_uuid,
                                 verification_status=None,
                                 verification_type=None,
                                 session=None) -> Optional[UserVerification]:
    """
    Given a user_uuid, return a verification record or None. If a specific status is requested, a list is always
    returned
    :param user_uuid:
    :param verification_status:
    :param verification_type:
    :param session:
    :return:
    """

    q = Query([UserVerification], session=session).filter(UserVerification.user_uuid == user_uuid)

    q = q.execution_options(populate_existing=True)

    if verification_type is not None:
        q = q.filter(UserVerification.verification_type == verification_type)
    if verification_status == 'all':
        return q.all()
    elif verification_status is not None:
        q = q.filter(UserVerification.verification_status == verification_status)
        return q.all()
    else:
        q = q.filter(UserVerification.verification_status != VerificationStatus.ARCHIVED)
        return q.first()


def get_verification_record_by_uuid(verification_uuid, session=None):
    if session:
        return session.get(UserVerification, verification_uuid, populate_existing=True)
    return UserVerification.q.get(verification_uuid)


def create_profession_change_request(user_uuid,
                                     current_profession_uuid=None,
                                     requested_profession_uuid=None,
                                     session=None) -> str:
    user_record = get_user_verification_record(user_uuid=user_uuid,
                                               session=session)
    if not user_record:
        raise UserError(msg="No user verification record found")

    if user_record.profession_change_request is not None:
        if user_record.profession_change_request.request_resolved is False:
            logger.error("Unresolved profession change request")
            raise UserError(msg="Unresolved profession change request")

    if user_record and user_record.verification_status is not VerificationStatus.VERIFIED:
        logger.error("User status is %s", user_record.verification_status)
        raise UserError(return_code=400, msg='User is not verified, cannot open change request')

    user_record.verification_status = VerificationStatus.ARCHIVED
    user_record.profession_tree_uuid = current_profession_uuid

    v = UserVerification()
    v.user_uuid = user_uuid
    v.verification_uuid = uuid.uuid4()
    v.verification_status = VerificationStatus.CHANGE_REQUESTED

    change_request = ProfessionChangeRequest()
    change_request.verification_uuid = v.verification_uuid
    change_request.requested_profession = requested_profession_uuid
    change_request.archived_verification_uuid = user_record.verification_uuid
    change_request.request_resolved = False
    if user_record.verification_type.name.lower() == 'npi':
        if user_record.npi:
            user_npi = user_record.npi
            make_transient(user_npi)
            user_npi.verification_uuid = v.verification_uuid
            v.npi = user_npi
            v.verification_status = VerificationStatus.CHANGE_REQUESTED
            v.verification_type = VerificationType.NPI
            v.flagged_for_review = False

    v.profession_change_request = change_request

    session.add_all([user_record, v, change_request])
    session.flush()

    return str(v.verification_uuid)


def is_user_verified(user_uuid, session):
    for i in session.query(UserVerification.verification_status).filter(UserVerification.user_uuid == user_uuid).all():
        if i[0] == VerificationStatus.VERIFIED:
            return True
        if i[0] == VerificationStatus.CHANGE_REQUESTED:
            return True
    return False


def get_open_change_requests(change_opened: timedelta, session: Session, has_verification_type=None):
    """
    Returns a list of open change request entries
    :param change_opened: Timedelta object indicating the most recent change request to look for. This is to avoid
        returning change requests that may be in use by the user.
    :param session: Database session
    :type session: Session
    :param has_verification_type: If VerificationType is set, then return all open change requests of this type. If it
        None, then return open change requests that have no type.
    :type has_verification_type: VerificationType
    :return:
    """
    if not isinstance(change_opened, timedelta):
        raise ValueError("change_opened must be a timedelta object")
    if not isinstance(session, Session):
        raise ValueError("Session must be a database session")
    if has_verification_type is None:
        verification_type_filter = (UserVerification.verification_type.is_(None))
    elif isinstance(has_verification_type, VerificationType):
        verification_type_filter = (UserVerification.verification_type == has_verification_type)
    else:
        raise ValueError("has_verification_type must be None or VerificationType")
    q = session.query(UserVerification) \
        .filter(UserVerification.created_at <= datetime.datetime.now(tz=timezone.utc) - change_opened,
                verification_type_filter)
    return q.all()


@managed_session
def close_expired_empty_change_requests(close_from: timedelta, session=None):
    """
    Given a timedelta, close all of the empty change requests up to today - close_from
    :param close_from: Timedelta object to say where to stop looking for open change requests
    :param session:
    :return:
    """
    for cr in get_open_change_requests(change_opened=close_from, session=session):
        logger.info("Closing change request for user %s", cr.user_uuid)
        v = VerificationManagement(user_uuid=cr.user_uuid, moderator_uuid=None, session=session)
        v.reject_change_request()


class VerificationManagement:

    def __init__(self, user_uuid, moderator_uuid, session):
        self.user_uuid = user_uuid
        self.moderator_uuid = moderator_uuid
        self.session = session
        self.is_profession_change_request = False
        self.verification = get_user_verification_record(user_uuid=user_uuid, session=session)
        if self.verification.profession_change_request:
            self.is_profession_change_request = True

    def approve_change_request(self):
        """
        When request_resolved is set to True, it triggers an update of the user's profession
        :return:
        """
        if self.is_profession_change_request:
            self.verification.profession_change_request.request_resolved = True
        self.verification.verification_status = VerificationStatus.VERIFIED
        self.session.add(self.verification)
        self.session.flush()

    def reject_change_request(self):
        archived_verification_record = self.verification.profession_change_request.archived_verification_uuid
        if archived_verification_record is not None:
            verification_record = self.session.query(UserVerification).get(archived_verification_record)
            if verification_record is not None:
                verification_record.verification_status = VerificationStatus.VERIFIED
                self.session.add(verification_record)
                self.session.delete(self.verification)
            else:
                logger.error("Failed to find linked verification record")
        else:
            logger.error("No archived verification record is linked to this change request, going by date")
            first_archived_record = self.session.query(UserVerification) \
                .filter(UserVerification.user_uuid == self.user_uuid,
                        UserVerification.verification_status == VerificationStatus.ARCHIVED) \
                .order_by(UserVerification.created_at.desc()).first()
            first_archived_record.verification_status = VerificationStatus.VERIFIED
            self.session.add(first_archived_record)
            self.session.delete(self.verification)
        self.session.flush()

    def flagged_for_review(self, flag=False):
        self.verification.flagged_for_review = flag
        self.verification.last_modified_by = self.moderator_uuid

    def update_status(self, status):
        if self.verification.verification_status is VerificationStatus.CHANGE_REQUESTED:
            if status == VerificationStatus.VERIFIED:
                return self.approve_change_request()
            if status == VerificationStatus.REJECTED:
                return self.reject_change_request()
        self.verification.verification_status = status
        self.verification.last_modified_by = self.moderator_uuid

    def update_tags(self, tag_uuids):
        for t in self.session.query(UserVerificationTag) \
                .filter(UserVerificationTag.user_uuid == self.user_uuid) \
                .all():
            tag = UserVerificationTag.delete(user_uuid=self.user_uuid, tag_uuid=t.tag_uuid)
            self.session.merge(tag)
        self.session.flush()
        new_user_tags = []
        for tag_uuid in tag_uuids:
            uvt = UserVerificationTag.create(user_uuid=self.user_uuid,
                                             tag_uuid=tag_uuid,
                                             moderator_uuid=self.moderator_uuid)
            new_user_tags.append(self.session.merge(uvt))
        self.session.flush()
        es_update_tags = []
        for inst in new_user_tags:
            if inst.deleted_at is None:
                es_update_tags.append(inst.as_firestore_dict())
        update_user_tags(user_uuid=str(self.user_uuid), tags=es_update_tags)

    def update_npi_number(self, npi_number):
        self.verification.last_modified_by = self.moderator_uuid
        if self.verification.npi:
            self.verification.npi.npi_number = npi_number
        else:
            npi = UserNPI()
            npi.npi_number = npi_number
            npi.user_uuid = self.user_uuid
            npi.verification_uuid = self.verification.verification_uuid
            self.session.add(npi)

    def delete_npi(self):
        if self.verification.npi:
            self.session.delete(self.verification.npi)

    def update_license_number(self, license_number):
        self.verification.last_modified_by = self.moderator_uuid
        if self.verification.license:
            self.verification.license.license_number = license_number
        else:
            license = UserLicense()
            license.user_uuid = self.user_uuid
            license.license_number = license_number
            license.verification_uuid = self.verification.verification_uuid
            self.session.add(license)

    def update_school(self, school_uuid):
        self.verification.school_uuid = school_uuid
        self.verification.last_modified_by = self.moderator_uuid

    def update_graduation_year(self, graduation_year):
        self.verification.graduation_year = graduation_year
        self.verification.last_modified_by = self.moderator_uuid

    def add_note(self, moderator_uuid, text):
        VerificationNote.create(user_uuid=self.user_uuid,
                                moderator_uuid=moderator_uuid,
                                text=text,
                                session=self.session)
