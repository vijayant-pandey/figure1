from mixpanel import MixpanelException

from figure1.core import TaskBase, celery_app
from figure1.common.mixpanel.domain import sync_user_to_mixpanel, \
    send_event_to_mixpanel, \
    sync_user_legacy_data_to_mixpanel, \
    sync_user_device_to_mixpanel, \
    sync_user_devices_to_mixpanel


@celery_app.task(bind=True,
                 base=TaskBase,
                 autoretry_for=(MixpanelException,),
                 retry_backoff=True,
                 name='figure1.backend.update_mixpanel_user')
def update_mixpanel_user(self, user_uuid):
    sync_user_to_mixpanel(user_uuid=user_uuid, session=self.session)


@celery_app.task(bind=True,
                 base=TaskBase,
                 autoretry_for=(MixpanelException,),
                 retry_backoff=True,
                 name='figure1.backend.update_mixpanel_user_legacy_data')
def update_mixpanel_user_legacy_data(self, user_uuid):
    sync_user_legacy_data_to_mixpanel(user_uuid=user_uuid, session=self.session)


@celery_app.task(bind=True,
                 base=TaskBase,
                 autoretry_for=(MixpanelException,),
                 retry_backoff=True,
                 name='figure1.backend.send_mixpanel_event')
def send_mixpanel_event(self, user_uuid, event_name, properties):
    send_event_to_mixpanel(user_uuid=user_uuid, event_name=event_name, properties=properties)


@celery_app.task(bind=True,
                 base=TaskBase,
                 autoretry_for=(MixpanelException,),
                 retry_backoff=True,
                 name='figure1.backend.sync_device_tokens_to_mixpanel_task')
def sync_user_device_tokens_to_mixpanel_task(self, user_uuid, device_user_tokens):
    sync_user_devices_to_mixpanel(user_uuid, device_user_tokens)
