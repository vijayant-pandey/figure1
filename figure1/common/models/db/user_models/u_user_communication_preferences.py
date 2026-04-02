from typing import Iterable
import logging
from sqlalchemy import ForeignKey, Column, Boolean, func, select
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from figure1.common.utils import replace_dict_key_value
from figure1.core import HasCreateUpdateDeleteTime, Base
from figure1.exceptions import CommunicationChannelNotFound
from figure1.common.models.db.reference_data_models import CommunicationSettings,\
    CommunicationGroup,\
    SpecialtyCommunicationSettings,\
    CommunicationChannel

from .u_user_model import User, UserState
from .u_user_specialty_tree_model import UserSpecialtyTreeV2
from figure1.common.types import UserCommunicationPreferencesModel, \
    CommunicationSettingsModel, \
    CommunicationTypes, \
    UserPreferencesModel, \
    UserPreferencesModelV2, \
    ActivityNotificationCategories, \
    ActivityCategories, \
    CommunicationMethods

from figure1.common.types.user_communication_preferences import ActivityNotificationCategorycomments, \
    ActivityNotificationCategoryfollow, \
    ActivityNotificationCategorypaging, \
    ActivityNotificationCategorysavedCases, \
    ActivityNotificationCategoryweeklyDigest

logger = logging.getLogger(__name__)


