import logging
import json
from elasticsearch_dsl import Search
from elasticsearch_dsl import Q
from pydantic import BaseModel
from pydantic import Field
from typing import List
from typing import Dict
from typing import Optional
from figure1.common.models.db import Topic
from figure1.common.models.firebase import FirebaseCollectionManager
from figure1.common.types import FirebaseFeedID
from figure1.common.types import CaseClassification
from figure1.common.types import UserFeedMetaDataDocument
from figure1.common.types import FeedMetaDataDocument
from figure1.common.types import Locale
from figure1.common.helpers import FeedCard
from figure1.common.helpers import UserDocument
from figure1.common.helpers import user_uuid_from_uid

from figure1.common.types import FeedCardType
from figure1.configuration import es_settings
from figure1.configuration import app_settings
from figure1.store import UserFeedConfig
from figure1.store import PreviewFeeds
from figure1.core import es
from .sponsored_content import SponsoredContent

fb = FirebaseCollectionManager()
fb_id = FirebaseFeedID()
logger = logging.getLogger('figure1.feeds.base')


class ElasticsearchQueryGenerator:
    _bool_should = []
    _bool_must = []
    _bool_must_not = []
    _bool_filters = []
    _aggregations = {}
    query = {}
    function_score_wrapper = {}

    def __repr__(self):
        return f"ElasticsearchQueryGenerator:<query:{json.dumps(self.query)}>"

    def __str__(self):
        if self.query:
            return json.dumps(self.query)

    def __init__(self):
        self.reset()

    def reset(self):
        self.function_score_wrapper = {}
        self._bool_filters = []
        self._bool_must_not = []
        self._bool_must = []
        self._bool_should = []
        self._aggregations = {}
        self.query = {}

    def _create_query(self):
        q = {}
        bool_query = {}
        if self._bool_filters:
            bool_query.update({"filter": self._bool_filters})
        if self._bool_should:
            bool_query.update({"should": self._bool_should})
        if self._bool_must:
            bool_query.update({"must": self._bool_must})
        if self._bool_must_not:
            bool_query.update({"must_not": self._bool_must_not})

        if self._aggregations:
            q.update({**self._aggregations})

        if self.function_score_wrapper:
            q.update({'query': self.function_score_wrapper})
            q['query']['function_score'].update({"query": {"bool": {**bool_query}}})
        else:
            q.update({'query': {"bool": {**bool_query}}})
        return q

    def to_json(self):
        q = self.validate_query()
        if q:
            return json.dumps(q)
        return {}

    def validate_query(self):
        q = self._create_query()
        if not q:
            return False
        validate = es.indices.validate_query(body=q, index=es_settings.cases_alias)
        if validate.get("valid", False):
            logger.debug("Query %s is valid", json.dumps(q))
            return q
        elif "aggs" in q:
            logger.info("Aggregates not supported in validation")
            return q
        else:
            logger.error("Query %s is invalid", json.dumps(q))
            return False

    def add_filter(self, search_filter):
        self._bool_filters.append(search_filter)
        return self

    def add_should(self, search_should):
        self._bool_should.append(search_should)
        return self

    def add_must(self, search_must):
        self._bool_must.append(search_must)
        return self

    def add_must_not(self, search_must_not):
        self._bool_must_not.append(search_must_not)
        return self

    def add_function_score(self, function_score):
        self.function_score_wrapper = function_score
        return self

    def apply_case_state_filter(self, case_state='APPROVED'):
        return self.add_filter(search_filter={"term": {"caseState": case_state}})

    def apply_language_filter(self, allow_languages=None):
        return self.add_filter(search_filter={"terms": {
            "language.keyword": Locale.get_lang_code_filter(allow_languages=allow_languages)
        }})

    def apply_date_filter(self):
        return self.add_filter(search_filter={"range": {
            "publishedAt": {
                "lte": "now/d"
            }
        }})

    def apply_new_case_params(self):
        return self.add_filter(search_filter={"range": {
            "publishedAt": {
                "gte": "now-30d/d"
            }
        }})

    def apply_user_filters(self, search_filters):
        if search_filters:
            return self.add_filter(search_filter={"terms": {"labels": [*search_filters]}})
        return self

    def apply_interest_aggregate(self, user_interests):
        if not user_interests:
            return

        if not isinstance(user_interests, list):
            return
        self._aggregations = {
            "aggs": {
                "user_interest_aggregation": {
                    "terms": {
                        "field": "specialtyUuids",
                        "exclude": user_interests
                    }
                }
            }
        }
        return self

    def apply_score_functions(self):

        create_decay_function = {
            "exp": {
                "publishedAt": {
                    "scale": "7d",
                    "decay": 0.9
                }
            },
            "weight": 1
        }

        trend_score = {
            "field_value_factor": {
                "field": "trendScore",
                "factor": 1.0,
                "modifier": "log2p",
                "missing": 1
            }
        }

        functions_score = {
            "function_score": {
                "score_mode": "sum",
                "boost_mode": "sum",
                "query": {},
                "functions": [
                    create_decay_function,
                    trend_score
                ]
            }
        }
        self.function_score_wrapper = functions_score
        return self

    def apply_group_must_not(self):
        return self.add_must_not(search_must_not={"exists": {
            "field": "groupUuid"
        }})


