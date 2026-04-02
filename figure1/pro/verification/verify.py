import uuid
import logging
from typing import Dict, Any
from celery import group
from celery.canvas import Signature
from sqlalchemy.orm import Session

from figure1.common.firebase import do_firebase_sync
from figure1.common.helpers.user import OnboardingWorkflow
from figure1.common.helpers.user import UserManagement
from figure1.common.models.db import User
from figure1.common.models.db import CommunicationGroup
from figure1.common.models.db import UserCommunicationPreferences
from figure1.common.models.db import CommunicationSettings
from figure1.common.types import UserVerificationUpdate
from figure1.common.types import OnboardingState
from figure1.common.types import VerificationType
from figure1.common.types import VerificationStatus
from figure1.common.types import CommunicationTypes
from figure1.common.types import CommunicationMethods
from figure1.common.utils import validate_npi
from figure1.common.utils import generate_presigned_s3_upload_url
from figure1.configuration import app_settings
from figure1.core import managed_session
from figure1.events import UserEvents
from figure1.common.npi.api import NPIResponse
from figure1.exceptions import VerificationMethodNotFound
from figure1.exceptions import UserNotFound
from figure1.exceptions import InvalidNPINumber
from .model_methods import update_verification_request
from .model_methods import add_npi_data
from .model_methods import add_license_data
from .model_methods import set_user_location
from .tasks import get_npi_info

logger = logging.getLogger(__name__)


@managed_session
def verify_user(update: UserVerificationUpdate, session: Session):
    task = None
    user = User.get_user_by_uid(user_uid=update.user_uid, session=session, raise_exception=True)
    user_uuid = str(user.user_uuid)
    if update.method is VerificationType.PHOTO:
        _verify_by_photo(user_uuid=user_uuid, update=update, session=session)
    elif update.method is VerificationType.NPI:
        task = _verify_by_npi(user_uuid=user_uuid, update=update, session=session)
        mgmt = UserManagement(user_uuid=user_uuid, session=session)
        mgmt.set_onboarding_state(onboarding_state=OnboardingState.CONFIRMATION)
    elif update.method is VerificationType.LICENSE:
        _verify_by_license(user_uuid=user_uuid, update=update, session=session)
    elif update.method is VerificationType.INSTITUTIONAL_EMAIL:
        _verify_by_institutional_email(user_uuid=user_uuid, update=update, session=session)
    else:
        raise VerificationMethodNotFound

    if update.method is not VerificationType.NPI:
        OnboardingWorkflow.update_onboarding_state(user_uuid=user_uuid, session=session)
    session.commit()
    if task:
        task = group(task, do_firebase_sync.si(firebasemodel='FirebaseUsersDB', uuid=user_uuid))
    else:
        task = do_firebase_sync.si(firebasemodel='FirebaseUsersDB', uuid=user_uuid)

    return {
        'onboardingState': user.user_state.onboarding_state.value,
        'task': task
    }


def _verify_by_photo(user_uuid: uuid,
                     update: UserVerificationUpdate,
                     session: Session):
    update_verification_request(user_uuid=user_uuid,
                                verification_type=VerificationType.PHOTO,
                                verification_status=VerificationStatus.PENDING_MANUAL_VERIFICATION,
                                verification_photos=update.photos,
                                session=session)
    if update.license_country_code or update.license_state_code:
        set_user_location(user_uuid=user_uuid,
                          state_uuid=update.license_state_code,
                          country_uuid=update.license_country_code,
                          session=session)
    session.flush()


def _verify_by_npi(user_uuid: uuid, update: UserVerificationUpdate, session: Session) -> Signature:
    npi_number = update.npi_number
    if not validate_npi(npi=npi_number):
        raise InvalidNPINumber(return_code=400, user_uuid=user_uuid, npi=npi_number)

    entry = update_verification_request(user_uuid=user_uuid,
                                        verification_type=VerificationType.NPI,
                                        graduation_year=update.graduation_year,
                                        school_uuid=update.license_school_code,
                                        session=session)
    add_npi_data(user_uuid=user_uuid, npi_number=npi_number, session=session, verification_uuid=entry.verification_uuid)

    # Note: npi verification failure sets state to PENDING_MANUAL_VERIFICATION
    session.flush()
    return get_npi_info.si(npi=npi_number, user_uuid=user_uuid)


