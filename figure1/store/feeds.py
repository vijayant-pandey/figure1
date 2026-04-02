from uuid import UUID
import logging
from typing import Dict
from ._connection import redis_conn
from ._utils import write_set, sponsored_content_available_set_key

logger = logging.getLogger(__name__)


class IndexQueue:
    def __init__(self, index_alias, index_name):
        self.index_alias = index_alias
        self.index_name = index_name
        self.index_queue_key = f"index:{index_alias}:{index_name}"

    def get_next_item(self):
        return redis_conn.spop(self.index_queue_key)

    def get_queue_count(self, queue_key=None):
        if queue_key:
            return redis_conn.scard(queue_key)
        return redis_conn.scard(self.index_queue_key)

    def write_queue_items(self, items):
        if isinstance(items, list):
            if items:
                write_set(items, self.index_queue_key)
        if isinstance(items, str):
            return redis_conn.sadd(self.index_queue_key, items)

    def delete_queue_key(self, queue_key=None):
        if queue_key:
            redis_conn.delete(queue_key)
        else:
            redis_conn.delete(self.index_queue_key)

    def find_active_queue_key(self):
        return redis_conn.keys(f"index:{self.index_alias}:*")


class PreviewFeeds:
    def __init__(self, feed_label, feed_name, feed_type_uuid):
        self.feed_label = feed_label
        self.feed_name = feed_name
        if isinstance(feed_type_uuid, UUID):
            self.feed_type_uuid = str(feed_type_uuid)
        elif isinstance(feed_type_uuid, str):
            self.feed_type_uuid = feed_type_uuid
        else:
            raise Exception("Feed type uuid is invalid")

        self.preview_feed_key = f"feeds:preview:{feed_label}"

    def write_feed_config(self):
        feed_config_map = {
            'feed_label': self.feed_label,
            'feed_name': self.feed_name,
            'feed_type_uuid': self.feed_type_uuid
        }
        redis_conn.hset(self.preview_feed_key, mapping=feed_config_map)

    @staticmethod
    def get_preview_feed(feed_label) -> Dict:
        """
        Returns an empty dict if the key is not found. May raise ResponseError if the key is not a hash.
        If the feed is found, returns a dict with 'feed_label', 'feed_name', 'feed_type_uuid' populated.
        :param feed_label:
        :return:
        """
        preview_feed_key = f"feeds:preview:{feed_label}"
        if redis_conn.exists(preview_feed_key):
            return redis_conn.hgetall(preview_feed_key)
        return {}


class SponsoredContentCache:

    @staticmethod
    def write_sponsored_content(items):
        write_set(items, sponsored_content_available_set_key)

    @staticmethod
    def get_sponsored_content_size():
        return redis_conn.scard(sponsored_content_available_set_key)