class FeedCardBaseModel(BaseModel):
    contentType: Optional[str] = "EOF"
    text: Optional[str] = "End Of Feed Reached"
    feedCardType: FeedCardType

    class Config:
        use_enum_values = True

    def elasticsearch_wrapper(self):
        return dict(_source=self.dict())


class FeedCardEOF(FeedCardBaseModel):
    pass


class FeedCardPreviewFeed(FeedCardBaseModel):
    previewFeedTypeUuid: Optional[str] = Field(alias='feed_type_uuid')
    previewFeedLabel: Optional[str] = Field(alias='feed_label')
    previewFeedName: Optional[str] = Field(alias='feed_name')


class FeedResultSet(BaseModel):
    feed_type_uuid: str
    search_results_total: int = 0
    end_of_feed: bool = False
    user_uid: str
    search_results: Dict[str, Dict[str, List]] = {'hits': {'hits': []}}


class GenerateFeed(object):
    index_alias = es_settings.cases_alias
    feed_preview_new_enabled = app_settings.feed_preview_new_enabled
    feed_preview_new_location = app_settings.feed_preview_new_location
    feed_preview_trending_enabled = app_settings.feed_preview_trending_enabled
    feed_preview_trending_location = app_settings.feed_preview_trending_location
    feed_type_uuid = None
    feed_search_filters = []
    firestore_metadata = None
    firestore_feed = None
    batch = None
    batch_count = 0

    def __init__(self, feed_type_uuid):
        self.feed_type_uuid = feed_type_uuid

    def configure_firestore(self):
        if hasattr(self, 'user_uid'):
            self.firestore_metadata = fb.set_fs_client(collections=['userFeedDB'], documents=[self.user_uid])
            self.firestore_feed = fb.fs_client.collection('userFeedDB') \
                .document(self.user_uid) \
                .collection(self.feed_type_uuid)
            self.batch = fb.fs_client.batch()
            self.batch_count = 0

    def delete_feed_documents(self):
        for doc in self.firestore_feed.list_documents():
            self.batch.delete(doc)
            self.batch_count += 1
            if self.batch_count == 499:
                logger.error("Deleted 499 documents")
                self.batch.commit()
                self.batch_count = 0
        logger.info("Deleted %s documents", self.batch_count)

    def execute_search(self, q, sort_fields, page_size: int, cursor: int):
        """
        Execute elasticsearch query, never return source
        :param q: elasticsearch query
        :param sort_fields: list of sort fields
        :param page_size: defaults to 10
        :param cursor: where to start the page
        :return:
        """
        if isinstance(q, ElasticsearchQueryGenerator):
            query = q.validate_query()
            if not query:
                logger.error("Query is invalid %s", json.dumps(query))
                return {}

            return es.search(body=query,
                             index=self.index_alias,
                             sort=sort_fields,
                             size=page_size,
                             _source=False,
                             from_=cursor)
        else:
            return es.search(body=q,
                             index=self.index_alias,
                             sort=sort_fields,
                             size=page_size,
                             _source=False,
                             from_=cursor)

    def end_of_feed(self):
        """
        Standalone feed document signaling the end of the feed. Wrap it in _source to make it compatible with
         elasticsearch results.
        :return:
        """
        return FeedCardEOF(feedCardType=FeedCardType.END_OF_FEED).elasticsearch_wrapper()

    def populate_feed_items(self, items, include_eof=True, last_page=False):
        """
        Given a list of case_uuids, get them from elasticsearch and return the list. Only ids that are marked
        as either APPROVED or SC_APPROVED are returned.
        If the list is empty or a non-list is passed, an EOF is returned
        :param items:
        :return:
        """
        feed_items = []
        if not isinstance(items, list):
            logger.error("items not passed in a list, returning EOF")
            if include_eof:
                feed_items.append(self.end_of_feed())
            return {"docs": feed_items}

        if not items:
            logger.info("No items in list, returning EOF")
            if include_eof:
                feed_items.append(self.end_of_feed())
            return {"docs": feed_items}

        mget_doc = {"docs": []}

        for i in items:
            mget_doc['docs'].append({"_id": i})

        results = es.mget(index=es_settings.cases_alias, body=mget_doc)

        for r in results.get("docs", []):
            if not r.get('found'):
                logger.error("Failed to find id %s", json.dumps(r))
                continue
            if r.get('_source').get('caseState') not in ['APPROVED', 'SC_APPROVED', 'SC_REVIEW']:
                logger.error("Document %s in incorrect state", r.get('_id'))
                continue
            feed_items.append(r)
        if last_page:
            feed_items.append(self.end_of_feed())
        logger.info("Returning %s populated items", len(feed_items))
        return {"docs": feed_items}

    def sync_feed_items(self, feed_data, user_uuid=None, return_only=False):
        """
        :param feed_data:
        :param user_uuid:
        :param return_only: if true, feed items are returned instead of syncing to firestore
        :return:
        """

        def _sync_item(item):
            fi = self.firestore_feed.document(fb_id.next_id())
            self.batch.set(fi, item, merge=False)
            self.batch_count += 1
            if self.batch_count == 499:
                self.batch.commit()
                self.batch_count = 0

        preview_trending_model = None
        preview_new_model = None
        if self.feed_preview_trending_enabled:
            preview_trending = PreviewFeeds.get_preview_feed(feed_label='trendingCases')
            if preview_trending:
                preview_trending_model = FeedCardPreviewFeed.parse_obj({**preview_trending,
                                                                        'feedCardType': FeedCardType.PREVIEW_FEED,
                                                                        'text': preview_trending.get("feed_name"),
                                                                        'contentType': 'preview_feed'})
        if self.feed_preview_new_enabled:
            preview_new = PreviewFeeds.get_preview_feed(feed_label='everything')
            if preview_new:
                preview_new_model = FeedCardPreviewFeed.parse_obj({**preview_new,
                                                                   'feedCardType': FeedCardType.PREVIEW_FEED,
                                                                   'text': preview_new.get("feed_name"),
                                                                   'contentType': 'preview_feed'
                                                                   })
        if feed_data.get("docs"):
            logger.debug("Got docs, extracting document list")
            feed_list = feed_data.get("docs", [])
        elif feed_data.get("hits"):
            logger.debug("Got search results, extracting document list")
            feed_list = feed_data.get('hits', {}).get('hits', [])
        else:
            logger.error("Unable to find docs or search results")
            return None

        feed_cards = []
        for count, item in enumerate(feed_list):
            if preview_trending_model and count == self.feed_preview_trending_location - 1:
                feed_item = FeedCard.feed_card(feed_item=preview_trending_model.elasticsearch_wrapper())
                if feed_item:
                    feed_cards.append(feed_item)

            elif preview_new_model and count == self.feed_preview_new_location - 1:
                feed_item = FeedCard.feed_card(feed_item=preview_new_model.elasticsearch_wrapper())
                if feed_item:
                    feed_cards.append(feed_item)

            if user_uuid:
                feed_item = FeedCard.feed_card(feed_item=item, user_uuid=user_uuid)
            else:
                feed_item = FeedCard.feed_card(feed_item=item)
            if feed_item:
                feed_cards.append(feed_item)

        if return_only:
            return feed_cards
        else:
            for fc in feed_cards:
                _sync_item(fc)
            self.batch.commit()


