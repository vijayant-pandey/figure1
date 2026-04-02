import logging

from figure1.core import managed_session
from figure1.common.models.db import ReviewMeshTerms
from figure1.common.types import FirebaseAction


class FirebaseReviewMeshTermsDB:
    def __init__(self, path, mesh_terms, columns=None):
        self._path = path
        self._mesh_terms = mesh_terms
        self._columns = columns

    @property
    def set(self):
        updates = self._mesh_terms.as_dict()
        if self._columns:
            updates = dict(filter(lambda x: x[0] in self._columns, updates.items()))
        return [{
            "path": self._path,
            "action": FirebaseAction.SET,
            "data": {"data": [updates]}
        }]

    @property
    def delete(self):
        return [{
            "path": self._path,
            "action": FirebaseAction.DELETE
        }]

    @staticmethod
    def sync(firebase_db, mesh_review_uuid, action, columns=None, session=None):
        logger = logging.getLogger(__name__)

        m = session.query(ReviewMeshTerms) \
            .filter(ReviewMeshTerms.mesh_review_uuid == mesh_review_uuid) \
            .one_or_none()
        if not m:
            logger.warning(f"Could not find reviewMeshTerms to sync, uuid={mesh_review_uuid}")
            return None

        path = firebase_db.collection('reviewMeshTermsDB').document(str(m.case_uuid)).path
        sync_object = FirebaseReviewMeshTermsDB(path=path, mesh_terms=m, columns=columns)

        if action is FirebaseAction.SET:
            return sync_object.set
        elif action is FirebaseAction.DELETE:
            return sync_object.delete
        else:
            logger.error(f"Unsupported action for row={mesh_review_uuid}, action={action}")
            return []
