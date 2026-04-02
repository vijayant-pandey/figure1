from figure1.common.models.firebase import FirebaseCollectionManager
from figure1.common.models.db import UserCommunicationPreferences, \
    User

fb = FirebaseCollectionManager()


def _update_firestore_document(user_uid, preferences, preference_type, reset=False, version=1):
    """
    Updates preferences in firestore on update.
    :param user_uid:
    :param preferences: User preferences object
    :param reset: boolean - Set this to force overwrite the target preferences document
    :return: None
    """

    if version == 1:
        fb.set_fs_client(documents=[user_uid, preference_type], collections=['usersDB', 'userPreferences'])
    elif version == 2:
        fb.set_fs_client(documents=[user_uid, preference_type], collections=['usersDB', 'userPreferencesV2'])
    else:
        return
    if reset:
        fb.set({preference_type: preferences}, merge=False)
    else:
        fb.set({preference_type: preferences}, merge=True)


def sync_user_communication_preferences(user_uuid, session):
    user = User.get_user_by_uuid(user_uuid=user_uuid, session=session, raise_exception=True)
    updated_prefs = UserCommunicationPreferences.get_merged_user_preferences(user_uuid=user.user_uuid, session=session)
    for preference_type in updated_prefs.keys():
        _update_firestore_document(user_uid=user.user_uid,
                                   preferences=updated_prefs.get(preference_type),
                                   preference_type=preference_type)


def sync_user_communication_preferences_v2(user_uuid, session):
    user = User.get_user_by_uuid(user_uuid=user_uuid, session=session, raise_exception=True)
    updated_prefs = UserCommunicationPreferences.get_merged_user_preferences_v2(user_uuid=user_uuid, session=session)
    for preference_type in updated_prefs.keys():
        _update_firestore_document(user_uid=user.user_uid,
                                   preferences=updated_prefs.get(preference_type),
                                   preference_type=preference_type,
                                   version=2)