class BaseFeed(GenerateFeed):
    page_size = 10

    def __init__(self, session, es_client, user_uid, feed_type_uuid, feed_language=Locale.EN_US):
        """
        The base class for user feeds.

        :param session: An orm session
        :param es_client: An initialized elasticsearch client
        :param user_uid: The UID of the user requesting the feed
        :param feed_type_uuid: The unique identifier for the feed requested.
        :param feed_language: This can be a string or a list of items in the Locale enum. If an unsupported value is
        passed, it is silently ignored. If nothing is passed, or all items are invalid, then it falls back to EN_US.
        """

        super().__init__(feed_type_uuid=feed_type_uuid)
        self.session = session
        self.es_client = es_client
        self.index_alias = es_settings.cases_alias
        self.sponsored_content_enabled = app_settings.sponsored_content_enabled
        self.feed_language = feed_language
        self.user_uid = user_uid
        self.user_uuid = user_uuid_from_uid(user_uid)

        self.feed_type_uuid = feed_type_uuid
        self.configure_firestore()
        self.feed_config = UserFeedConfig(user_uuid=self.user_uuid, feed_type_uuid=feed_type_uuid)

        target_data = UserDocument.get_user_target_data(user_uid=user_uid, session=self.session)
        logger.info("Target data %s", target_data)
        self.sp = SponsoredContent(user_uuid=self.user_uuid)

    def check_indices_exist(self, index_list):
        search_index = []
        for i in index_list:
            if self.es_client.indices.exists(index=i):
                search_index.append(i)
            else:
                logger.error(f"Warning - index {i} is configured, but does not exist in es")
        return search_index

    def sync_metadata(self, feed_kind, feed_name, search_results_total=0, end_of_feed=False, hidden=False):
        fb.set_fs_client(collections=['userFeedDB'], documents=[self.user_uid])
        feed = FeedMetaDataDocument(
            feed_type_uuid=self.feed_type_uuid,
            feedTypeUuid=self.feed_type_uuid,
            feed_kind=feed_kind.name.lower() if feed_kind else "",
            feedKind=feed_kind.name.lower() if feed_kind else "",
            search_results_total=search_results_total,
            searchResultsTotal=search_results_total,
            endOfFeed=end_of_feed,
            feed_name=feed_name,
            feedName=feed_name,
            hidden=hidden,
        )
        meta = UserFeedMetaDataDocument(
            user_uid=self.user_uid,
            userUid=self.user_uid,
            user_uuid=self.user_uuid,
            userUuid=self.user_uuid,
            feeds={feed.feed_type_uuid: feed}
        )
        fb.set(meta.dict(exclude_none=True), merge=True)


