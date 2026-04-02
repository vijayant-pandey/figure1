import logging

from figure1.core import FirebaseTaskBase, celery_app
from figure1.common.models.db import PromotionChannels


@celery_app.task(bind=True, base=FirebaseTaskBase, name='figure1.backend.sync_promotion_channels')
def sync_promotion_channels(self, clean=None):
    logging.info("Syncing promotion channels to firestore...")
    firestore_data = {}
    doc = self.fs_client.collection('referenceData').document('promotionChannels')

    for c in self.session.query(PromotionChannels).all():
        uuid = str(c.channel_uuid)
        firestore_data[uuid] = {
            "channel_uuid": uuid,
            "channel_name": c.channel_name
        }

    doc.set({"all": firestore_data})
