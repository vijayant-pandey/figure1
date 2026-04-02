import logging

from figure1.common.models.db import User, UserDeviceNotificationToken
from figure1.common.types import FirebaseAction


class FirebaseUserDeviceNotificationTokensDB:
    def __init__(self, path, user=None, user_device_notifications=None, columns=None):
        self._path = path
        self._user_device_notifications = user_device_notifications
        self._user = user

    @property
    def set(self):
        updates = [
            user_device_notification.as_dict()
            for user_device_notification in self._user_device_notifications
        ]

        logging.info(f"Updates for user: {self._user['userUid']} {self._user['userUuid']} {self._user['email']}")

        return [{
            "path": self._path,
            "action": FirebaseAction.SET,
            "data": {
                "userUuid": self._user['userUuid'],
                "userUid": self._user['userUid'],
                "email": self._user['email'],
                "fcmTokens": updates
            }
        }]

    @property
    def delete(self):
        return [{
            "path": self._path,
            "action": FirebaseAction.DELETE
        }]

    @staticmethod
    def sync(firebase_db, uuid, action, session=None, columns=None):
        logger = logging.getLogger(__name__)
        user = User.get_user_by_uuid(user_uuid=uuid, session=session, raise_exception=True)
        all_user_tokens = UserDeviceNotificationToken.list_all(user_uuid=uuid, session=session)

        path = firebase_db.collection('tokensDB').document(user.user_uid).path
        sync_object = FirebaseUserDeviceNotificationTokensDB(
            path=path,
            user=user.as_dict(),
            user_device_notifications=all_user_tokens
        )

        if action is FirebaseAction.SET:
            ops = sync_object.set
        elif action is FirebaseAction.DELETE:
            ops = sync_object.delete
        else:
            logger.error(f"Unsupported action for user={uuid}, action={action}")
            return []

        return ops
