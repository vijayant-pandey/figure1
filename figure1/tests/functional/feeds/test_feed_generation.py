from figure1.configuration import es_settings
from figure1.feeds.everything_feed import EverythingFeed
from figure1.feeds.topic_feed import TopicFeed
from figure1.feeds.mfy_feed import MadeForYouFeed
from figure1.feeds.feed_tasks import generate_preview_feeds_task
from figure1.pro.topics.domain import handle_bulk_topics
from figure1.feeds import write_feed_metadata, delete_feed_items, GroupFeed
from figure1.common.models.db import FeedType, Topic, GroupFeedDescriptor
from figure1.common.helpers import FeedCard
from figure1.store import PreviewFeeds
from figure1.pro.api.domain import get_rfy_data_feed
import time


def _get_fs_doc(fs, user_uid):
    def get_doc():
        return fs.collection('userFeedDB') \
            .document(user_uid).get()

    doc = get_doc()
    count = 0
    while not doc.exists:
        count += 1
        time.sleep(5)
        doc = get_doc()
        if count >= 5:
            break
    return doc.to_dict()


def test_mfy_feed(load_db, get_elasticsearch_client, test_user, get_firestore_client):
    session = load_db
    fs = get_firestore_client
    es = get_elasticsearch_client
    e = FeedType.get_made_for_you_uuid(session=session)
    generate_preview_feeds_task.apply()
    mfy = MadeForYouFeed(session=session, es_client=es, user_uid=test_user.get('userUid'), feed_type_uuid=str(e))
    mfy.feed_preview_new_location = 1
    mfy.feed_preview_new_enabled = True
    mfy.page_size = 100
    mfy.generate_feed()
    mfy.get_feed_items()

    assert 'query' in mfy.mfy_config.get_feed_query()

    last_doc = None
    doc_list = []
    preview_card = None
    for doc in fs.collection('userFeedDB') \
            .document(test_user.get('userUid')) \
            .collection(str(e)) \
            .list_documents():

        last_doc = doc.get().to_dict()
        doc_list.append(last_doc)
        if last_doc.get("feedCardType") == "preview_feed":
            preview_card = last_doc
    assert preview_card is not None

    expected_count = mfy.feed_config.get_cursor()
    if mfy.feed_config.get_eof():
        expected_count += 1
        assert last_doc.get('contentType') == 'EOF'

    if mfy.feed_preview_new_enabled:
        expected_count += 1

    delete_feed_items(user_uid=test_user.get('userUid'), feed_type_uuid=e)
    deleted_len = len(list(fs.collection('userFeedDB')
                           .document(test_user.get('userUid'))
                           .collection(str(e))
                           .list_documents(page_size=15)))
    assert deleted_len == 0


def test_everything_feed(load_db, get_elasticsearch_client, test_user, get_firestore_client):
    session = load_db
    fs = get_firestore_client
    es = get_elasticsearch_client
    e = FeedType.get_everything_uuid(session=session)
    h = EverythingFeed(session=session, es_client=es, user_uid=test_user.get('userUid'), feed_type_uuid=str(e))
    h.generate_feed()
    h.get_feed_items()

    fb_doc_len = len(list(fs.collection('userFeedDB')
                          .document(test_user.get('userUid'))
                          .collection(str(e))
                          .list_documents(page_size=15)))
    last_doc = None
    for doc in fs.collection('userFeedDB') \
            .document(test_user.get('userUid')) \
            .collection(str(e)) \
            .list_documents():
        last_doc = doc.get().to_dict()

    if h.feed_config.get_eof():
        assert h.feed_config.get_cursor() + 1 == fb_doc_len
        assert last_doc.get('contentType') == 'EOF'
    else:
        assert h.feed_config.get_cursor() == fb_doc_len

    delete_feed_items(user_uid=test_user.get('userUid'), feed_type_uuid=e)
    deleted_len = len(list(fs.collection('userFeedDB')
                           .document(test_user.get('userUid'))
                           .collection(str(e))
                           .list_documents(page_size=15)))
    assert deleted_len == 0


def test_topic_feeds(load_db, get_elasticsearch_client, test_user, get_firestore_client):
    session = load_db
    es = get_elasticsearch_client
    fs = get_firestore_client
    for t in Topic.get_all_topics_as_dict(session=session):
        topic = TopicFeed(session=session,
                          es_client=es,
                          user_uid=test_user.get('userUid'),
                          feed_type_uuid=t['feedTypeUuid'])
        topic.generate_feed()
        assert topic.feed_config.get_cursor() == 0
        assert topic.feed_config.feed_type_uuid == t['feedTypeUuid']
        topic.get_feed_items()
        fb_doc_len = len(list(fs.collection('userFeedDB')
                              .document(test_user.get('userUid'))
                              .collection(t['feedTypeUuid'])
                              .list_documents(page_size=15)))
        last_doc = None
        for doc in fs.collection('userFeedDB') \
                .document(test_user.get('userUid')) \
                .collection(t['feedTypeUuid']) \
                .list_documents():
            last_doc = doc.get().to_dict()
        if topic.feed_config.get_eof():
            assert topic.feed_config.get_cursor() + 1 == fb_doc_len
            assert last_doc.get('contentType') == 'EOF'
        else:
            assert topic.feed_config.get_cursor() == fb_doc_len


