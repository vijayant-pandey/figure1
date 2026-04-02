import logging
from figure1.core import TaskBase, celery_app
from .domain import sync_user_communication_preferences, sync_user_communication_preferences_v2
from figure1.common.models.db import UserCommunicationPreferences

logger = logging.getLogger("figure1.common.comms.task")


@celery_app.task(bind=True,
                 base=TaskBase,
                 name='figure1.frontend.sync_communication_preferences')
def sync_communication_preferences_task(self, user_uuid):
    """
    Push communication preferences to firestore
    :return:
    """
    sync_user_communication_preferences(user_uuid=user_uuid, session=self.session)


@celery_app.task(bind=True,
                 base=TaskBase,
                 name='figure1.frontend.initialize_user_communication_preferences')
def initialize_user_communication_preferences_task(self, user_uuid):
    """
    Initializes the UserCommunicationPreferences for a user_uuid

    This task will only set user preferences on initial user creation.  If preferences already exist, do nothing.
    Otherwise, creates a UserCommunicationPreference for any specialty defaults that differ from the
    CommunicationSetting default.
    """
    if list(UserCommunicationPreferences.get_user_preference(user_uuid=user_uuid, session=self.session)):
        return

    UserCommunicationPreferences.initialize_user_communication_preferences(user_uuid=user_uuid, session=self.session)


@celery_app.task(bind=True,
                 base=TaskBase,
                 name='figure1.frontend.sync_communication_preferences_v2')
def sync_communication_preferences_task_v2(self, user_uuid):
    """
    Push communication preferences to firestore
    :return:
    """
    sync_user_communication_preferences_v2(user_uuid=user_uuid, session=self.session)
