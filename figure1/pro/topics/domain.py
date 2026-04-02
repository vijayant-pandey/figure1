import logging
from celery import group
from operator import itemgetter

from figure1.admin.reference_data import sync_topics
from figure1.core import managed_session
from figure1.common.models.db import UserFeedSubscription, User, Topic, FeedType, FeedKind
from figure1.common.models.firebase import FirebaseCollectionManager
from figure1.common.types import FeedMetaDataDocument, Locale
from figure1.events import UserEvents
from figure1.exceptions import TopicFeedNotFound
from figure1.feeds import delete_feed_items_task

fb = FirebaseCollectionManager()


def _update_firestore_document(user_uid, update_doc=None, delete_doc_uuid=None):
    """
    Takes an update_doc which is a feed_meta data struct. This is added to the feeds list in the feed document for
    the user. To follow/unfollow, the is_followed boolean is toggled.

    When handling campaign preview topics things are slightly different. When a user is removed, we want to make sure
    that the feed no longer appears. As a result, the feed_type_uuid only is passed to delete_doc_uuid and the
    uuid is removed completely from the feeds map.

    :param user_uid:
    :param update_doc: meta data document for a feed to operate on
    :return: None
    """
    fb.set_fs_client(documents=[user_uid], collections=['userFeedDB'])

    if update_doc:
        fb.set({'feeds': update_doc}, merge=True)

    if delete_doc_uuid:
        f = fb.get().to_dict()
        if not f:
            return
        feeds_doc = {}
        if 'feeds' in f:
            for k in f['feeds'].keys():
                if k == delete_doc_uuid:
                    continue
                else:
                    feeds_doc.update({k: f['feeds'][k]})
        fb.set({'feeds': feeds_doc}, merge=False)


def manage_topic(follow: bool, session, feed_type_uuid, user_uid):
    feed_data = FeedType.get_feed_from_type_uuid(feed_type_uuid=feed_type_uuid, session=session)
    feed = FeedMetaDataDocument(
        feed_type_uuid=feed_type_uuid,
        feedTypeUuid=feed_type_uuid,
        feed_kind=feed_data.kind.name.lower(),
        feedKind=feed_data.kind.name.lower(),
        is_followed=follow,
        isFollowed=follow,
        search_results_total=0,
        searchResultsTotal=0,
        endOfFeed=False,
        feed_name=feed_data.name,
        feedName=feed_data.name,
        hidden=feed_data.topic.hidden if feed_data.topic else False
    )
    _update_firestore_document(user_uid=user_uid, update_doc=feed.firestore_struct())


@managed_session
def follow_topic(user_uid, feed_type_uuid, session=None):
    """
    Follows a topic, this is intended to handle a single topic.

    This can throw a Validation error if there is a problem with the feed data, this is caught by a general flask
    exception handler.
    :param user_uid:
    :param feed_type_uuid:
    :param session:
    :return:
    """
    user = User.get_user_by_uid(user_uid=user_uid, session=session, raise_exception=True)
    UserFeedSubscription.create(user_uuid=user.user_uuid, feed_type_uuid=feed_type_uuid, session=session)
    manage_topic(follow=True, feed_type_uuid=feed_type_uuid, user_uid=user_uid, session=session)
    UserEvents.USER_SUBSCRIBE(user_uuid=str(user.user_uuid))
    return {'success': f"Subscribed user {user_uid} to topic {feed_type_uuid}"}


@managed_session
def unfollow_topic(user_uid, feed_type_uuid, session=None):
    """
    Unsubscribes a user from a topic. This removes the feed_type_uuid/user_uuid combination from the
    UserFeedSubscription table and sets the isFollowed property to false in the firestore feeds map.
    :param user_uid:
    :param feed_type_uuid:
    :param session:
    :return:
    """
    user = User.get_user_by_uid(user_uid=user_uid, session=session, raise_exception=True)
    session.query(UserFeedSubscription) \
        .filter(UserFeedSubscription.user_uuid == user.user_uuid,
                UserFeedSubscription.feed_type_uuid == feed_type_uuid) \
        .delete()
    manage_topic(follow=False, feed_type_uuid=feed_type_uuid, user_uid=user_uid, session=session)
    delete_feed_items_task.delay(user_uid=user_uid, feed_type_uuid=feed_type_uuid)
    UserEvents.USER_UNSUBSCRIBE(user_uuid=str(user.user_uuid))
    return {'success': f"Unsubscribed user {user_uid} to topic {feed_type_uuid}"}


@managed_session
def unfollow_campaign_preview(user_uid, feed_type_uuid, session=None):
    """
    Unfollowing a campaign preview is normally initiated when a user uid is removed from the preview list in
    the campaign tool. Unsubscribing a user here is different than unfollowing a public feed because we do not
    want the feed to appear as a feed the user can subscribe too. Therefore, we delete the feed completely from
    the feed list.

    :param user_uid:
    :param feed_type_uuid:
    :param session:
    :return:
    """
    user = User.get_user_by_uid(user_uid=user_uid, session=session, raise_exception=True)
    session.query(UserFeedSubscription) \
        .filter(UserFeedSubscription.user_uuid == user.user_uuid,
                UserFeedSubscription.feed_type_uuid == feed_type_uuid) \
        .delete()
    _update_firestore_document(user_uid=user_uid, delete_doc_uuid=feed_type_uuid)