class GeneratePreview(GenerateFeed):
    page_size = 50
    feed_language = Locale.EN_US

    def __init__(self, feed_type_uuid):
        super().__init__(feed_type_uuid=feed_type_uuid)
        self.q = Search(using=es, index=es_settings.cases_alias)
        self.default_filters = [
            Q("terms", language__keyword=Locale.get_lang_code_filter(allow_languages=self.feed_language)),
            Q("term", caseState='APPROVED'),
            Q("range", publishedAt={'lte': 'now/d'})]

        self.feed_preview_new_enabled = False
        self.feed_preview_trending_enabled = False
        self.configure_firestore()

    def configure_firestore(self):
        self.firestore_metadata = fb.set_fs_client(collections=['referenceData'], documents=['feeds'])
        self.firestore_feed = fb.fs_client.collection('referenceData').document('feeds').collection(self.feed_type_uuid)
        self.batch = fb.fs_client.batch()
        self.batch_count = 0

    def _execute_search(self):
        response = self.q.execute()
        for item in response.hits[:self.page_size]:
            yield item.to_dict()
        return StopIteration

    def _append_image_cases(self, items: List[Dict], minimum_with_image: int):
        """
        Ensures items includes at least `minimum_with_image` number of cases that contain an image.  Cases are appended
        to items if required.
        """
        image_count = len([x for x in items if x.get('media') and x['media'][0].get('type') == 'image'])

        if image_count < minimum_with_image:
            required_length = len(items) + minimum_with_image - image_count
            self.q = self.q.filter("nested", path='media', query=Q("term", media__type='image'))
            for item in self._execute_search():
                if len(items) == required_length:
                    return
                if item not in items:
                    items.append(item)

    def generate_new_items(self, minimum_with_image: int = 4):
        """
        Generates a query sorted by publishedAt date and returns a list of ids
        :return:
        """
        self.q = self.q.query(Q("bool", filter=self.default_filters)) \
            .exclude("exists", field="groupUuid") \
            .sort("-publishedAt")

        logger.info("Executing query for new items %s", self.q.to_dict())
        items = list(self._execute_search())
        if minimum_with_image > 0:
            self._append_image_cases(items=items, minimum_with_image=minimum_with_image)
        return [x.get('caseUuid') for x in items]

    def generate_topic_items(self, topic: Topic, minimum_with_image: int = 4):
        def _reformat_sort_fields():
            """
            Converts sort fields in the format of 'createdAt:desc' to the format expected by elastic dsl.
            """
            for sf in topic.sort_fields:
                if isinstance(sf, dict):
                    yield sf
                elif isinstance(sf, str) and sf.count(':') == 1:
                    if sf.endswith('desc'):
                        yield '-' + sf.split(':')[0]
                    else:
                        yield sf.split(':')[0]

        self.q = self.q.exclude("exists", field="groupUuid")

        if topic.specialty_uuids:
            self.q = self.q.filter("terms", specialtyUuids=[str(s) for s in topic.specialty_uuids])
        if topic.topic_language:
            self.q = self.q.filter("terms", language__keyword=Locale.get_lang_code_filter(topic.topic_language))
        if topic.expire_query:
            self.q = self.q.query(topic.expire_query)
        if topic.filter_query:
            self.q = self.q.query(topic.filter_query)

        if topic.state_filter:
            self.q = self.q.filter("term", caseState=topic.state_filter)
        else:
            self.q = self.q.filter("term", caseState='APPROVED')

        if topic.sort_fields:
            sort_fields = _reformat_sort_fields()
            if sort_fields:
                self.q = self.q.sort(*sort_fields)
            else:
                logger.error("Failed to parse %s into proper sort format", topic.sort_fields)
        else:
            self.q = self.q.sort("-publishedAt")

        logger.info("Executing query for topic items %s", self.q.to_dict())
        items = list(self._execute_search())
        if minimum_with_image > 0:
            self._append_image_cases(items=items, minimum_with_image=minimum_with_image)
        return [x.get('caseUuid') for x in items]