def _verify_by_license(user_uuid: uuid,
                       update: UserVerificationUpdate,
                       session: Session):
    verification = update_verification_request(user_uuid=user_uuid,
                                               verification_type=VerificationType.LICENSE,
                                               verification_status=VerificationStatus.PENDING_MANUAL_VERIFICATION,
                                               graduation_year=update.graduation_year,
                                               school_uuid=update.license_school_code,
                                               session=session)
    add_license_data(user_uuid=user_uuid,
                     verification_uuid=verification.verification_uuid,
                     license_number=update.license_number,
                     country_uuid=update.license_country_code,
                     state_uuid=update.license_state_code,
                     session=session)


def _verify_by_institutional_email(user_uuid: uuid,
                                   update: UserVerificationUpdate,
                                   session: Session):
    update_verification_request(user_uuid=user_uuid,
                                verification_status=VerificationStatus.PENDING_MANUAL_VERIFICATION,
                                verification_type=VerificationType.INSTITUTIONAL_EMAIL,
                                institutional_email=update.institutional_email,
                                session=session)
    if update.license_country_code or update.license_state_code:
        set_user_location(user_uuid=user_uuid,
                          state_uuid=update.license_state_code,
                          country_uuid=update.license_country_code,
                          session=session)


def verify_by_npi(user_uuid: uuid, update: UserVerificationUpdate, session: Session) -> Signature:
    return _verify_by_npi(user_uuid, update, session)


@managed_session
def save_comms_for_user(user_uid, request, session=None):
    user = User.get_user_by_uid(user_uid, session, raise_exception=True)
    is_sms = request.get('is_sms', False)
    is_push = request.get('is_push', False)
    is_email = request.get('is_email', False)
    phone_number = request.get('phone_number')
    for vg in session.query(CommunicationGroup) \
            .filter(CommunicationGroup.communication_group_type == CommunicationTypes.TRANSACTIONAL,
                    CommunicationGroup.communication_group_name == 'Verification') \
            .all():
        comm_setting = session.query(CommunicationSettings) \
            .filter(CommunicationSettings.communication_group_uuid == vg.communication_group_uuid).one_or_none()
        if not comm_setting:
            continue
        if comm_setting.communication_method is CommunicationMethods.EMAIL:
            UserCommunicationPreferences.set_user_preference(user_uuid=user.user_uuid, session=session,
                                                             communication_uuid=comm_setting.communication_uuid,
                                                             communication_setting=is_email)
        if comm_setting.communication_method is CommunicationMethods.SMS:
            UserCommunicationPreferences.set_user_preference(user_uuid=user.user_uuid, session=session,
                                                             communication_uuid=comm_setting.communication_uuid,
                                                             communication_setting=is_sms)
        if comm_setting.communication_method is CommunicationMethods.PUSH:
            UserCommunicationPreferences.set_user_preference(user_uuid=user.user_uuid, session=session,
                                                             communication_uuid=comm_setting.communication_uuid,
                                                             communication_setting=is_push)
    UserEvents.USER_COMM_PREFS_UPDATED(user_uuid=user.user_uuid, phone_number=phone_number, session=session)

    return {'success': f"User by user_uid={user_uid} has saved verification communication preferences"}


def parse_npi_data(data: Dict[str, Any]):
    response = NPIResponse.parse_obj(data)
    return response.to_summary().dict()


@managed_session
def get_upload_url(user_uid, session):
    User.get_user_uuid_by_uid(user_uid=user_uid, session=session, raise_exception=True)
    presigned_url = generate_presigned_s3_upload_url(upload_path=f"users/verification/{user_uid}",
                                                     expires_in=600,
                                                     include_filename=True)
    return {'media_upload_url': presigned_url,
            "media_download_domain": app_settings.figure1_imgix_url}
