import logging
import os
import csv
import uuid
import re

from figure1.common.models.db import CommunicationGroup, \
    CommunicationSettings, \
    UserCommunicationPreferences, CommunicationChannel
from figure1.core import managed_session, FirebaseTaskBase, celery_app
from figure1.common.types import CommunicationTypes, CommunicationMethods, \
    ActivityNotificationCategories

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, base=FirebaseTaskBase, name='figure1.backend.initialize_communication_groups')
def initialize_communication_groups(self, clean=None):
    logger.info("Syncing communication groups to firestore...")
    load_activity_skeleton(session=self.session)
    sync_communication_settings(session=self.session, fs_client=self.fs_client)
    if clean:
        clean_duplicate_subscriptions_task.apply_async()
    logger.info("Done updating communication groups")


@celery_app.task(bind=True, base=FirebaseTaskBase, name='figure1.backend.clean_differential_subscriptions')
def clean_duplicate_subscriptions_task(self):
    r = _remove_duplicated_user_preferences(session=self.session, limit=1_000_000)
    while r == 1_000_000:
        self.session.commit()
        r = _remove_duplicated_user_preferences(session=self.session, limit=1_000_000)


def sync_communication_settings(session, fs_client):
    docV2 = fs_client.collection('referenceData').document('communicationSettingsV2')
    fs_data_v2 = UserCommunicationPreferences.get_default_preferences_v2(session=session)
    docV2.set(fs_data_v2)


def _normalize_text(text):
    return re.sub(r'\s+', repl='', string=text)


def load_groups(data, session):
    group_type = _normalize_text(data.pop(0)).lower()
    group_name = data.pop(0)
    group_description = data.pop(0)
    group_display_order = data.pop(0)

    for c in CommunicationTypes:
        if isinstance(group_type, CommunicationTypes):
            continue
        if c.value == group_type:
            group_type = c

    if group_display_order:
        try:
            group_display_order = int(group_display_order)
        except ValueError:
            group_display_order = 0
    else:
        group_display_order = 0
    group: CommunicationGroup = session.query(CommunicationGroup) \
        .filter(CommunicationGroup.communication_group_name == group_name,
                CommunicationGroup.communication_group_type == group_type) \
        .one_or_none()
    if not group:
        group = CommunicationGroup()
        group.communication_group_type = group_type
        group.communication_group_uuid = uuid.uuid4()

    group.communication_group_name = group_name
    group.communication_group_description = group_description
    group.communication_group_display_order = group_display_order
    session.add(group)


def load_settings(data, session):
    """
    There are several required fields
    :param data:
    :param session:
    :return:
    :raises: ValueError if fields are not the correct type
    """
    iterable_message_type = int(data.pop(0))
    iterable_channel_id = int(data.pop(0))
    communication_type = _normalize_text(data.pop(0)).lower()
    communication_method = _normalize_text(data.pop(0)).lower()
    communication_group_name = data.pop(0)
    communication_setting_name = data.pop(0)
    communication_setting_description = data.pop(0)
    communication_setting_display_order = data.pop(0)
    communication_setting_default = _normalize_text(data.pop(0)).upper()
    communication_setting_enabled = _normalize_text(data.pop(0)).upper()
    legacy_id = data.pop(0)

    for c in CommunicationTypes:
        if isinstance(communication_type, CommunicationTypes):
            continue
        if c.value == communication_type.lower():
            communication_type = c

    for m in CommunicationMethods:
        if isinstance(communication_method, CommunicationMethods):
            continue
        if m.value == communication_method.lower():
            communication_method = m

    if communication_setting_default == 'ON':
        communication_setting_default = True
    else:
        communication_setting_default = False

    if communication_setting_enabled == 'ON':
        communication_setting_enabled = True
    else:
        communication_setting_enabled = False

    if communication_setting_display_order:
        try:
            communication_setting_display_order = int(communication_setting_display_order)
        except ValueError:
            communication_setting_display_order = 0
    else:
        communication_setting_display_order = 0
    group = session.query(CommunicationGroup) \
        .filter(CommunicationGroup.communication_group_name == communication_group_name,
                CommunicationGroup.communication_group_type == communication_type) \
        .one_or_none()
    if not group:
        logger.error("Group %s with type %s not found", communication_group_name, communication_type.value)
        return None

    channel = session.query(CommunicationChannel.communication_channel_uuid) \
        .filter(CommunicationChannel.communication_channel_id == iterable_channel_id) \
        .one_or_none()
    if not channel:
        logger.error("Channel with id %s not found", iterable_channel_id)
    communication_channel_uuid = channel[0] if channel else None

    ex: CommunicationSettings = session.query(CommunicationSettings) \
        .filter(CommunicationSettings.communication_iterable_message_type == iterable_message_type) \
        .one_or_none()

    if not ex:
        ex = CommunicationSettings()
        ex.communication_group_uuid = group.communication_group_uuid
        ex.communication_uuid = uuid.uuid4()

    ex.communication_method = communication_method
    ex.communication_name = communication_setting_name
    ex.communication_description = communication_setting_description
    ex.communication_enabled = communication_setting_enabled
    ex.communication_default_setting = communication_setting_default
    ex.communication_display_order = communication_setting_display_order
    ex.communication_iterable_message_type = iterable_message_type
    ex.communication_channel_uuid = communication_channel_uuid
    ex.legacy_id = legacy_id if legacy_id else None
    session.add(ex)


