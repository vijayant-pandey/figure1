import logging

from figure1.core import FirebaseTaskBase, celery_app
from figure1.common.types import Locale


@celery_app.task(bind=True, base=FirebaseTaskBase, name='figure1.backend.initialize_locales')
def initialize_locales(self, clean=None):
    logger = logging.getLogger(__name__)
    logger.info("Syncing locales to firestore...")
    _sync_locales(fs_client=self.fs_client)
    logging.info("Done updating locales")


def _sync_locales(fs_client):
    locales = fs_client.collection('referenceData').document('locales')
    locales_old = fs_client.collection('b_referenceData').document('locales')
    firestore_data = {}

    for locale in Locale:
        firestore_data[locale.code] = locale.as_dict()

    locales.set({'supported': firestore_data})
    locales_old.set({'supported': firestore_data})
