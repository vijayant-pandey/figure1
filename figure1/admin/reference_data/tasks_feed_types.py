import logging

from figure1.common.models.db import FeedKind
from figure1.common.models.db import FeedPreview
from figure1.common.models.db import FeedType
from figure1.common.models.db import Topic
from figure1.core import FirebaseTaskBase
from figure1.core import celery_app


@celery_app.task(bind=True, base=FirebaseTaskBase, name='figure1.backend.initialize_feed_types')
def initialize_feed_types(self, clean=None):
    logger = logging.getLogger(__name__)
    logger.info("Saving feed types to postgres...")
    _save_feed_types(session=self.session)
    logger.info("Syncing feed types to firestore...")
    _sync_feed_types(fs_client=self.fs_client, session=self.session)
    logger.info("Done updating feed types")


def _save_feed_types(session):
    logger = logging.getLogger(__name__)

    if not session.query(FeedType).filter(FeedType.kind == FeedKind.EVERYTHING).one_or_none():
        logger.error("Creating everything feed entry")
        FeedType.create(kind=FeedKind.EVERYTHING,
                        name="New cases",
                        label="everything",
                        session=session)
    if not session.query(FeedType).filter(FeedType.kind == FeedKind.MADE_FOR_YOU).one_or_none():
        logger.error("Creating mfy feed entry")
        FeedType.create(kind=FeedKind.MADE_FOR_YOU,
                        name="For You",
                        label="madeForYou",
                        session=session)
    if not session.query(FeedType).filter(FeedType.kind == FeedKind.SEARCH).one_or_none():
        logger.error("Creating search feed entry")
        FeedType.create(kind=FeedKind.SEARCH,
                        name="Search",
                        label="search",
                        session=session)

    FeedPreview.add_public_feeds(session=session)


def _sync_feed_types(fs_client, session):
    firestore_data = {}
    doc = fs_client.collection('referenceData').document('feeds')

    for ft in session.query(FeedType) \
            .filter(FeedType.kind != FeedKind.GROUP) \
            .all():
        display_order = None
        if ft.kind is FeedKind.TOPIC:
            t = session.query(Topic) \
                .filter(Topic.feed_type_uuid == ft.feed_type_uuid,
                        Topic.hidden.is_(False),
                        Topic.display_order < 100)\
                .one_or_none()
            if not t:
                continue
            else:
                display_order = t.display_order

        uuid = str(ft.feed_type_uuid)
        firestore_data[uuid] = {
            "feed_type_uuid": uuid,
            "feed_kind": ft.kind.name.lower(),
            "feed_name": {
                'en': ft.name
            },
            "label": ft.label,
            "display_order": display_order
        }
        doc.set({"all": firestore_data})
