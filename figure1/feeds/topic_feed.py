import logging
import json
from typing import Dict
from figure1.common.types import Locale
from figure1.common.models.db import Topic, FeedKind
from figure1.exceptions import TopicFeedNotFound
from .feed_base import BaseFeed, FeedResultSet, ElasticsearchQueryGenerator

logger = logging.getLogger('figure1.userfeed.topic')


class TopicFeed(BaseFeed):
    def __init__(self, session, es_client, user_uid, feed_type_uuid, feed_language=Locale.EN_US):
        super().__init__(session=session,
                         es_client=es_client,
                         user_uid=user_uid,
                         feed_type_uuid=feed_type_uuid,
                         feed_language=feed_language)
        self.topic = session.query(Topic).get(feed_type_uuid)
        if not self.topic:
            raise TopicFeedNotFound(return_code=404,
                                    user_uuid=self.user_uuid,
                                    feed_type_uuid=feed_type_uuid,
                                    msg="Topic feed not found")
        self.topic = self.topic.as_dict()
        self.sort_fields = []
        self.feed_preview_new_enabled = False
        self.feed_preview_trending_enabled = False
        self.first_page = False

    def generate_feed(self, skip_delete=False):
        self.first_page = True
        self.feed_config.set_cursor(0)
        self.feed_config.unset_eof()
        if not skip_delete:
            self.delete_feed_documents()
        self.sp.regenerate_sponsored_content()
        return {}

    def get_feed_items(self, return_feed_items=False) -> Dict:
        """
        Generate search query then execute the search
        Updates the cursor at the end, and returns the search results.
        Returns an empty dict if the endOfFeed marker is set

        :param return_feed_items: If true, feed items are returned directly instead of being written to firestore.
                                  Metadata is always written to firestore, regardless of the value of this param.
        :return: Dict
        """
        feed_resultset = FeedResultSet(user_uid=self.user_uid, feed_type_uuid=self.feed_type_uuid)
        q = ElasticsearchQueryGenerator()
        if self.feed_config.get_eof():
            logger.error("End of feed already set, return empty set")
            feed_resultset.end_of_feed = True
            self.sync_metadata(feed_kind=FeedKind.TOPIC,
                               feed_name=self.topic.get('name'),
                               end_of_feed=True,
                               search_results_total=0,
                               hidden=self.topic.get('hidden'))
            return feed_resultset.dict()

        q.apply_case_state_filter(case_state=self.topic['stateFilter'])
        q.apply_group_must_not()

        # If this is a preview feed, then make sure sponsored content is disabled
        if self.topic['stateFilter'] == 'SC_REVIEW':
            self.sponsored_content_enabled = False
        else:
            q.apply_date_filter()

        if self.feed_search_filters:
            q.apply_user_filters(search_filters=self.feed_search_filters)

        # If the language is set by the topic, use that one.
        if self.topic['topicLanguage']:
            for lang in Locale.__members__:
                if Locale[lang].code == self.topic['topicLanguage']:
                    q.apply_language_filter(allow_languages=Locale[lang])
        else:
            q.apply_language_filter(allow_languages=self.feed_language)

        if self.topic['specialtyUuids']:
            if len(self.topic['specialtyUuids']) >= 1024:
                logger.error("Too many specialtyUuids for term search, truncating list")
                q.add_must(search_must={"terms": {"specialtyUuids": [*self.topic['specialtyUuids'][:1023]]}})
            else:
                q.add_must(search_must={"terms": {"specialtyUuids": self.topic['specialtyUuids']}})
                logger.info("Filtering on specialtyUuids: %s", json.dumps(self.topic['specialtyUuids']))

        if self.topic['expireQuery']:
            q.add_filter(search_filter=self.topic['expireQuery'])
            logger.info("Expiring items based on: %s", json.dumps(self.topic['expireQuery']))

        if self.topic['filterQuery']:
            q.add_filter(search_filter=self.topic['filterQuery'])
            logger.info("Custom topic filter being applied: %s", json.dumps(self.topic['filterQuery']))

        if self.topic['sortFields']:
            self.sort_fields = self.topic['sortFields']
            logger.info("Custom topic sort being applied: %s", json.dumps(self.topic['sortFields']))
        else:
            q.apply_score_functions()

        items = self.execute_search(q=q,
                                    sort_fields=self.sort_fields,
                                    page_size=self.page_size,
                                    cursor=self.feed_config.get_cursor())

        total_hits = items.get('hits', {}).get('total', {}).get('value', 0)
        result_ids = [i.get("_id", {}) for i in items.get('hits', {}).get('hits', [])]
        if len(result_ids):
            self.feed_config.increment_cursor(increment_by=len(result_ids))

        if total_hits <= self.feed_config.get_cursor():
            self.feed_config.set_cursor(total_hits)
            self.feed_config.set_eof()

        if self.sponsored_content_enabled:
            injected_results = self.sp.inject_id_only(result_ids, skip_first_insert=self.first_page)
            populated = self.populate_feed_items(items=injected_results, last_page=self.feed_config.get_eof())
        else:
            populated = self.populate_feed_items(items=result_ids, last_page=self.feed_config.get_eof())

        self.sync_metadata(feed_kind=FeedKind.TOPIC,
                           feed_name=self.topic.get('name'),
                           end_of_feed=self.feed_config.get_eof(),
                           search_results_total=items.get('hits', {}).get('total', {}).get('value', 0),
                           hidden=self.topic.get('hidden', False))
        return self.sync_feed_items(feed_data=populated, return_only=return_feed_items, user_uuid=self.user_uuid)
