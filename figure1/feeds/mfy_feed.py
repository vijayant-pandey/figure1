import logging
import json
from typing import Dict

from elasticsearch_dsl import Search, Q, A, SF
from figure1.common.types import Locale
from figure1.common.models.db import FeedType, FeedKind
from figure1.common.helpers import UserDocument
from figure1.exceptions import MFYNotFound
from figure1.configuration import app_settings, es_settings
from .feed_base import BaseFeed, ElasticsearchQueryGenerator
from figure1.store import UserRFYFeedConfig

logger = logging.getLogger('figure1.userfeed.mfy')


class MadeForYouFeed(BaseFeed):

    def __repr__(self):
        return json.dumps(dict(
            feed_language=self.feed_language.value.json(),
            feed_type_uuid=self.feed_type_uuid,
            user_uid=self.user_uid,
            user_interests=self.mfy_config.get_user_interests(),
            end_of_feed=self.mfy_config.get_eof(),
            cursor=self.mfy_config.get_cursor(),
        ))

    def __init__(self, session, es_client, user_uid, feed_type_uuid, feed_language=Locale.EN_US):
        super().__init__(session=session,
                         es_client=es_client,
                         user_uid=user_uid,
                         feed_type_uuid=feed_type_uuid,
                         feed_language=feed_language)

        self.sort_fields = []
        f = session.query(FeedType).filter(FeedType.feed_type_uuid == feed_type_uuid).one_or_none()
        if not f:
            raise MFYNotFound(user_uuid=self.user_uuid)
        else:
            self.mfyfeed = f
        self.first_page = False
        self.mfy_config = UserRFYFeedConfig(user_uuid=self.user_uuid, feed_type_uuid=self.feed_type_uuid)
        logger.debug("Redis mfy config %s", self.mfy_config)

    def generate_post_eof_interests(self):
        user_interests = self.get_user_interests()
        q = Search(using=self.es_client, index=es_settings.cases_alias)
        q.filter("terms", language__keyword=Locale.get_lang_code_filter(allow_languages=self.feed_language))
        q.filter("term", caseState='APPROVED')
        q.filter("range", publishedAt={'lte': 'now/d'})
        if user_interests:
            q = q.query('terms', specialtyUuids=user_interests)
            a = A('terms', field='specialtyUuids', exclude=user_interests)
            q.aggs.bucket('user_interest_aggregation', a)
        response = q.execute()
        post_eof_interests = []
        if hasattr(response.aggregations, 'user_interest_aggregation'):
            for a in response.aggregations.user_interest_aggregation.buckets:
                post_eof_interests.append(a.key)
        self.mfy_config.set_post_eof_interests(post_eof_interests)
        return post_eof_interests

    def get_user_interests(self):
        user_interests = self.mfy_config.get_user_interests()
        if user_interests:
            return user_interests
        else:
            user_interests = UserDocument.get_made_for_you_specialties(user_uuid=self.user_uuid, session=self.session)
            if user_interests:
                self.mfy_config.update_user_interests(interests=user_interests)
                return user_interests
        return []

    def generate_query(self):

        post_eof_interests = self.mfy_config.get_post_eof_interests()
        if not post_eof_interests:
            post_eof_interests = self.generate_post_eof_interests()

        q = ElasticsearchQueryGenerator()
        q = q.apply_language_filter(allow_languages=self.feed_language) \
            .apply_case_state_filter() \
            .apply_date_filter() \
            .apply_group_must_not()
        if self.feed_search_filters:
            q.apply_user_filters(search_filters=self.feed_search_filters)

        q.apply_score_functions()
        user_interests = self.get_user_interests()
        if user_interests:
            q = q.add_should(search_should={"terms": {"specialtyUuids": user_interests, "boost": 1.2}})
        if post_eof_interests:
            q = q.add_should(search_should={"terms": {"specialtyUuids": post_eof_interests, "boost": 1.0}})
        logger.info("Saved query %s", q.to_json())
        self.mfy_config.write_feed_query(q.to_json())
        return q

    def generate_feed(self, skip_delete=False):
        """
        If the list of user specialties is in elasticsearch, use that. Otherwise, grab
        the User from the helper function and pull out the specialties. If that fails,
        then use the everything index

        :return:
        """
        self.first_page = True
        self.sp.regenerate_sponsored_content()
        self.generate_query()
        if self.mfy_config.get_eof():
            self.mfy_config.set_cursor(0)
            self.mfy_config.set_eof_cursor(0)
            self.mfy_config.unset_eof()

        if self.feed_search_filters:
            self.mfy_config.set_cursor(0)
            self.mfy_config.set_eof_cursor(0)
        if not skip_delete:
            self.delete_feed_documents()
        logger.debug("Sponsored content object %s", self.sp)
        return {}

    def get_feed_items(self, return_feed_items=False) -> Dict:
        """
        Gets available feed items. Returns an empty dict if the end of the feed is reached.

        :param return_feed_items: If true, feed items are returned directly instead of being written to firestore.
                                  Metadata is always written to firestore, regardless of the value of this param.
        :return:
        """
        if self.mfy_config.get_eof():
            return {}
        cursor = self.mfy_config.get_cursor()
        q = self.mfy_config.get_feed_query()

        if self.first_page is False:
            self.feed_preview_trending_enabled = False
            self.feed_preview_new_enabled = False

        items = self.execute_search(q=q, sort_fields=self.sort_fields, page_size=self.page_size,
                                    cursor=cursor)

        total_hits = items.get('hits', {}).get('total', {}).get('value', 0)
        result_ids = [i.get("_id", {}) for i in items.get('hits', {}).get('hits', [])]

        self.mfy_config.increment_cursor(increment_by=len(result_ids))

        if total_hits <= self.mfy_config.get_cursor():
            self.mfy_config.set_cursor(total_hits)
            self.mfy_config.set_eof()

        if self.sponsored_content_enabled:
            injected_results = self.sp.inject_id_only(result_ids, skip_first_insert=self.first_page)
            populated = self.populate_feed_items(items=injected_results, last_page=self.mfy_config.get_eof())
        else:
            populated = self.populate_feed_items(items=result_ids, last_page=self.mfy_config.get_eof())

        self.sync_metadata(feed_kind=FeedKind.MADE_FOR_YOU,
                           feed_name=self.mfyfeed.name,
                           end_of_feed=self.mfy_config.get_eof(),
                           search_results_total=items.get('hits', {}).get('total', {}).get('value', 0))
        return self.sync_feed_items(feed_data=populated, return_only=return_feed_items, user_uuid=self.user_uuid)
