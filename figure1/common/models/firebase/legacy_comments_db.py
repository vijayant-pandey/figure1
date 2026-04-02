import logging

from figure1.core import managed_session
from figure1.common.models.db import LegacyComment
from figure1.common.types import FirebaseAction


class FirebaseCommentsDB:
    def __init__(self, path, comment=None, columns=None):
        self._path = path
        self._comment = comment
        self._columns = columns

    @property
    def set(self):
        updates = self._comment.as_dict()
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
    def sync(firebase_db, comment_uuid, action, columns=None, session=None):
        logger = logging.getLogger(__name__)
        path = firebase_db.collection('commentsDB').document(str(comment_uuid)).path

        if action is FirebaseAction.DELETE:
            return FirebaseCommentsDB(path=path).delete

        c = session.query(LegacyComment) \
            .filter(LegacyComment.comment_uuid == comment_uuid) \
            .one_or_none()
        if not c:
            logger.warning(f"Could not find legacyComment to sync, uuid={comment_uuid}")
            return None

        if action is FirebaseAction.SET:
            return FirebaseCommentsDB(path=path, comment=c, columns=columns).set
        else:
            logger.error(f"Unsupported action for row={comment_uuid}, action={action}")
            return []
