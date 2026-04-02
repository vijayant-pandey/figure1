import logging
from sqlalchemy import event
from sqlalchemy.orm.base import NO_VALUE
from figure1.common.models.db import UserState
from .user_events import on_onboarding_state_change

logger = logging.getLogger(__name__)
onboarding_state = {}


@event.listens_for(UserState.onboarding_state, 'set', named=True, active_history=True, raw=True)
def handle_onboarding_state_change(**kw):
    """
    Handles changes to the user onboarding state.
    :param kw:
    :return:
    """

    target = kw['target']
    v = kw['value']
    previous_value = kw['oldvalue']
    user_uuid = target.dict.get('user_uuid')

    previous_state = {}
    if user_uuid in onboarding_state:
        previous_state = onboarding_state.get(user_uuid)

    logger.info("Target user_uuid is %s", target.dict.get("user_uuid"))

    if previous_value is NO_VALUE:
        logger.info("Net new value - possibly set via session merge, do not execute anything.")
    else:
        if previous_state.get("last_set_state") == v:
            logger.info("This state was already set, do nothing")
        elif v == previous_value:
            logger.info("Caught transition between the same states, do nothing")
        else:
            logger.info("State changed from %s to %s, executing transition", previous_value, v)
            onboarding_state.update({user_uuid: {'last_set_state': v}})
            if previous_value == NO_VALUE:
                previous_value = None
            on_onboarding_state_change.delay(user_uuid=user_uuid, from_state=previous_value, to_state=v)
        return v
