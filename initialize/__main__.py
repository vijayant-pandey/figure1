import logging
import figure1.configuration.log_settings

from celery.canvas import Signature

from figure1.common.models.firebase import sync_firestore_data_versions_task
from figure1.common.token_rotator import run_token_rotator
from figure1.common.elasticsearch import cases_startup, user_startup, comment_startup, \
    search_term_index_startup, specialty_startup, elasticsearch_credential_startup, campaign_startup

from figure1.feeds.feed_tasks import generate_preview_feeds_task
from figure1.feeds.sponsored_content import get_all_sponsored_content
from figure1.store import SponsoredContentCache
from figure1.admin.reference_data import initialize_feed_types
from figure1.common.base import update_trending_records
from figure1.aggregation import regenerate_new_cases_task

logger = logging.getLogger('init')


def _initialize():
    run_token_rotator()
    elasticsearch_credential_startup()
    _initialize_elasticsearch()
    _initialize_feeds()
    _initialize_sponsored_content()
    _initialize_firestore_data_versions()
    _initialize_datafeeds()


def _initialize_feeds():
    """
    Required to ensure that new feed types are populated and that preview feeds are populated
    :return:
    """
    feed_update = initialize_feed_types.si()
    feed_update.link(update_trending_records.si())
    feed_update.link(generate_preview_feeds_task.si())
    feed_update.apply_async()


def _initialize_elasticsearch():
    case_index_task = cases_startup()
    if case_index_task is not None:
        case_index_task.apply_async()
    search_term_index_startup.apply_async()
    user_startup.apply_async()
    comment_startup.apply_async()
    specialty_startup.apply_async()
    campaign_startup.apply_async()


def _initialize_sponsored_content():
    """
    Generates a list of all sponsored content if one doesn't exist
    :return:
    """
    if SponsoredContentCache.get_sponsored_content_size() < 10:
        SponsoredContentCache.write_sponsored_content(list(get_all_sponsored_content()))


def _initialize_firestore_data_versions():
    """
    Sync the latest firestore data versions to configurationDB.versions
    :return:
    """
    sync_firestore_data_versions_task.apply_async()


def _initialize_datafeeds():
    """
    Tasks to ensure the datafeeds are available
    :return:
    """
    regenerate_new_cases_task.apply_async()


logger.info("Running initialization tasks")
_initialize()
logger.info("Initialization tasks sent")
