import logging
from figure1.core import celery_app
from figure1.configuration import es_settings
from figure1.common.base import update_trending_records
from figure1.common.elasticsearch import elasticsearch_key_rotation, \
    elasticsearch_credential_startup, \
    update_user_typeahead
from figure1.common.token_rotator import run_token_rotator_task, secs_between_token_rotations
from figure1.common.iterable import add_scheduled_aggregation_tasks
from figure1.tools import sync_unsynced_users_task
from figure1.feeds.feed_tasks import generate_preview_feeds_task
from figure1.aggregation import generate_user_recommendations_task
from figure1.notifications import notify_users_activity_reminder_task
from figure1.notifications import notify_users_of_not_chosen_diagnosis_cases_task
from figure1.common.firebase import rolling_case_sync
from figure1.aggregation import clean_expired_new_cases_task
from .change_request_cleanup import cleanup_change_request_task

logger = logging.getLogger(__name__)


@celery_app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    logger.debug("Loading scheduled tasks...")
    add_scheduled_aggregation_tasks(sender=sender, **kwargs)
    sender.add_periodic_task(secs_between_token_rotations, run_token_rotator_task.si(), name='Rotate jwt token')
    sender.add_periodic_task(300.0, elasticsearch_key_rotation.si(), name='Update access key')
    sender.add_periodic_task(43201.0, elasticsearch_credential_startup.si(), name='Regenerate Elasticsearch credential')
    sender.add_periodic_task(300, generate_user_recommendations_task.si(), name='Update user profiles')
    sender.add_periodic_task(3800, update_trending_records.si(), name='Update Trend Score')

    sender.add_periodic_task(110, sync_unsynced_users_task.si(), name="Synced unsynced users to firestore")

    sender.add_periodic_task(43200.0, update_user_typeahead.si(
        target_index_name=es_settings.public_search_terms_alias),
                             name="Update user search type-ahead")

    sender.add_periodic_task(3600, generate_preview_feeds_task.si(), name="Generate preview feeds")
    sender.add_periodic_task(43200.0,
                             notify_users_of_not_chosen_diagnosis_cases_task.si(),
                             name="Notify users of not chosen case diagnosis in the last three days.")
    sender.add_periodic_task(7200,
                             notify_users_activity_reminder_task.si(),
                             name="Send activity reminder notifications")
    sender.add_periodic_task(359,
                             rolling_case_sync.si(limit=20),
                             name="Rolling sync of cases")

    sender.add_periodic_task(1800,
                             clean_expired_new_cases_task.si(),
                             name="Clean expired cases from new case datafeed")
    logger.info("Loaded celery periodic tasks")
