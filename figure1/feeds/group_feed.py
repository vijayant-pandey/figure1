import logging
import json
from typing import Dict
from figure1.common.types import Locale
from figure1.common.models.db import GroupFeedDescriptor, FeedKind
from figure1.exceptions import GroupFeedNotFound
from .feed_base import BaseFeed, FeedResultSet, ElasticsearchQueryGenerator

logger = logging.getLogger('figure1.userfeed.group')


class GroupFeed(BaseFeed):
    def __init__(self, session, es_client, user_uid, feed_type_uuid, feed_language=Locale.EN_US):
        super().__init__(session=session,
                         es_client=es_client,
                         user_uid=user_uid,
                         feed_type_uuid=feed_type_uuid,
                         feed_language=feed_language)
        self.group_feed = session.query(GroupFeedDescriptor).get(feed_type_uuid)
        if not self.group_feed:
            raise GroupFeedNotFound(return_code=404,
                                    user_uuid=self.user_uuid,
                                    feed_type_uuid=feed_type_uuid,
                                    msg="Group feed not found")
        self.group_feed = self.group_feed.as_dict()
        self.sort_fields = ["publishedAt:desc"]
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
            self.sync_metadata(feed_kind=FeedKind.GROUP,
                               feed_name=self.group_feed.get('name'),
                               end_of_feed=True,
                               search_results_total=0,
                               hidden=self.group_feed.get('hidden'))
            return feed_resultset.dict()

        q.apply_case_state_filter(case_state=self.group_feed['stateFilter'])

        # If this is a preview feed, then make sure sponsored content is disabled
        if self.group_feed['stateFilter'] == 'SC_REVIEW':
            self.sponsored_content_enabled = False
        else:
            q.apply_date_filter()

        if self.feed_search_filters:
            q.apply_user_filters(search_filters=self.feed_search_filters)

        # If the language is set by the group, use that one.
        if self.group_feed['language']:
            for lang in Locale.__members__:
                if Locale[lang].code == self.group_feed['language']:
                    q.apply_language_filter(allow_languages=Locale[lang])
        else:
            q.apply_language_filter(allow_languages=self.feed_language)

        if self.group_feed['specialtyUuids']:
            if len(self.group_feed['specialtyUuids']) >= 1024:
                logger.error("Too many specialtyUuids for term search, truncating list")
                q.add_must(search_must={"terms": {"specialtyUuids": [*self.group_feed['specialtyUuids'][:1023]]}})
            else:
                q.add_must(search_must={"terms": {"specialtyUuids": self.group_feed['specialtyUuids']}})
                logger.info("Filtering on specialtyUuids: %s", json.dumps(self.group_feed['specialtyUuids']))

        if self.group_feed['expireQuery']:
            q.add_filter(search_filter=self.group_feed['expireQuery'])
            logger.info("Expiring items based on: %s", json.dumps(self.group_feed['expireQuery']))

        if self.group_feed['filterQuery']:
            q.add_filter(search_filter=self.group_feed['filterQuery'])
            logger.info("Custom group filter being applied: %s", json.dumps(self.group_feed['filterQuery']))

        if self.group_feed['sortFields']:
            self.sort_fields = self.group_feed['sortFields']
            logger.info("Custom group sort being applied: %s", json.dumps(self.group_feed['sortFields']))
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

        self.sync_metadata(feed_kind=FeedKind.GROUP,
                           feed_name=self.group_feed.get('name'),
                           end_of_feed=self.feed_config.get_eof(),
                           search_results_total=items.get('hits', {}).get('total', {}).get('value', 0),
                           hidden=self.group_feed.get('hidden', False))
        return self.sync_feed_items(feed_data=populated, return_only=return_feed_items, user_uuid=self.user_uuid)
