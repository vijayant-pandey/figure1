import logging
from uuid import uuid4, UUID
from datetime import datetime
from figure1.common.models.db import UserProfile
from figure1.common.helpers import UserDocument
from figure1.common.types import FirebaseAction, FirebaseFeedID
from figure1.common.activities.user_profile_activities import update_all_activities_task

logger = logging.getLogger(__name__)
fb_id = FirebaseFeedID()


class FirebaseUsersProfileDB:
    def __init__(self, path, user, columns=None):
        self._path = path
        self._columns = columns
        self._user = user

    def set(self):
        return {
            "path": self._path,
            "action": FirebaseAction.SET,
            "data": self._user
        }

    @property
    def delete(self):
        return {
            "path": self._path,
            "action": FirebaseAction.DELETE
        }

    @staticmethod
    def sync(firebase_db, user_uuid, action, columns=None, session=None):
        if isinstance(user_uuid, UUID):
            user_uuid = str(user_uuid)
        try:
            UUID(user_uuid)
        except (TypeError, ValueError):
            logger.error("Invalid user uuid - %s", user_uuid)
            return StopIteration
        user_uuid = str(user_uuid)
        public_profile = UserDocument.get_public_profile(user_uuid=user_uuid, session=session)
        if not public_profile:
            logger.warning(f"Could not find user to sync, uuid={user_uuid}")
            return StopIteration

        path = firebase_db.collection('usersProfileDB').document(user_uuid).path
        sync_object = FirebaseUsersProfileDB(path=path, user=public_profile, columns=columns)

        if action is FirebaseAction.SET:
            p = session.query(UserProfile).get(user_uuid)
            if p:
                p.synced_at = datetime.utcnow()
                session.add(p)
            yield sync_object.set()
            FirebaseUsersProfileDB.update_user_activties(user_uuid=user_uuid)
        elif action is FirebaseAction.DELETE:
            yield sync_object.delete
        else:
            logger.error(f"Unsupported action for row={user_uuid}, action={action}")
            return StopIteration

    @staticmethod
    def update_user_activties(user_uuid):
        logger.info("Updating user activities")
        update_all_activities_task.delay(user_uuid=user_uuid)