class GenerateDataFeed(GenerateFeed):
    page_size = 10
    feed_language = Locale.EN_US
    sort_fields = ["-publishedAt"]

    def __init__(self):
        self.q = Search(using=es, index=es_settings.cases_alias)
        self.default_filters = [
            Q("terms", language__keyword=Locale.get_lang_code_filter(allow_languages=self.feed_language)),
            Q("term", caseState='APPROVED'),
            Q("range", publishedAt={'lte': 'now/d'})]
        super().__init__(feed_type_uuid=None)

    def _execute_search(self, query, sort=False):
        logger.error("Executing search %s", json.dumps(query.to_dict()))
        if sort:
            query = query.sort(*self.sort_fields)

        response = query.execute()
        for item in response.hits[:self.page_size]:
            f = FeedCard.feed_card(feed_item=item.to_dict())
            if f:
                yield f
            else:
                continue

    def get_onboarding_cases(self, user_uuid):
        user_specialties = UserDocument.get_made_for_you_specialties(user_uuid=user_uuid)

        if user_specialties:
            query = self.q.query(Q("bool",
                                   should=[Q("terms", specialtyUuids=user_specialties)],
                                   must_not=[Q("exists", field="groupUuid"),
                                             Q("term", isAnonymous=True),
                                             Q("term", caseClassification=CaseClassification.NONMEDICAL.value)],
                                   filter=self.default_filters))
            return self._execute_search(query=query)
        query = self.q.query(Q("bool",
                               filter=self.default_filters,
                               must_not=[Q("exists", field="groupUuid"),
                                         Q("term", isAnonymous=True),
                                         Q("term", caseClassification=CaseClassification.NONMEDICAL.value)]))
        return self._execute_search(sort=True, query=query)