@managed_session
def handle_bulk_topics(user_uid, data, session=None):
    """
    The managed session will handle commits and rollbacks, Database errors and Validation errors are handled
    by generic exception handlers.
    Firestore may be in an odd position if the database commit fails, but as soon as the feed syncs, it should fix
    the subscriptions. Updating firestore here is essentially an optimistic update.
    :param user_uid:
    :param data:
    :param session:
    :return:
    """
    logger = logging.getLogger(__name__)
    user = User.get_user_by_uid(user_uid=user_uid, session=session, raise_exception=True)
    feed_updates = {}
    task_list = []
    for topic_action in data:
        feed_type_uuid = topic_action.get('feed_type_uuid')
        if not feed_type_uuid:
            logger.error("No feed uuid in action dict, skipping")
            continue

        feed_data = FeedType.get_feed_from_type_uuid(feed_type_uuid=feed_type_uuid, session=session)
        feed = FeedMetaDataDocument(
            feed_type_uuid=feed_type_uuid,
            feedTypeUuid=feed_type_uuid,
            feed_kind=feed_data.kind.name.lower(),
            feedKind=feed_data.kind.name.lower(),
            endOfFeed=False,
            feed_name=feed_data.name,
            feedName=feed_data.name,
        )
        if topic_action.get('action').lower() == 'follow':
            UserFeedSubscription.create(user_uuid=user.user_uuid, feed_type_uuid=feed_type_uuid, session=session)
            feed.isFollowed = True
            feed.is_followed = True
            UserEvents.USER_SUBSCRIBE(user_uuid=str(user.user_uuid))
        elif topic_action.get('action').lower() == 'unfollow':
            feed.isFollowed = False
            feed.is_followed = False
            session.query(UserFeedSubscription) \
                .filter(UserFeedSubscription.user_uuid == user.user_uuid,
                        UserFeedSubscription.feed_type_uuid == feed_type_uuid) \
                .delete()
            task_list.append(delete_feed_items_task.si(user_uid=user_uid, feed_type_uuid=feed_type_uuid))
            UserEvents.USER_UNSUBSCRIBE(user_uuid=str(user.user_uuid))
        else:
            logger.error("Action %s was not recognized", topic_action.get('action'))
            continue
        feed_updates.update(feed.firestore_struct())
    if task_list:
        task = group(*task_list)
        task.apply_async()
    _update_firestore_document(user_uid=user_uid, update_doc=feed_updates)
    return {'success': 'Topics updated'}


@managed_session
def create_topic(label,
                 name,
                 specialtyUuids: list,
                 filter_query: dict,
                 expire_query: dict,
                 sort_fields: list,
                 state_filter: str = 'APPROVED',
                 topic_language: str = 'EN_US',
                 session=None):
    ft = FeedType.create(kind=FeedKind.TOPIC,
                         name=name,
                         label=label,
                         session=session)

    t = Topic.create_or_update(feed_type_uuid=ft.feed_type_uuid,
                               name=name,
                               label=label,
                               specialty_uuids=specialtyUuids,
                               hidden=True,
                               state_filter=state_filter,
                               filter_query=filter_query,
                               expire_query=expire_query,
                               sort_fields=sort_fields,
                               topic_language=topic_language,
                               session=session)
    sync_topics.apply_async(countdown=5)
    return t.as_dict()


@managed_session
def update_topic(label,
                 name,
                 hidden,
                 display_order,
                 specialtyUuids: list,
                 filter_query: dict,
                 expire_query: dict,
                 sort_fields: list,
                 state_filter: str = 'APPROVED',
                 topic_language: str = 'EN_US',
                 session=None):
    t = session.query(Topic).filter(Topic.label == label).one_or_none()
    task = None

    if not t:
        raise TopicFeedNotFound(msg="No topic to update", return_code=404)

    if name:
        t.name = name
        session.query(FeedType).filter(FeedType.feed_type_uuid == t.feed_type_uuid).update({'name': name})
    if hidden is False:
        t.hidden = False
        task = sync_topics.si()
    else:
        t.hidden = True
        task = sync_topics.si()

    if specialtyUuids:
        t.specialty_uuids = specialtyUuids
    if filter_query:
        t.filter_query = filter_query
    if expire_query:
        t.expire_query = expire_query
    if sort_fields:
        t.sort_fields = sort_fields
    if state_filter:
        t.state_filter = state_filter
    if topic_language:
        for locale in Locale.__members__:
            if Locale[locale].code == topic_language:
                t.topic_language = topic_language
    if display_order < 100:
        chk = session.query(Topic).filter(Topic.display_order == display_order).one_or_none()
        if chk:
            return {"error": f'Unable to adjust display order - already in use for topic {chk.label}'}
        t.display_order = display_order
    else:
        t.display_order = display_order

    session.add(t)
    if task:
        task.apply_async(countdown=5)
    return t.as_dict()


@managed_session
def delete_topic(label, session=None):
    session.query(Topic).filter(Topic.label == label).delete()
    session.query(FeedType).filter(FeedType.label == label).delete()
    session.commit()

    sync_topics.delay()
    return {'success': 'Feed deleted'}


@managed_session
def get_topic_list(session=None, show_hidden=True):
    topics = list(Topic.get_all_topics_as_dict(session=session, show_hidden=show_hidden))
    topics.sort(key=itemgetter('displayOrder'))
    return topics
