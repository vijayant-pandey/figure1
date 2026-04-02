import logging
from .case_events import on_case_state_change
from sqlalchemy import event
from sqlalchemy.orm.base import NEVER_SET
from figure1.common.models.db import Case
from figure1.common.elasticsearch import update_case_state
from figure1.configuration import app_settings

logger = logging.getLogger(__name__)
case_state = {}


@event.listens_for(Case.state, 'set', named=True, active_history=True, raw=True)
def handle_case_state_change(**kw):
    """
    Handles any changes made to case state. The purpose is to trigger a case transition
    :param kw:
    :return:
    """

    target = kw['target']
    v = kw['value']
    previous_value = kw['oldvalue']
    case_uuid = target.dict.get("case_uuid")

    previous_state = {}
    if case_uuid in case_state:
        previous_state = case_state.get(case_uuid)

    if app_settings.case_state_event_listener_enabled is False:
        logger.debug("Case state event listener is disabled, nothing to do")
        return v

    logger.info("Target case_uuid is %s", target.dict.get("case_uuid"))

    if previous_value is NEVER_SET:
        logger.info("Net new value - possibly set via session merge, do not execute anything.")
    else:
        if previous_state.get("last_set_state") == v:
            logger.info("This state was already set, do nothing")
        elif v == previous_value:
            logger.info("Caught transition between the same states, do nothing")
        else:
            logger.info("State changed from %s to %s, executing transition", previous_value, v)
            case_state.update({case_uuid: {'last_set_state': v}})
            update_case_state(case_uuid=case_uuid, state=v)
            on_case_state_change.delay(case_uuid=case_uuid, from_state=previous_value, to_state=v)
    return v
