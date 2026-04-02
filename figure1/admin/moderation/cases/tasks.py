from figure1.core import FirebaseTaskBase, celery_app
from figure1.common.models.firebase.user_drafts_db import FirebaseUserDraftsDB
from figure1.common.types import CaseState


@celery_app.task(bind=True, base=FirebaseTaskBase, name='figure1.frontend.sync_case_rejected_state')
def sync_case_rejected_state(self, user_uid, case):
    draft_uid = FirebaseUserDraftsDB.get_draft_uid(fs_client=self.fs_client,
                                                   user_uid=user_uid,
                                                   case_uuid=case.case_uuid)

    for update in FirebaseUserDraftsDB.sync_draft(firebase_db=self.fs_client,
                                                  user_uid=user_uid,
                                                  draft_uid=draft_uid,
                                                  case_uuid=case.case_uuid,
                                                  state=CaseState.REJECTED,
                                                  rejection_reason=case.rejection_reason):
        doc = self.fs_client.document(update.get('path'))
        self.batch.set(doc, update.get('data'), merge=True)

    self.batch.commit()
