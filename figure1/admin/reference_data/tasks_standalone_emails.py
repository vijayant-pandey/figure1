import logging

from sqlalchemy.exc import DatabaseError

from figure1.core import FirebaseTaskBase, celery_app
from figure1.common.models.data.read_data import StandaloneEmailData
from figure1.common.models.db import StandaloneEmail
from figure1.common.iterable import IterableAPI
from figure1.common.types import StandaloneEmailKind

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, base=FirebaseTaskBase, name='figure1.backend.initialize_standalone_email')
def initialize_standalone_emails(self, clean=None):
    logger.info("Saving standalone emails to postgres...")
    _save_standalone_emails(session=self.session)
    logger.info("Done updating standalone emails")


def _save_standalone_emails(session):
    iterable_client = IterableAPI()
    campaigns = iterable_client.list_campaigns()
    if not campaigns:
        logger.error(f"Could not get iterable campaigns")
        return

    for d in StandaloneEmailData.load_standalone_emails():
        try:
            kind = StandaloneEmailKind(d.get('kind').lower())
        except ValueError as e:
            logger.error(f"Unrecognized kind for standalone email: {e}")
            continue

        iterable_name = d.get('iterableName')

        campaign = next((c for c in campaigns if c['name'] == iterable_name), None)
        if not campaign:
            logger.error(f"Could not find iterable campaign for: {iterable_name}")
            continue

        iterable_campaign_id = campaign.get('id')
        if not iterable_campaign_id:
            logger.error(f"Could not find iterable campaign id for: {iterable_name}")
            continue

        StandaloneEmail.create_or_update(kind=kind,
                                         iterable_campaign_id=iterable_campaign_id,
                                         session=session)

    try:
        session.commit()
    except DatabaseError as e:
        logger.error(f"Failed to save standalone emails: {e}")
        session.rollback()