class UserCommunicationPreferences(Base, HasCreateUpdateDeleteTime):
    """
    Most of the settings are from the default settings table, things like name and so on, since the only thing a user
    can change is to turn a communication on or off, all we need to store here is the cross reference between user and
    preference and the current state set by the user.

    """
    __tablename__ = "u_user_communication_preferences"
    user_uuid = Column(UUID(as_uuid=True), ForeignKey(User.user_uuid), primary_key=True)
    communication_uuid = Column(UUID(as_uuid=True),
                                ForeignKey(CommunicationSettings.communication_uuid),
                                primary_key=True)
    communication_setting = Column(Boolean, nullable=False)
    communication = relationship('CommunicationSettings')

    @staticmethod
    def migrate_user_preferences(communication_uuid, new_communication_uuid, session, user_uuid=None):
        count = 0
        user_pref_query = session.query(UserCommunicationPreferences) \
            .filter(UserCommunicationPreferences.communication_uuid == communication_uuid)
        if user_uuid:
            user_pref_query = user_pref_query.filter(UserCommunicationPreferences.user_uuid == user_uuid)

        for pref in user_pref_query.all():
            count += 1
            if pref.communication.communication_default_setting == pref.communication_setting:
                session.delete(pref)
            else:
                ucp = UserCommunicationPreferences()
                ucp.communication_uuid = new_communication_uuid
                ucp.user_uuid = pref.user_uuid
                ucp.communication_setting = pref.communication_setting
                session.merge(ucp)
                us = UserState()
                us.user_uuid = pref.user_uuid
                us.requires_iterable_sync = True
                session.merge(us)
            if not count % 10000:
                session.flush()
        session.flush()

    @staticmethod
    def find_migratable_preferences(user_uuid, session, communication_uuid=None):
        """
        Activity settings are exploded to all entries in Comments, Replies, and Likes
        Paging settings are copied to the new id
        :param session:
        :param user_uuid: The user_uuid to update the preference for.
        :return:
        """

        new_activity_email_uuids = []
        new_activity_push_uuids = []
        old_activity_email_uuid = None
        old_activity_push_uuid = None
        new_paging_email_uuid = None
        new_paging_push_uuid = None
        old_paging_email_uuid = None
        old_paging_push_uuid = None

        if communication_uuid:
            existing_setting = session.query(CommunicationSettings) \
                .filter(CommunicationSettings.communication_uuid == communication_uuid).one()
            if existing_setting.communication_group.communication_group_name != 'Activity' or \
                    existing_setting.communication_group.communication_group_name != 'Paging':
                logger.debug("Not a migratable setting")
                return

        group_query_base = session.query(CommunicationGroup) \
            .filter(CommunicationGroup.communication_group_type == CommunicationTypes.ACTIVITY)

        find_old_activity_group = group_query_base.filter(CommunicationGroup.communication_group_name == 'Activity')
        find_old_paging_group = group_query_base.filter(CommunicationGroup.communication_group_name == 'Paging')

        find_new_activity_group = group_query_base \
            .filter(CommunicationGroup.communication_group_category ==
                    ActivityNotificationCategories.CommentsRepliesLikes,
                    CommunicationGroup.communication_group_name == 'Comments on your cases')

        find_new_paging_group = group_query_base \
            .filter(CommunicationGroup.communication_group_category == ActivityNotificationCategories.Paging)

        for old_activity in find_old_activity_group.all():
            if old_activity.communication_group:
                for setting in old_activity.communication_group:
                    if setting.communication_method == CommunicationMethods.EMAIL:
                        old_activity_email_uuid = setting.communication_uuid
                    if setting.communication_method == CommunicationMethods.PUSH:
                        old_activity_push_uuid = setting.communication_uuid

        for new_activity in find_new_activity_group.all():
            if new_activity.communication_group:
                for setting in new_activity.communication_group:
                    if setting.communication_method == CommunicationMethods.EMAIL:
                        new_activity_email_uuids.append(setting.communication_uuid)
                    if setting.communication_method == CommunicationMethods.PUSH:
                        new_activity_push_uuids.append(setting.communication_uuid)

        for a in new_activity_email_uuids:
            UserCommunicationPreferences.migrate_user_preferences(communication_uuid=old_activity_email_uuid,
                                                                  new_communication_uuid=a,
                                                                  user_uuid=user_uuid,
                                                                  session=session)

        for a in new_activity_push_uuids:
            UserCommunicationPreferences.migrate_user_preferences(communication_uuid=old_activity_push_uuid,
                                                                  new_communication_uuid=a,
                                                                  user_uuid=user_uuid,
                                                                  session=session)
        for old_paging in find_old_paging_group.all():
            if old_paging.communication_group:
                for setting in old_paging.communication_group:
                    if setting.communication_method == CommunicationMethods.EMAIL:
                        old_paging_email_uuid = setting.communication_uuid

                    if setting.communication_method == CommunicationMethods.PUSH:
                        old_paging_push_uuid = setting.communication_uuid

        for new_paging in find_new_paging_group.all():
            if new_paging.communication_group:
                for setting in new_paging.communication_group:
                    if setting.communication_method == CommunicationMethods.EMAIL:
                        new_paging_email_uuid = setting.communication_uuid
                    if setting.communication_method == CommunicationMethods.PUSH:
                        new_paging_push_uuid = setting.communication_uuid

        UserCommunicationPreferences.migrate_user_preferences(communication_uuid=old_paging_email_uuid,
                                                              new_communication_uuid=new_paging_email_uuid,
                                                              user_uuid=user_uuid,
                                                              session=session)
        UserCommunicationPreferences.migrate_user_preferences(communication_uuid=old_paging_push_uuid,
                                                              new_communication_uuid=new_paging_push_uuid,
                                                              user_uuid=user_uuid,
                                                              session=session)
        session.commit()

    @staticmethod
    def _get_defaults(session):
        up = UserPreferencesModel()
        for group in CommunicationTypes:
            if group == CommunicationTypes.CHANNEL:
                continue
            gr_list = []
            for g in session.query(CommunicationGroup) \
                    .filter(CommunicationGroup.communication_group_type == group,
                            CommunicationGroup.communication_group_category.is_(None)) \
                    .all():
                gr_list.append(CommunicationSettingsModel.from_orm(g))
            setattr(up, group.value, gr_list)
        return up.dict()

    @staticmethod
    def _get_defaults_v2(session):
        up = UserPreferencesModelV2()
        activites = ActivityCategories()
        for group in CommunicationTypes:
            if group == CommunicationTypes.CHANNEL:
                continue
            gr_list = []
            if group == CommunicationTypes.ACTIVITY:
                activity_groups = session.query(CommunicationGroup) \
                    .filter(CommunicationGroup.communication_group_type == group,
                            CommunicationGroup.communication_group_category.isnot(None)) \
                    .all()

                for a in activity_groups:
                    if a.communication_group_category == ActivityNotificationCategories.CommentsRepliesLikes:
                        gr_list.append(a)
                activites.commentRepliesLikes = ActivityNotificationCategorycomments(preferences=gr_list)
                gr_list = []

                for a in activity_groups:
                    if a.communication_group_category == ActivityNotificationCategories.Paging:
                        gr_list.append(a)
                activites.paging = ActivityNotificationCategorypaging(preferences=gr_list)
                gr_list = []

                for a in activity_groups:
                    if a.communication_group_category == ActivityNotificationCategories.Follow:
                        gr_list.append(a)
                activites.follow = ActivityNotificationCategoryfollow(preferences=gr_list)
                gr_list = []

                for a in activity_groups:
                    if a.communication_group_category == ActivityNotificationCategories.SavedCases:
                        gr_list.append(a)
                activites.savedCases = ActivityNotificationCategorysavedCases(preferences=gr_list)
                gr_list = []

                for a in activity_groups:
                    if a.communication_group_category == ActivityNotificationCategories.WeeklyDigest:
                        gr_list.append(a)
                activites.weeklyDigest = ActivityNotificationCategoryweeklyDigest(preferences=gr_list)
                up.activity = activites
            else:
                for g in session.query(CommunicationGroup) \
                        .filter(CommunicationGroup.communication_group_type == group) \
                        .all():
                    gr_list.append(CommunicationSettingsModel.from_orm(g))
                setattr(up, group.value, gr_list)
        return up

    @staticmethod
    def get_default_preferences_v2(session):
        return UserCommunicationPreferences._get_defaults_v2(session=session).dict()

    @staticmethod
    def set_user_preference(user_uuid, communication_uuid, communication_setting, session):
        """
        Set a user's communication preference for this communication_uuid. Once set, future default changes will not
        affect it.

        On subscription, if there is a communication_channel associated with the preference, the user is resubscribed
        to it
        :param user_uuid:
        :param communication_uuid:
        :param communication_setting: boolean value to enable/disable this communication type
        :param session:
        :return:
        """
        existing = session.query(UserCommunicationPreferences).get((user_uuid, communication_uuid))
        if existing:
            existing.communication_setting = communication_setting
            session.add(existing)
        elif session.query(CommunicationSettings.communication_default_setting) \
                .filter(CommunicationSettings.communication_uuid == communication_uuid,
                        CommunicationSettings.communication_default_setting != communication_setting) \
                .one_or_none():
            pref = UserCommunicationPreferences()
            pref.user_uuid = user_uuid
            pref.communication_uuid = communication_uuid
            pref.communication_setting = communication_setting
            session.add(pref)

        # Resubscribe to associated channel, if needed
        if communication_setting:
            cs = session.query(CommunicationSettings).get(communication_uuid)
            if cs and cs.communication_channel_uuid:
                UserChannelPreferences.set_user_preference(user_uuid=user_uuid,
                                                           channel_uuid=cs.communication_channel_uuid,
                                                           channel_setting=True,
                                                           session=session)

        UserCommunicationPreferences.find_migratable_preferences(user_uuid=user_uuid,
                                                                 communication_uuid=communication_uuid,
                                                                 session=session)
        session.flush()

    @staticmethod
    def get_user_preference(user_uuid, session, communication_uuid=None) -> Iterable[UserCommunicationPreferencesModel]:
        """
        If no communication uuid is passed, a list of preferences that have been set by the user is returned.
        This does _not_ return default preferences
        :param user_uuid: User uuid to get the user preference for
        :param session:
        :param communication_uuid: Optional - Returns the preference model for this uuid if set.
        :return: Iterable of UserCommunicationPreferencesModels or empty if the user has not set anything
        """
        if communication_uuid:
            existing = session.query(UserCommunicationPreferences).get((user_uuid, communication_uuid))
            if existing:
                yield UserCommunicationPreferencesModel.from_orm(existing)
        else:
            for pref in session.query(UserCommunicationPreferences) \
                    .filter(UserCommunicationPreferences.user_uuid == user_uuid) \
                    .all():
                if pref:
                    yield UserCommunicationPreferencesModel.from_orm(pref)

    @staticmethod
    def reset_user_preferences(user_uuid, session):
        session.query(UserCommunicationPreferences).filter(UserCommunicationPreferences.user_uuid == user_uuid).delete()

    @staticmethod
    def get_merged_user_preferences(user_uuid, session):
        defaults = UserCommunicationPreferences._get_defaults(session=session)
        for user_pref in UserCommunicationPreferences.get_user_preference(user_uuid=user_uuid, session=session):

            for k in defaults.keys():
                for comm_group in defaults.get(k):
                    for item in comm_group.get("communicationGroupItems"):
                        if user_pref.communication.communicationUuid == item.get('communicationUuid'):
                            item['communicationSetting'] = user_pref.userCommunicationSetting
        return defaults

    @staticmethod
    def get_merged_user_preferences_v2(user_uuid, session):
        defaults = UserCommunicationPreferences._get_defaults_v2(session=session)
        defaults = defaults.dict()
        for user_pref in UserCommunicationPreferences.get_user_preference(user_uuid=user_uuid, session=session):
            replace_dict_key_value(replace_key="communicationSetting",
                                   replace_value=user_pref.userCommunicationSetting,
                                   search_value=user_pref.communication.communicationUuid,
                                   search_dict=defaults)
        return defaults

    @staticmethod
    def get_preference_uuid_settings(session, user_uuid):
        """
        Given a user_uuid, returns an iterator containing a tuple of
        (<communication_uuid>, <iterable_message_type>, setting). The settings are
        merged with the default settings, so all valid settings are returned. Valid settings are filtered by the
        enabled value being set to true and the iterable message type being greater than 0.

        :param session:
        :param user_uuid:
        :return:
        """
        user_settings = select(UserCommunicationPreferences.communication_uuid.label("user_communication_uuid"),
                               UserCommunicationPreferences.communication_setting.label("user_communication_setting")) \
            .filter(UserCommunicationPreferences.user_uuid == user_uuid).cte("user_settings")
        q = session.query(func.coalesce(user_settings.c.user_communication_setting,
                                        CommunicationSettings.communication_default_setting),
                          CommunicationSettings.communication_iterable_message_type,
                          CommunicationSettings.communication_uuid) \
            .join(user_settings,
                  user_settings.c.user_communication_uuid == CommunicationSettings.communication_uuid, full=True) \
            .filter(CommunicationSettings.communication_enabled.is_(True),
                    CommunicationSettings.communication_iterable_message_type > 0)

        for c in q.all():
            yield str(c[2]), c[1], c[0]

    @staticmethod
    def initialize_user_communication_preferences(user_uuid, session):
        """
        Initializes the UserCommunicationPreferences for a user_uuid

        Creates a UserCommunicationPreference for any specialty defaults that differ from the CommunicationSetting
        default
        """

        primary_specialty = UserSpecialtyTreeV2.get_primary(user_uuid=user_uuid, session=session)
        if not primary_specialty:
            return
        specialty_setting_query = session.query(CommunicationSettings) \
            .join(CommunicationGroup,
                  CommunicationGroup.communication_group_uuid == CommunicationSettings.communication_group_uuid) \
            .join(SpecialtyCommunicationSettings,
                  SpecialtyCommunicationSettings.communication_uuid == CommunicationSettings.communication_uuid) \
            .filter(CommunicationSettings.communication_enabled.is_(True),
                    CommunicationGroup.communication_group_type == CommunicationTypes.CONTENT,
                    SpecialtyCommunicationSettings.tree_uuid == primary_specialty.treeUuid)
        for communication in specialty_setting_query.all():
            if communication.specialty_defaults:
                for specialty_setting in communication.specialty_defaults:
                    if str(specialty_setting.tree_uuid) != primary_specialty.treeUuid:
                        continue
                    if communication.communication_default_setting != specialty_setting.communication_default_setting:
                        UserCommunicationPreferences.set_user_preference(
                            user_uuid=user_uuid,
                            communication_uuid=communication.communication_uuid,
                            communication_setting=specialty_setting.communication_default_setting,
                            session=session)


