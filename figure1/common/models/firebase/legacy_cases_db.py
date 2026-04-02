import logging

from figure1.core import managed_session
from figure1.common.models.db import LegacyCase, TaggingAssignment, TaggingState
from figure1.common.types import FirebaseAction


class FirebaseCasesDB:
    def __init__(self, path, case=None, columns=None):
        self._path = path
        self._case = case
        self._columns = columns

    @property
    def set(self):
        updates = self._case.as_dict()
        updates['share_link'] = f"figure1pro://cases/{updates.get('caseUuid')}"
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
    def sync(firebase_db, case_uuid, action, columns=None, session=None):
        logger = logging.getLogger(__name__)

        c = session.query(LegacyCase) \
            .filter(LegacyCase.case_uuid == case_uuid) \
            .one_or_none()
        if not c:
            logger.warning(f"Could not find legacyCase to sync, uuid={case_uuid}")
            return None

        path = firebase_db.collection('casesDB').document(str(case_uuid)).path
        sync_object = FirebaseCasesDB(path=path, case=c, columns=columns)

        if action is FirebaseAction.SET:
            ops = sync_object.set
        elif action is FirebaseAction.DELETE:
            ops = sync_object.delete
        else:
            logger.error(f"Unsupported action for row={case_uuid}, action={action}")
            return []

        for t in session.query(TaggingAssignment) \
                .filter(TaggingAssignment.case_uuid == case_uuid,
                        TaggingAssignment.deleted_at.is_(None)) \
                .all():
            for assignment_op in FirebaseClientAssignmentDB.sync(firebase_db,
                                                                 t.assignment_uuid,
                                                                 action,
                                                                 columns,
                                                                 session=session):
                ops.append(assignment_op)

        return ops


class FirebaseClientAssignmentDB:
    def __init__(self, path, case, columns=None):
        self._path = path
        self._case = case
        self._columns = columns

    @property
    def set(self):
        updates = self._case.as_dict()
        updates['reviewed'] = self._case.state.value >= TaggingState.PENDING_APPROVAL.value
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
    @managed_session
    def sync(firebase_db, assignment_uuid, action, columns=None, session=None):
        logger = logging.getLogger(__name__)

        a = session.query(TaggingAssignment) \
            .filter(TaggingAssignment.assignment_uuid == assignment_uuid) \
            .one_or_none()
        if not a:
            logger.warning(f"Could not find caseAssignment to sync, uuid={assignment_uuid}")
            return None

        c = session.query(LegacyCase) \
            .filter(LegacyCase.case_uuid == a.case_uuid) \
            .one_or_none()
        if not c:
            logger.warning(f"Could not find case from caseAssignment to sync, uuid={a.case_uuid}")
            return None

        path = firebase_db.collection('clientAssignmentDB') \
            .document(a.reviewer_uid) \
            .collection('assignedCases') \
            .document(str(a.case_uuid)) \
            .path
        sync_object = FirebaseClientAssignmentDB(path=path, case=c, columns=columns)

        if action is FirebaseAction.SET:
            return sync_object.set
        elif action is FirebaseAction.DELETE:
            return sync_object.delete
        else:
            logger.error(f"Unsupported action for row={assignment_uuid}, action={action}")
            return []
