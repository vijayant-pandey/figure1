import logging
from datetime import datetime, timezone, timedelta

from celery import group
from google.api_core.exceptions import ServiceUnavailable
from sqlalchemy import nullsfirst, or_

from figure1.common.models.db import Case
from figure1.common.models.firebase import CaseDetailV2
from figure1.configuration import app_settings
from figure1.exceptions import CaseSyncThrottled
from figure1.core import FirebaseTaskBase, celery_app, TaskBase
from figure1.common.firebase.utils import delete_collection_batch
from figure1.common.types import FirebaseAction, CaseState

logger = logging.getLogger('figure1.common.firebase')


def _filter_arguments_by_model_name(firebasemodel_name, **kwargs):
    if firebasemodel_name != CaseDetailV2.__name__:
        kwargs.pop('case_detail_only', None)

    return kwargs


@celery_app.task(bind=True,
                 base=FirebaseTaskBase,
                 autoretry_for=(ServiceUnavailable, CaseSyncThrottled),
                 retry_backoff=30,
                 name='figure1.frontend.firebase_sync')
def do_firebase_sync(self, firebasemodel, uuid, action=FirebaseAction.SET,
                     columns=None, merge=True, case_detail_only=False):
    logger.debug("Running sync for model %s with uuid %s and action %s", firebasemodel, uuid, action)
    cls = self.load_class(firebasemodel=firebasemodel)
    count = 0
    batch = self.fs_client.batch()

    filtered_args = _filter_arguments_by_model_name(firebasemodel, action=action, columns=columns,
                                                    session=self.session, case_detail_only=case_detail_only)

    for update in cls.sync(self.fs_client, uuid, **filtered_args):
        if update is None:
            continue

        count += 1

        if update.get('action') is FirebaseAction.DELETE:
            doc = self.fs_client.document(update.get('path'))
            batch.delete(doc)
        elif update.get('action') is FirebaseAction.SET:
            doc = self.fs_client.document(update.get('path'))
            try:
                batch.set(doc, update.get('data'), merge=merge)
            except TypeError as te:
                logging.critical("Data %s raised an error", update.get('data'))
                raise
        elif update.get('action') is FirebaseAction.DELETE_COLLECTION:
            collection_path = update.get('path')
            count = delete_collection_batch(collection_path=collection_path,
                                            batch=batch,
                                            starting_batch_count=count)
        else:
            return {'error': f"Unrecognized action={update.get('action')}, uuid={uuid}, model={firebasemodel}"}
        if count >= 490:
            logging.debug(f"Committing batch of {count}")
            batch.commit()
            count = 0
    batch.commit()
    self.session.commit()
    self.session.close()
    return {'success': f"Wrote uuid {uuid} to model {firebasemodel}"}


@celery_app.task(bind=True,
                 base=TaskBase,
                 name='figure1.backend.rolling_case_sync')
def rolling_case_sync(self: TaskBase, limit: int = 10):
    if app_settings.case_sync_enabled is False:
        return

    if not isinstance(limit, int):
        raise ValueError("limit must be int")

    case_query = self.session.query(Case.case_uuid) \
        .filter(or_(Case.state == CaseState.APPROVED,
                    Case.state == CaseState.SC_APPROVED),
                or_(Case.synced_at < datetime.now(tz=timezone.utc) - timedelta(weeks=1),
                    Case.synced_at.is_(None))) \
        .order_by(nullsfirst(Case.synced_at)) \
        .limit(limit)

    tasks = []
    for each in case_query.all():
        case_uuid = str(each[0])
        task = do_firebase_sync.si(uuid=case_uuid, firebasemodel="CaseDetailV2")
        task.link(do_firebase_sync.si(uuid=case_uuid, firebasemodel="CommentV2"))

        tasks.append(task)

    group(*tasks).apply_async(queue='backend')
