import logging

from figure1.common.models.db import CaseCMEUserAnswer
from figure1.common.models.db import User
from figure1.common.types.cme import CMEUserAnswerModel
from figure1.core import FirebaseTaskBase, celery_app

logger = logging.getLogger('figure1.tools.casecme')


@celery_app.task(bind=True,
                 base=FirebaseTaskBase,
                 name='figure1.backend.sync_case_cme_answers')
def sync_case_cme_answers(self: FirebaseTaskBase):
    """
    Starts a task to sync all case cme answers to firestore
    :return: None
    """

    batch = self.fs_client.batch()
    firebase_write_count = 0

    for a in self.session.query(CaseCMEUserAnswer).all():
        u = User.get_user_by_uuid(user_uuid=a.user_uuid, session=self.session, raise_exception=True)
        if not u:
            continue
        model = CMEUserAnswerModel.from_orm(a)
        model.userUid = u.user_uid
        model.firestore_batch_write(batch)
        firebase_write_count += 1
        if firebase_write_count % 500 == 0:
            logger.info("Committing firestore batch, synced %s", firebase_write_count)
            batch.commit()

    batch.commit()
    logger.info("Completed, synced %s", firebase_write_count)