@managed_session
def load_communication_settings_from_csv(filename, session):
    if os.path.isfile(filename):
        with open(filename, mode='r', newline='') as fn:
            reader = csv.reader(fn)
            for line in reader:
                load_settings(data=line, session=session)
    else:
        return {"Error": f"Filename {filename} is not a file"}
    return


@managed_session
def load_communication_groups_from_csv(filename, session):
    if os.path.isfile(filename):
        with open(filename, mode='r', newline='') as fn:
            reader = csv.reader(fn)
            for line in reader:
                load_groups(data=line, session=session)
    else:
        return {"Error": f"Filename {filename} is not a file"}
    return


@managed_session
def load_activity_skeleton(session):
    """
    This ensures there are database entries for all possible settings, if an existing group or setting is detected,
    nothing is changed. No settings are deleted here.

    :param session:
    :return:
    """
    default_email_communication_setting = {
        'communication_method': CommunicationMethods.EMAIL,
        'communication_enabled': False,
        'communication_default_setting': False,
        'communication_name': 'email',
        'communication_description': 'email',
        'communication_iterable_message_type': 0,
        'communication_display_order': 0,
    }

    default_push_communication_setting = {
        'communication_method': CommunicationMethods.PUSH,
        'communication_enabled': False,
        'communication_default_setting': False,
        'communication_name': 'push',
        'communication_description': 'push',
        'communication_iterable_message_type': 0,
        'communication_display_order': 1,
    }
    categories = {
        'WeeklyDigest': {
            "groups": [
                {
                    'communication_group_name': "Weekly summaries of comments, likes, followers",
                    'communication_group_description': "",
                    'communication_group_display_order': 0,
                    'communication_settings': [default_email_communication_setting]
                },
            ]
        },
        'SavedCases': {
            "groups": [
                {
                    'communication_group_name': "New updates on cases you saved",
                    'communication_group_description': "",
                    'communication_group_display_order': 0,
                    'communication_settings': [default_email_communication_setting,
                                               default_push_communication_setting]
                },
                {
                    'communication_group_name': "New cases from members whose cases you saved",
                    'communication_group_description': "",
                    'communication_group_display_order': 1,
                    'communication_settings': [default_email_communication_setting,
                                               default_push_communication_setting]
                },
            ]
        },
        'Paging': {
            "groups": [
                {
                    'communication_group_name':
                        "Newly shared cases in your specialty requiring time sensitive insights",
                    'communication_group_description': "",
                    'communication_group_display_order': 0,
                    'communication_settings': [default_email_communication_setting,
                                               default_push_communication_setting]
                },
            ]
        },
        'Follow': {
            "groups": [
                {
                    'communication_group_name': "New cases from members you follow",
                    'communication_group_description': "",
                    'communication_group_display_order': 0,
                    'communication_settings': [default_email_communication_setting,
                                               default_push_communication_setting]
                },
                {
                    'communication_group_name': "New followers",
                    'communication_group_description': "",
                    'communication_group_display_order': 1,
                    'communication_settings': [default_email_communication_setting,
                                               default_push_communication_setting]
                },
            ]
        },
        'CommentsRepliesLikes': {
            'groups': [
                {
                    'communication_group_name': "Comments on your cases",
                    'communication_group_description': "",
                    'communication_group_display_order': 0,
                    'communication_settings': [default_email_communication_setting,
                                               default_push_communication_setting]
                },
                {
                    'communication_group_name': "Likes on your cases",
                    'communication_group_description': "",
                    'communication_group_display_order': 1,
                    'communication_settings': [default_email_communication_setting,
                                               default_push_communication_setting]
                },
                {
                    'communication_group_name': "Replies to your comments",
                    'communication_group_description': "",
                    'communication_group_display_order': 2,
                    'communication_settings': [default_email_communication_setting,
                                               default_push_communication_setting]
                },
                {
                    'communication_group_name': "Comments on cases you saved",
                    'communication_group_description': "",
                    'communication_group_display_order': 3,
                    'communication_settings': [default_email_communication_setting,
                                               default_push_communication_setting]
                }
            ]
        }
    }

    for k in categories.keys():
        if k not in ActivityNotificationCategories.__members__:
            logger.error("Notification not found %s", k)
            continue

        for g in categories[k]['groups']:
            logger.info("Handling group %s", g['communication_group_name'])
            find_existing_group = session.query(CommunicationGroup.communication_group_uuid) \
                .filter(CommunicationGroup.communication_group_type == CommunicationTypes.ACTIVITY,
                        CommunicationGroup.communication_group_category == ActivityNotificationCategories[k],
                        CommunicationGroup.communication_group_name == g['communication_group_name'])
            group = find_existing_group.one_or_none()
            logger.debug("Executing Query %s", find_existing_group.statement)
            if group:
                logger.info("Group exists, checking communication settings")
                for skel_setting in g['communication_settings']:
                    find_communication_setting = session.query(CommunicationSettings) \
                        .filter(CommunicationSettings.communication_group_uuid == group[0],
                                CommunicationSettings.communication_method == skel_setting['communication_method'])
                    logger.info("Handling setting %s", skel_setting['communication_name'])
                    logger.debug("Executing Query %s", find_communication_setting.statement)
                    if find_communication_setting.one_or_none():
                        logger.info("Existing setting found, continue")
                        continue
                    else:
                        logger.info("No setting found, setting default")
                        default = CommunicationSettings()
                        default.communication_group_uuid = group[0]
                        default.communication_uuid = uuid.uuid4()
                        for setting, v in skel_setting.items():
                            setattr(default, setting, v)
                        session.add(default)
            else:
                logger.info("No group found, creating a new one with name %s", g['communication_group_name'])
                default_group = CommunicationGroup()
                default_group.communication_group_uuid = uuid.uuid4()
                default_group.communication_group_name = g['communication_group_name']
                default_group.communication_group_description = g['communication_group_description']
                default_group.communication_group_display_order = g['communication_group_display_order']
                default_group.communication_group_category = ActivityNotificationCategories[k]
                default_group.communication_group_type = CommunicationTypes.ACTIVITY
                session.add(default_group)
                session.flush()
                logger.info("Group created, adding default settings")
                for skel_setting in g['communication_settings']:
                    logger.info("Adding default setting %s", skel_setting['communication_name'])
                    default_settings = CommunicationSettings()
                    default_settings.communication_uuid = uuid.uuid4()
                    default_settings.communication_group_uuid = default_group.communication_group_uuid
                    for setting, v in skel_setting.items():
                        setattr(default_settings, setting, v)
                    session.add(default_settings)
                    session.flush()
    session.commit()


def _remove_duplicated_user_preferences(session, limit):
    """
    Find user preferences that duplicate default settings and remove them
    :param session:
    :return:
    """
    q = session.query(UserCommunicationPreferences) \
        .join(CommunicationSettings,
              CommunicationSettings.communication_uuid == UserCommunicationPreferences.communication_uuid) \
        .filter(UserCommunicationPreferences.communication_setting
                == CommunicationSettings.communication_default_setting)

    logger.info("Total preferences %s", q.count())
    count = 0
    for dup in q.yield_per(1000).limit(limit):
        session.delete(dup)
        count += 1
        if not count % 10000:
            session.flush()
            logger.info("Processed %s", count)
    return count