class UserChannelPreferences(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "u_user_communication_channel_preferences"
    user_uuid = Column(UUID(as_uuid=True), ForeignKey(User.user_uuid), primary_key=True)
    communication_channel_uuid = Column(UUID(as_uuid=True),
                                        ForeignKey(CommunicationChannel.communication_channel_uuid),
                                        primary_key=True)
    communication_setting = Column(Boolean, nullable=False)
    communication_channel = relationship('CommunicationChannel')

    @staticmethod
    def get_preference_uuid_settings(session, user_uuid):
        """
        Given a user_uuid, returns an iterator containing a tuple of
        (<communication_channel_uuid>, <channel_id>, <setting>). The settings are
        merged with the default settings, so all valid settings are returned. Valid settings are filtered by the
        enabled value being set to true and the iterable message type being greater than 0.

        :param session:
        :param user_uuid:
        :return:
        """
        user_settings = select(UserChannelPreferences.communication_channel_uuid.label("user_channel_uuid"),
                               UserChannelPreferences.communication_setting.label("user_communication_setting")) \
            .filter(UserChannelPreferences.user_uuid == user_uuid).cte("user_settings")
        q = session.query(func.coalesce(user_settings.c.user_communication_setting,
                                        CommunicationChannel.communication_default_setting),
                          CommunicationChannel.communication_channel_id,
                          CommunicationChannel.communication_channel_uuid) \
            .join(user_settings, user_settings.c.user_channel_uuid == CommunicationChannel.communication_channel_uuid,
                  full=True) \
            .filter(CommunicationChannel.communication_channel_id > 0)

        for c in q.all():
            yield str(c[2]), c[1], c[0]

    @staticmethod
    def set_user_preference(user_uuid,
                            channel_uuid,
                            channel_setting,
                            session):
        """
        Subscribes or unsubscribes a user to a channel.
        :param user_uuid:
        :param channel_uuid:
        :param channel_setting:
        :param session:
        :return:
        """

        c = session.query(CommunicationChannel).get(channel_uuid)
        if not c:
            raise CommunicationChannelNotFound(communication_channel_uuid=channel_uuid,
                                               msg=f"Invalid uuid: {channel_uuid}")

        User.get_user_by_uuid(user_uuid=user_uuid, raise_exception=True, session=session)

        existing = session.query(UserChannelPreferences).get((user_uuid, channel_uuid))
        if existing:
            existing.communication_setting = channel_setting
            session.add(existing)
        elif c.communication_default_setting != channel_setting:
            ucp = UserChannelPreferences()
            ucp.user_uuid = user_uuid
            ucp.communication_channel_uuid = channel_uuid
            ucp.communication_setting = channel_setting
            session.add(ucp)

        session.flush()
