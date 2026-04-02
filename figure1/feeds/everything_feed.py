import logging
from typing import Dict
from figure1.common.types import Locale
from figure1.common.models.db import FeedKind, FeedType
from .feed_base import BaseFeed, ElasticsearchQueryGenerator

logger = logging.getLogger('figure1.userfeed.everything')


class EverythingFeed(BaseFeed):
    def __init__(self, session, es_client, user_uid, feed_type_uuid, feed_language=Locale.EN_US):
        super().__init__(session=session,
                         es_client=es_client,
                         user_uid=user_uid,
                         feed_type_uuid=feed_type_uuid,
                         feed_language=feed_language)
        self.feed = FeedType.get_feed_from_type_uuid(feed_type_uuid=feed_type_uuid, session=session)
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
        Gets available feed items. Returns an empty dict if the end of the feed is reached.

        :param return_feed_items: If true, feed items are returned directly instead of being written to firestore.
                                  Metadata is always written to firestore, regardless of the value of this param.
        :return:
        """

        if self.feed_config.get_eof():
            return {}

        q = ElasticsearchQueryGenerator()
        q.apply_case_state_filter()
        q.apply_language_filter(allow_languages=self.feed_language)
        q.apply_user_filters(search_filters=self.feed_search_filters)
        q.apply_date_filter()
        q.apply_group_must_not()

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

        logger.info("Syncing to firestore")
        self.sync_metadata(feed_kind=FeedKind.EVERYTHING,
                           feed_name=self.feed.name,
                           end_of_feed=self.feed_config.get_eof(),
                           search_results_total=items.get('hits', {}).get('total', {}).get('value', 0))
        return self.sync_feed_items(feed_data=populated, return_only=return_feed_items, user_uuid=self.user_uuid)
