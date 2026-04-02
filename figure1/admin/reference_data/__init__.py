import enum
from .tasks_countries import initialize_countries
from .tasks_feed_types import initialize_feed_types
from .tasks_groups import sync_groups
from .tasks_labels import initialize_labels
from .tasks_legacy_specialties import initialize_legacy_specialties
from .tasks_locales import initialize_locales
from .tasks_notifications import initialize_communication_groups, \
    load_communication_groups_from_csv, \
    load_communication_settings_from_csv, \
    load_activity_skeleton
from .tasks_promotion_channels import sync_promotion_channels
from .tasks_schools import initialize_schools
from .tasks_specialties import initialize_specialties
from .tasks_standalone_emails import initialize_standalone_emails
from .tasks_topics import sync_topics
from .tasks_verification_tags import sync_verification_tags


class ReferenceDataTasks(enum.Enum):
    specialties = initialize_specialties
    feed_types = initialize_feed_types
    labels = initialize_labels
    locales = initialize_locales
    schools = initialize_schools
    notifications = initialize_communication_groups
    countries = initialize_countries
    standalone_emails = initialize_standalone_emails
    topics = sync_topics
    promotion_channels = sync_promotion_channels
    groups = sync_groups
