import logging

from sqlalchemy import func

from figure1.common.models.db import Case
from figure1.common.helpers import CaseDetail
from figure1.common.types import CaseState, FirebaseAction


class ModerationDBCases:
    firebase_collection = 'moderationDB'
    case_document = 'caseModeration'
    queue_collection = 'queue'
    suggested_edit_collection = 'suggestedEdits'
    flagged_collection = 'flagged'
    reported_collection = 'reported'
    rejected_collection = 'rejected'
    all_collection = 'all'

    def __init__(self, paths):
        self._paths = paths

    # SET action sets the case on the collection matching its current state, and deletes from others states
    def set(self, case_data):
        return [{
            "path": path.get('path'),
            "action": path.get('action'),
            "data": case_data
        } for path in self._paths]

    # DELETE action deletes the case from collections for all case states
    def delete(self):
        return [{
            "path": path.get('path'),
            "action": FirebaseAction.DELETE
        } for path in self._paths]

    @staticmethod
    def _get_paths_and_actions(firebase_db, case):
        doc = firebase_db.collection(ModerationDBCases.firebase_collection).document(ModerationDBCases.case_document)
        state = case.get('caseState')
        uuid = case.get('caseUuid')
        return [
            {
                'path': doc.collection(ModerationDBCases.queue_collection).document(uuid).path,
                'action': FirebaseAction.SET if state == CaseState.PENDING_APPROVAL.name else FirebaseAction.DELETE,
            },
            {
                'path': doc.collection(ModerationDBCases.flagged_collection).document(uuid).path,
                'action': FirebaseAction.SET if state == CaseState.FLAGGED.name else FirebaseAction.DELETE,
            },
            {
                'path': doc.collection(ModerationDBCases.reported_collection).document(uuid).path,
                'action': FirebaseAction.SET if state == CaseState.REPORTED.name else FirebaseAction.DELETE,
            },
            {
                'path': doc.collection(ModerationDBCases.rejected_collection).document(uuid).path,
                'action': FirebaseAction.SET if state == CaseState.REJECTED.name else FirebaseAction.DELETE,
            },
            {
                'path': doc.collection(ModerationDBCases.suggested_edit_collection).document(uuid).path,
                'action': FirebaseAction.SET if state == CaseState.EDIT_SUGGESTED.name else FirebaseAction.DELETE,
            },
            {
                'path': doc.collection(ModerationDBCases.all_collection).document(uuid).path,
                'action': FirebaseAction.SET,
            },
        ]

    @staticmethod
    def _set_metadata(firebase_db, session):
        counts = {'all': 0}
        for r in session.query(Case.state, func.count(Case.state)) \
                .filter(Case.state != CaseState.APPROVED, Case.state != CaseState.DRAFT) \
                .group_by(Case.state) \
                .all():
            counts[r[0]] = r[1]
            counts['all'] += r[1]

        path = firebase_db \
            .collection(ModerationDBCases.firebase_collection) \
            .document(ModerationDBCases.case_document).path

        return {
            "path": path,
            "action": FirebaseAction.SET,
            "data": {
                "count": {
                    'all': counts.get('all', 0),
                    'queue': counts.get(CaseState.PENDING_APPROVAL, 0),
                    'flagged': counts.get(CaseState.FLAGGED, 0),
                    'reported': counts.get(CaseState.REPORTED, 0),
                    'rejected': counts.get(CaseState.REJECTED, 0),
                    'suggested_edits': counts.get(CaseState.EDIT_SUGGESTED, 0),
                }
            }
        }

    @staticmethod
    def sync(firebase_db, case_uuid, action, session, columns=None):
        logger = logging.getLogger(__name__)

        case = CaseDetail.moderation_case_detail(case_uuid=case_uuid, session=session)
        if not case:
            logger.error(f"No case found for case_uuid {case_uuid}")
            return []

        paths = ModerationDBCases._get_paths_and_actions(firebase_db=firebase_db, case=case)
        sync_object = ModerationDBCases(paths=paths)

        firebase_ops = [ModerationDBCases._set_metadata(firebase_db, session)]
        if action is FirebaseAction.SET:
            firebase_ops.extend(sync_object.set(case_data=case))
        if action is FirebaseAction.DELETE:
            firebase_ops.extend(sync_object.delete())
        return firebase_ops
