import logging
from .user_events import handle_user_verification_state_change, handle_profession_change_approved
from sqlalchemy import event
from sqlalchemy.orm.base import NEVER_SET
from figure1.common.types import VerificationStatus, VerificationType
from figure1.common.models.db import UserVerification, ProfessionChangeRequest
from figure1.configuration import app_settings

logger = logging.getLogger(__name__)

verification_state = {}


@event.listens_for(ProfessionChangeRequest.request_resolved, 'set', named=True, active_history=True, raw=True)
def handle_resolve_change_request(target, value, oldvalue, **kw):
    verification_uuid = target.dict.get('verification_uuid')

    if value == oldvalue:
        return value

    if value is True:
        if verification_uuid is not None:
            handle_profession_change_approved(verification_uuid=verification_uuid)
        else:
            logger.error("Request set to resolved, but no verification uuid passed, nothing to do")


@event.listens_for(UserVerification.verification_status, 'set', named=True, active_history=True, raw=True)
def handle_verification_state_change(**kw):
    """
    Handles any changes made to verification state. The purpose is to trigger a case transition
    :param kw:
    :return:
    """

    target = kw['target']
    v = kw['value']
    previous_value = kw['oldvalue']
    verification_uuid = target.dict.get("verification_uuid")
    user_uuid = target.dict.get("user_uuid")
    previous_state = {}
    if verification_uuid in verification_state:
        previous_state = verification_state.get(verification_uuid)

    logger.info("Target verification_uuid is %s", target.dict.get("verification_uuid"))
    if app_settings.verification_event_listener_enabled is False:
        logger.debug("Verification event listener is disabled, nothing to do")
        return v

    if previous_state.get("last_set_state") == v:
        logger.info("This state was already set, do nothing")
        return v

    if previous_value is NEVER_SET:
        logger.error("Net new value, do nothing")
    else:

        if v == VerificationStatus.VERIFIED:
            verification_state.update({verification_uuid: {'last_set_state': v}})
            handle_user_verification_state_change(verification_uuid=verification_uuid,
                                                  user_uuid=user_uuid,
                                                  state=v,
                                                  previous_state=previous_value)
            return v
        elif v == previous_value:
            logger.info("Caught transition between the same states, do nothing")
        else:
            logger.info("State changed from %s to %s, executing transition", previous_value, v)
            verification_state.update({verification_uuid: {'last_set_state': v}})
            handle_user_verification_state_change(verification_uuid=verification_uuid,
                                                  user_uuid=user_uuid,
                                                  state=v,
                                                  previous_state=previous_value)
    return v
