from figure1.common.models.db import UserCommunicationPreferences, \
    CommunicationSettings, \
    SpecialtyCommunicationSettings, \
    UserSpecialtyTreeV2, CommunicationGroup
from figure1.common.types import CommunicationTypes
from figure1.common.iterable.domain import get_subscription_preferences


def test_preference_defaults(test_user, load_db, generate_default_preferences):
    """
    User is subscribed by default to one differential and one other content type that is not a differential. There
    should be two preferences set by this.

    :param test_user:
    :param load_db:
    :param generate_default_preferences:
    :return:
    """
    session = load_db
    q = session.query(CommunicationSettings) \
        .join(CommunicationGroup,
              CommunicationGroup.communication_group_uuid == CommunicationSettings.communication_group_uuid) \
        .filter(CommunicationSettings.communication_iterable_message_type != 0,
                CommunicationGroup.communication_group_type == CommunicationTypes.CONTENT,
                CommunicationGroup.communication_group_name != 'Your Differentials').first()
    d = UserCommunicationPreferences.get_merged_user_preferences(user_uuid=test_user.get('userUuid'), session=session)
    UserCommunicationPreferences.set_user_preference(user_uuid=test_user.get('userUuid'),
                                                     communication_uuid=str(q.communication_uuid),
                                                     communication_setting=False,
                                                     session=session)
    session.commit()
    p2 = get_subscription_preferences(user_uuid=test_user.get('userUuid'), session=session)
    assert q.communication_iterable_message_type in p2['unsubscribed_message_types']

    UserCommunicationPreferences.initialize_user_communication_preferences(user_uuid=test_user.get('userUuid'),
                                                                           session=session)
    session.commit()

    count_q = session.query(UserCommunicationPreferences) \
        .filter(UserCommunicationPreferences.user_uuid == test_user.get('userUuid'))
    assert count_q.count() == 2
