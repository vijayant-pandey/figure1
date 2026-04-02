import logging
from datetime import datetime, timezone

from figure1.core import es
from figure1.common.models.db import User, UserFeedSubscription, FeedType, FeedPreview, FeedKind, \
    Topic
from figure1.common.types import UserFeedMetaDataDocument, FeedMetaDataDocument
from figure1.core import FirebaseTaskBase, FirebaseClient, celery_app
from figure1.exceptions import UserNotFound
from figure1.feeds import MadeForYouFeed
from figure1.feeds.feed_base import GeneratePreview
from figure1.store import UserRFYFeedConfig, PreviewFeeds

fs = FirebaseClient()
logger = logging.getLogger('figure1.common.feed_tasks')


@celery_app.task(bind=True, base=FirebaseTaskBase, name='figure1.backend.generate_preview_feeds')
def generate_preview_feeds_task(self):
    for f in self.session.query(FeedPreview).order_by(FeedPreview.last_run_time.desc()).all():
        pf = PreviewFeeds(feed_label=f.feed_type.label,
                          feed_name=f.feed_type.name,
                          feed_type_uuid=str(f.feed_type_uuid))
        pf.write_feed_config()
        gen_feed = GeneratePreview(feed_type_uuid=str(f.feed_type_uuid))
        gen_feed.delete_feed_documents()
        if f.feed_type.kind is FeedKind.EVERYTHING:
            newcase_list = gen_feed.generate_new_items()
            if newcase_list:
                feed_data = gen_feed.populate_feed_items(items=newcase_list, include_eof=False)
                gen_feed.sync_feed_items(feed_data=feed_data)
            f.last_run_time = datetime.now(tz=timezone.utc)
            self.session.add(f)
        if f.feed_type.kind is FeedKind.TOPIC:
            topic = self.session.query(Topic).get(f.feed_type_uuid)
            if topic:
                case_list = gen_feed.generate_topic_items(topic=topic)
                if case_list:
                    feed_data = gen_feed.populate_feed_items(items=case_list, include_eof=False)
                    gen_feed.sync_feed_items(feed_data=feed_data)
                f.last_run_time = datetime.now(tz=timezone.utc)
                self.session.add(f)


@celery_app.task(bind=True,
                 base=FirebaseTaskBase,
                 autoretry_for=(UserNotFound,),
                 name='figure1.backend.write_feed_metadata_task')
def write_feed_metadata_task(self, user_uid=None, user_uuid=None, regenerate_mfy=False):
    uid = None
    if user_uid:
        uid = user_uid
    elif user_uuid:
        user = User.get_user_by_uuid(user_uuid=user_uuid, session=self.session, raise_exception=True)
        if user.user_uid:
            uid = user.user_uid
    else:
        raise UserNotFound(msg='No user argument passed')
    if not uid:
        logger.error("No user_uid - cannot write feed - passed uid %s and uuid %s", user_uid, user_uuid)
        return
    write_feed_metadata(user_uid=uid, session=self.session)


@celery_app.task(base=FirebaseTaskBase,
                 name='figure1.backend.delete_feed_items_task')
def delete_feed_items_task(user_uid, feed_type_uuid):
    delete_feed_items(user_uid=user_uid, feed_type_uuid=feed_type_uuid)


def delete_feed_items(user_uid: str, feed_type_uuid: str):
    firestore_client = fs.fs_client
    batch = firestore_client.batch()
    coll = firestore_client.collection('userFeedDB').document(user_uid).collection(feed_type_uuid)
    count = 0
    for doc in coll.list_documents():
        batch.delete(doc)
        count += 1
        if count >= 499:
            batch.commit()
            count = 0
    batch.commit()


def write_feed_metadata(session, user_uid=None, user_uuid=None):
    """
    This writes out all feed metadata for a given user. It does not attempt to merge, it overwrites
    all metadata.
    :param user_uid:
    :param user_uuid:
    :param session:
    :return:
    """

    def populate_feed(feed_data) -> FeedMetaDataDocument:
        return FeedMetaDataDocument(feed_type_uuid=feed_data.feed_type_uuid,
                                    feedTypeUuid=feed_data.feed_type_uuid,
                                    feed_kind=feed_data.kind.name.lower(),
                                    feedKind=feed_data.kind.name.lower(),
                                    is_followed=True,
                                    isFollowed=True,
                                    feed_name=feed_data.name,
                                    feedName=feed_data.name,
                                    hidden=feed_data.topic.hidden if feed_data.topic else False)

    firestore_client = fs.fs_client.collection('userFeedDB').document(user_uid)

    everything_uuid = FeedType.get_everything_uuid(session=session)
    mfy_uuid = FeedType.get_made_for_you_uuid(session=session)
    everything_data = FeedType.get_feed_from_type_uuid(feed_type_uuid=everything_uuid, session=session)
    mfy_data = FeedType.get_feed_from_type_uuid(feed_type_uuid=mfy_uuid, session=session)
    if user_uid:
        user = User.get_user_by_uid(user_uid=user_uid, session=session, raise_exception=True)
    elif user_uuid:
        user = User.get_user_by_uuid(user_uuid=user_uuid, session=session, raise_exception=True)
    else:
        return None

    user_feed_doc = UserFeedMetaDataDocument(
        user_uid=user.user_uid,
        userUid=user.user_uid,
        user_uuid=user.user_uuid,
        userUuid=user.user_uuid,
        username=user.username,
        email=user.email,
        first_name=user.first_name,
        firstName=user.first_name,
        last_name=user.last_name,
        lastName=user.last_name,
        feeds={}
    )

    rfy_config = UserRFYFeedConfig(user_uuid=str(user.user_uuid), feed_type_uuid=str(mfy_uuid))
    rfy_config.delete_user_interests()
    for feed in UserFeedSubscription.get_subscribed_feeds(user_uuid=user.user_uuid, session=session):
        feed_data: FeedType = FeedType.get_feed_from_type_uuid(feed_type_uuid=feed.get('feedTypeUuid'),
                                                               session=session)
        feed_doc = populate_feed(feed_data=feed_data)
        user_feed_doc.feeds.update({feed_doc.feed_type_uuid: feed_doc})

    everything_doc = populate_feed(feed_data=everything_data)
    mfy_doc = populate_feed(feed_data=mfy_data)
    user_feed_doc.feeds.update({everything_doc.feed_type_uuid: everything_doc,
                                mfy_doc.feed_type_uuid: mfy_doc})

    firestore_client.set(user_feed_doc.dict(exclude_none=True))
