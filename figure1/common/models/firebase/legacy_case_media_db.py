import logging

from figure1.core import managed_session
from figure1.common.models.db import Media
from figure1.common.types import FirebaseAction


class FirebaseCaseMediaDB:
    def __init__(self, path, media=None, columns=None):
        self._path = path
        self._media = media
        self._columns = columns

    @property
    def set(self):
        updates = self._media.as_dict()
        if self._columns:
            updates = dict(filter(lambda x: x[0] in self._columns, updates.items()))

        return [{
            "path": self._path,
            "action": FirebaseAction.SET,
            "data": updates
        }]

    @property
    def delete(self):
        return [{
            "path": self._path,
            "action": FirebaseAction.DELETE
        }]

    @staticmethod
    def sync(firebase_db, media_uuid, action, columns=None, session=None):
        logger = logging.getLogger(__name__)
        path = firebase_db.collection('caseMediaDB').document(str(media_uuid)).path

        if action is FirebaseAction.DELETE:
            return FirebaseCaseMediaDB(path=path).delete

        m = session.query(Media) \
            .filter(Media.media_uuid == media_uuid) \
            .one_or_none()
        if not m:
            logger.warning(f"Could not find media to sync, uuid={media_uuid}")
            return None

        if action is FirebaseAction.SET:
            return FirebaseCaseMediaDB(path=path, media=m, columns=columns).set
        else:
            logger.error(f"Unsupported action for row={media_uuid}, action={action}")
            return []
