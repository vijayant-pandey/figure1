import logging
from figure1.admin.reference_data.model_methods import get_public_labels
from figure1.core import FirebaseTaskBase, celery_app
from figure1.common.models.db import Label
from figure1.common.models.data import LabelData


@celery_app.task(bind=True, base=FirebaseTaskBase, name='figure1.backend.initialize_labels')
def initialize_labels(self, clean=None):
    logger = logging.getLogger(__name__)
    logger.info("Saving labels to postgres...")
    save_labels(session=self.session)
    logger.info("Syncing labels to firestore...")
    _sync_labels(fs_client=self.fs_client, session=self.session)
    logging.info("Done updating labels")
    return 'Labels updated'


def save_labels(session, filename=None):
    logger = logging.getLogger(__name__)

    data = LabelData.load_labels(filename=filename)
    if not data:
        return

    for label in data:
        Label.create_or_update(name=label[0],
                               kind=label[1],
                               is_public=label[2].lower() == 'true',
                               skip_commit=True,
                               session=session)

    try:
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f'Failed to update labels: {e}')


def _sync_labels(fs_client, session):
    specialties = fs_client.collection('referenceData').document('labels')
    specialties_old = fs_client.collection('b_referenceData').document('labels')
    firestore_data = {}

    for label in get_public_labels(session):
        uuid = str(label.label_uuid)
        firestore_data[uuid] = {
            'labelUuid': uuid,
            'name': {
                'en': label.name
            },
            "labelKind": label.kind
        }

    specialties.set({'all': firestore_data})
    specialties_old.set({'all': firestore_data})