def test_group_feeds(load_db, get_elasticsearch_client, test_user, get_firestore_client, test_group_case):
    session = load_db
    es = get_elasticsearch_client
    fs = get_firestore_client
    case, _ = test_group_case

    gfm = session.query(GroupFeedDescriptor)\
        .filter(GroupFeedDescriptor.group_uuid == case.group_uuid)\
        .one_or_none()\
        .as_dict()
    feed_type_uuid = gfm['feedTypeUuid']

    gf = GroupFeed(session=session,
                   es_client=es,
                   user_uid=test_user.get('userUid'),
                   feed_type_uuid=feed_type_uuid)
    gf.generate_feed()
    assert gf.feed_config.get_cursor() == 0
    assert gf.feed_config.feed_type_uuid == gfm['feedTypeUuid']
    gf.get_feed_items()
    fb_doc_len = len(list(fs.collection('userFeedDB')
                          .document(test_user.get('userUid'))
                          .collection(feed_type_uuid)
                          .list_documents(page_size=15)))
    last_doc = None
    first_doc = None
    count = 0
    for doc in fs.collection('userFeedDB') \
            .document(test_user.get('userUid')) \
            .collection(feed_type_uuid) \
            .list_documents():
        count += 1
        if not first_doc:
            first_doc = doc.get().to_dict()
        last_doc = doc.get().to_dict()

    assert count == 2
    assert first_doc.get('caseUuid') == str(case.case_uuid)
    if gf.feed_config.get_eof():
        assert gf.feed_config.get_cursor() + 1 == fb_doc_len
        assert last_doc.get('contentType') == 'EOF'
    else:
        assert gf.feed_config.get_cursor() == fb_doc_len


def test_bulk_follow(load_db, test_user, get_firestore_client):
    fs = get_firestore_client
    session = load_db
    user_uid = test_user.get('userUid')
    bulk_follow = {'actions': []}

    for t in Topic.get_all_topics_as_dict(session=session):
        bulk_follow['actions'].append({'action': "follow", 'feed_type_uuid': t['feedTypeUuid']})

    handle_bulk_topics(user_uid=user_uid, data=bulk_follow['actions'], session=session)
    doc = _get_fs_doc(fs=fs, user_uid=user_uid)

    for t in Topic.get_all_topics_as_dict(session=session):
        assert doc['feeds'][t['feedTypeUuid']]['is_followed'] is True


def test_bulk_unfollow(load_db, test_user, get_firestore_client):
    fs = get_firestore_client
    session = load_db
    user_uid = test_user.get('userUid')
    bulk_unfollow = {'actions': []}
    for t in Topic.get_all_topics_as_dict(session=session):
        bulk_unfollow['actions'].append({'action': "unfollow", 'feed_type_uuid': t['feedTypeUuid']})
    handle_bulk_topics(user_uid=user_uid, data=bulk_unfollow['actions'], session=session)
    doc = _get_fs_doc(fs=fs, user_uid=user_uid)

    for t in Topic.get_all_topics_as_dict(session=session):
        assert doc['feeds'][t['feedTypeUuid']]['is_followed'] is False


def test_write_metadata(load_db, test_user, get_firestore_client):
    fs = get_firestore_client
    session = load_db
    user_uid = test_user.get('userUid')
    write_feed_metadata(user_uid=user_uid, session=session)
    everything = FeedType.get_everything_uuid(session=session)
    mfy = FeedType.get_made_for_you_uuid(session=session)
    user_feed = fs.collection('userFeedDB').document(user_uid).get().to_dict()
    assert user_feed['feeds'][everything]['feedKind'] == 'everything'
    assert user_feed['feeds'][everything]['hidden'] is False
    assert user_feed['feeds'][mfy]['feedKind'] == 'made_for_you'
    assert user_feed['feeds'][mfy]['hidden'] is False


def test_generate_feed_card(load_db, test_user, get_elasticsearch_client):
    es = get_elasticsearch_client
    r = es.search(index=es_settings.cases_alias,
                  body={"query": {"bool": {"must_not": [{"term": {"caseType": "promo_card"}}]}}})
    assert len(r.get('hits', {}).get('hits', [])) > 0
    for fi in r.get('hits', {}).get('hits', []):
        item = FeedCard.feed_card(feed_item=fi, user_uuid=test_user.get('userUuid'))
        assert isinstance(item, dict)


def test_preview_feed():
    """
    Ensure redis is populated correctly and handles non-existent feeds correctly
    :return:
    """
    generate_preview_feeds_task.apply()
    e = PreviewFeeds.get_preview_feed(feed_label='everything')
    topic = PreviewFeeds.get_preview_feed(feed_label='topic_radiology')
    empty = PreviewFeeds.get_preview_feed(feed_label='notExists')
    assert 'feed_name' in e
    assert 'feed_label' in e
    assert 'feed_type_uuid' in e

    assert 'feed_name' in topic
    assert 'feed_label' in topic
    assert 'feed_type_uuid' in topic

    assert empty == {}


def test_onboarding_feed(test_user):
    """
    Ensure that the onboarding call returns something.
    """
    df = get_rfy_data_feed(test_user.get('userUuid'))
    items = df.get('feed_items', [])
    assert len(items) > 0


def test_feed_request_response(load_db, get_elasticsearch_client, test_user, get_firestore_client):
    session = load_db
    fs = get_firestore_client
    es = get_elasticsearch_client
    e = FeedType.get_everything_uuid(session=session)
    h = EverythingFeed(session=session, es_client=es, user_uid=test_user.get('userUid'), feed_type_uuid=str(e))
    h.generate_feed(skip_delete=True)
    feed = h.get_feed_items(return_feed_items=True)

    fb_doc_len = len(list(fs.collection('userFeedDB')
                          .document(test_user.get('userUid'))
                          .collection(str(e))
                          .list_documents(page_size=15)))
    assert fb_doc_len == 0

    if h.feed_config.get_eof():
        assert h.feed_config.get_cursor() + 1 == len(feed)
        assert feed[-1].get('contentType') == 'EOF'
    else:
        assert h.feed_config.get_cursor() == len(feed)
