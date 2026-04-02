import operator
import json
import logging
from typing import List, Set
from random import randint
from figure1.configuration import app_settings
from redis.exceptions import ResponseError
from ._connection import redis_conn
from ._utils import sponsored_content_available_set_key

logger = logging.getLogger('figure1.store.user')


class NewCaseHandler:

    def __init__(self):
        self.new_queue = "case:new:queue"
        self.new_case_sent_queue = "case:new:queue:sent"

    def get_sent_cases(self) -> Set:
        return redis_conn.smembers(self.new_case_sent_queue)

    def is_case_sent(self, key) -> bool:
        return redis_conn.sismember(self.new_case_sent_queue, key)

    def case_sent(self, key):
        redis_conn.sadd(self.new_case_sent_queue, key)

    def get_new_cases_list(self):
        return redis_conn.lrange(self.new_queue, 0, -1)

    def clean_sent_queue(self):
        return redis_conn.delete(self.new_case_sent_queue)

    def remove_new_case_queues(self, case_uuid=None):
        script = """
        local case_uuid = ARGV[1]
        local case_temp_set = KEYS[1]
        local case_set = KEYS[2]
        local case_list = KEYS[3]
        for i, v in ipairs(redis.call('LRANGE', case_list, 0, -1))
        do
          redis.call('SADD', case_temp_set, v)
        end
        if case_uuid ~= nil then redis.call('SREM', case_temp_set, case_uuid) end
        redis.call('DEL', case_list)
        for i, v in ipairs(redis.call('SMEMBERS', case_temp_set))
        do
          redis.call('LPUSH', case_list, v)
          end
        redis.call('DEL', case_set, case_temp_set)
        return redis.call('LLEN', case_list)
        """
        new_queue_len = None
        if case_uuid is not None:
            new_queue_len = redis_conn.eval(script,
                                            3,
                                            "new_case_temp_set",
                                            f"case:new:{case_uuid}",
                                            self.new_queue, case_uuid)
            redis_conn.delete(f"case:new:{case_uuid}:interacted")
        else:
            for case_uuid in redis_conn.lrange(self.new_queue, 0, -1):
                new_queue_len = redis_conn.eval(script,
                                                3,
                                                "new_case_temp_set",
                                                f"case:new:{case_uuid}",
                                                self.new_queue,
                                                case_uuid)
                redis_conn.delete(f"case:new:{case_uuid}:interacted")
        return new_queue_len

    def write_new_case(self, case, users, score=1, interacted_set=None):
        """
        Given a case_uuid and a list of users, set the score
        :param case:
        :param users:
        :param score:
        :param interacted_set:
        :type interacted_set: set
        :return:
        """

        if not users:
            return
        existing = redis_conn.lrange(self.new_queue, 0, -1)
        if case not in existing:
            redis_conn.rpush(self.new_queue, case)
        case_key = f"case:new:{case}"
        interacted = f"case:new:{case}:interacted"
        p = redis_conn.pipeline()
        if interacted_set is not None:
            p.sadd(interacted, *list(interacted_set))
        for u in users:
            p.hincrby(case_key, u, score)
        p.execute()

    def get_new_case_by_user(self, user_uuid, depth=0):
        """
        Given a user_uuid, try to find a new case. Optionally takes a depth to indicate recursion level, though this
        is intended to be used internally. When the depth is greater than 5, it returns none to avoid a recursive loop.
        :param user_uuid: The user to try to find a new case for.
        :param depth:
        :return:
        """
        if depth > 5:
            return None
        new_cases = redis_conn.lrange(self.new_queue, 0, -1)
        if not new_cases:
            return None
        max_user_score = 0
        user_new_case = None
        for i in new_cases:
            score = redis_conn.hget(f"case:new:{i}", user_uuid)
            if score is None:
                continue
            if int(score) > max_user_score:
                max_user_score = int(score)
                user_new_case = i
        redis_conn.hdel(f"case:new:{user_new_case}", user_uuid)
        if user_new_case is None:
            r = randint(0, len(new_cases) - 1)
            logger.debug("List of new cases %s", new_cases)
            logger.debug("Sending random case %s to user %s", new_cases[r], user_uuid)
            user_new_case = new_cases[r]
        if not user_new_case:
            return self.get_new_case_by_user(user_uuid=user_uuid, depth=depth + 1)
        else:
            interacted_key = f"case:new:{user_new_case}:interacted"
            queue_key = user_new_case + user_uuid
            if redis_conn.sismember(interacted_key, user_uuid):
                return self.get_new_case_by_user(user_uuid=user_uuid, depth=depth + 1)
            if self.is_case_sent(queue_key):
                return self.get_new_case_by_user(user_uuid=user_uuid, depth=depth + 1)
            self.case_sent(queue_key)
            return user_new_case


class Recommended:
    user_recommended_case = 'user_recommended_case'
    user_recommended_case_sent = 'user_recommended_case_sent'
    user_regenerate_profile = 'user_recommended_profile_regen'
    user_recommended_task_lock = 'user_recommended_task_lock:'

    @classmethod
    def set_lock(cls, task_id):
        if redis_conn.exists(cls.user_recommended_task_lock + task_id):
            logger.debug("updated lock for task id %s", task_id)
            return redis_conn.expire(cls.user_recommended_task_lock + task_id, 300)
        tasks = redis_conn.keys(pattern=cls.user_recommended_task_lock + '*')
        logger.debug("Task keys found %s", tasks)
        if len(tasks) >= 3:
            logger.info("Return false, too many tasks")
            return False
        else:
            logger.debug("Setting lock for task id %s", task_id)
            return redis_conn.set(cls.user_recommended_task_lock + task_id, task_id, ex=300)

    @classmethod
    def delete_lock(cls, task_id):
        return redis_conn.delete(cls.user_recommended_task_lock + task_id)

    @classmethod
    def regenerate_user(cls, user_uuid):
        """
        Adding a user to this queue means that their profile needs to be re-generated.
        """
        redis_conn.sadd(cls.user_regenerate_profile, str(user_uuid))

    @classmethod
    def get_regenerate_user(cls, count=1):
        """
        Returns 1 or more users in a list to regenerate their profiles. This action removes the returned users.
        """
        return redis_conn.spop(cls.user_regenerate_profile, count=count)

    @classmethod
    def get_sent_user_keys(cls):
        """
        Returns a map of user_uuids -> case_uuids that have been recommended. This is only set when the recommended
        case is requested from the api.
        """
        return redis_conn.hgetall(cls.user_recommended_case_sent)

    @classmethod
    def delete_sent_user_keys(cls):
        """
        Wipe this key when the sent map has been written to the database
        """
        redis_conn.delete(cls.user_recommended_case_sent)

    @classmethod
    def set_sent_user_recommendation(cls, user_uuid, case_uuid):
        """
        When a case is sent to a user, update here.
        """
        redis_conn.hset(cls.user_recommended_case_sent, key=user_uuid, value=case_uuid)
        Recommended.regenerate_user(user_uuid=user_uuid)

    @classmethod
    def add_user_recommended_case(cls, user_uuid, case_uuid):
        """
        When a case is recommended for a user, put it in this hashmap. New entries overwrite previous ones.
        """
        redis_conn.hset(cls.user_recommended_case, key=str(user_uuid), value=str(case_uuid))

    @classmethod
    def get_user_recommended_case(cls, user_uuid):
        """
        Return a case_uuid given a user_uuid. Removes the key from the hash.
        """
        case_uuid = redis_conn.hget(name=cls.user_recommended_case, key=str(user_uuid))
        redis_conn.hdel(cls.user_recommended_case, str(user_uuid))
        return case_uuid


class UserKeyManagement:

    @staticmethod
    def delete_user_keys(user_uuid=None):
        return UserKeyManagement.delete_keys(UserKeyManagement.get_all_user_keys(user_uuid=user_uuid))

    @staticmethod
    def get_all_user_keys(user_uuid=None):
        if user_uuid:
            search_pattern = f"user:*{user_uuid}*"
        else:
            search_pattern = "user:*"
        return redis_conn.keys(pattern=search_pattern)

    @staticmethod
    def get_key_value(key):
        if not redis_conn.exists(key):
            return
        key_type = redis_conn.type(key)
        if key_type == 'string':
            return redis_conn.get(key)

        if key_type == 'list':
            if redis_conn.llen(key) > 100:
                return redis_conn.llen(key)
            return redis_conn.lrange(key, 0, -1)

        if key_type == 'set':
            if redis_conn.scard(key) > 100:
                return redis_conn.scard(key)
            return redis_conn.smembers(key)

        if key_type == 'hash':
            return redis_conn.hgetall(key)
        if key_type == 'zset':
            return "type zset not supported"
        if key_type == 'stream':
            return "type stream not supported"
        return f"Key type {key_type} is unknown"

    @staticmethod
    def delete_keys(key):
        if not key:
            return 0
        if isinstance(key, list):
            return redis_conn.unlink(*key)
        elif isinstance(key, str):
            return redis_conn.delete(key)
        else:
            return "Unknown key type passed, should be str or list"


class UserUidMap:
    def __init__(self, user_uid):
        self.user_uid_map_key = f"user:{user_uid}:map"

    def get_uuid(self):
        try:
            return redis_conn.hget(self.user_uid_map_key, 'user_uuid')
        except ResponseError:
            return {}

    def set_uuid(self, user_uuid):
        stringified_uuid = str(user_uuid)
        redis_conn.hset(self.user_uid_map_key, 'user_uuid', stringified_uuid)
        return self.get_uuid()

    def delete(self):
        redis_conn.delete(self.user_uid_map_key)


class UserDataCache:
    def __init__(self, user_uuid):
        self.user_uuid = str(user_uuid)
        self.compact_user_data_key = f"user:compact:{self.user_uuid}"

    def wipe_cache_key(self, key=None):
        if key:
            redis_conn.delete(key)

    def get_compact_user_data(self):
        try:
            r = redis_conn.get(self.compact_user_data_key)
        except ResponseError:
            redis_conn.delete(self.compact_user_data_key)
            return None

        if r:
            return json.loads(r)
        return None

    def write_compact_user_data(self, data):
        if isinstance(data, dict):
            serialize = json.dumps(data)
            redis_conn.set(self.compact_user_data_key, serialize)
            redis_conn.expire(self.compact_user_data_key, 3600)
        else:
            return None


class FeedCacheConfig:
    def __init__(self, user_uuid, feed_type_uuid):
        self.user_uuid = user_uuid
        self.feed_type_uuid = feed_type_uuid
        self.feed_views = f"user:{self.feed_type_uuid}:feed_views:{self.user_uuid}"
        self.all_feed_views = f"user:all:feed_views:{self.user_uuid}"
        self.detail_views = f"user:case_detail_views:{self.user_uuid}"
        self.cursor = f"user:{self.feed_type_uuid}:cursor:{self.user_uuid}"
        self.internal_rfy_feed_cursor = f"user:internal_rfy_feed:{self.user_uuid}"
        self.sponsored_content_views = f"user:sponsoredcontent:views:{self.user_uuid}"

    def _is_populated_list(self, handle_list):
        if isinstance(handle_list, list):
            if handle_list:
                return handle_list
        return []

    def set_feed_views(self, feed_view_items):
        logger.info("Setting feed views for items %s", feed_view_items)
        fv = self._is_populated_list(feed_view_items)
        if not fv:
            logger.info("No items for feed views")
            return
        fv_set = set(fv)
        sc_available = redis_conn.smembers(sponsored_content_available_set_key)
        logger.debug("Available sponsored content is %s", sc_available)
        sc_views = fv_set.intersection(sc_available)
        logger.debug("Intersection of available sponsored content and feed views is %s", sc_views)
        if sc_views:
            logger.debug("Writing intersection to existing sponsored content view list %s",
                         redis_conn.smembers(self.sponsored_content_views))
            redis_conn.sadd(self.sponsored_content_views, *sc_views)
            logger.debug("New sponsored content view list for user %s is %s",
                         self.user_uuid,
                         redis_conn.smembers(self.sponsored_content_views))
        redis_conn.sadd(self.feed_views, *fv)
        redis_conn.expire(self.feed_views, app_settings.feed_rfy_views_expire)

    def set_detail_views(self, detail_views):
        dv = self._is_populated_list(detail_views)
        if not dv:
            return
        redis_conn.sadd(self.detail_views, *dv)
        redis_conn.expire(self.detail_views, 604800)

    def set_eof(self):
        redis_conn.hset(self.cursor, key='eof', value='true')

    def get_eof(self):
        eof = redis_conn.hget(self.cursor, key='eof')
        if eof == 'true':
            return True
        else:
            return False

    def unset_eof(self):
        redis_conn.hset(self.cursor, key='eof', value='false')

    def get_random_seed(self):
        s = redis_conn.hget(self.cursor, key='seed')
        try:
            return int(s)
        except TypeError:
            return 0

    def set_random_seed(self, seed):
        redis_conn.hset(self.cursor, key='seed', value=seed)

    def get_cursor(self) -> int:
        c = redis_conn.hget(self.cursor, 'cursor')
        try:
            return int(c)
        except TypeError:
            return 0

    def get_eof_cursor(self) -> int:
        c = redis_conn.hget(self.cursor, 'eofcursor')
        try:
            return int(c)
        except TypeError:
            return 0

    def set_cursor(self, cursor_value):
        redis_conn.hset(self.cursor, key='cursor', value=cursor_value)
        redis_conn.expire(self.cursor, app_settings.sponsored_content_queue_generation_delay)

    def set_eof_cursor(self, cursor_value):
        redis_conn.hset(self.cursor, key='eofcursor', value=cursor_value)

    def increment_eof_cursor(self, increment_by):
        redis_conn.hincrby(self.cursor, key='eofcursor', amount=increment_by)

    def increment_cursor(self, increment_by):
        redis_conn.hincrby(self.cursor, key='cursor', amount=increment_by)


class UserFeedConfig(FeedCacheConfig):
    def __repr__(self):
        return f"UserFeedConfig:<user_uuid:{self.user_uuid},feed_type_uuid:{self.feed_type_uuid}>"

    def __init__(self, user_uuid, feed_type_uuid):
        self.feed_query_key = f"user:{feed_type_uuid}:{user_uuid}:query"
        super().__init__(user_uuid=user_uuid, feed_type_uuid=feed_type_uuid)

    def write_feed_query(self, q):
        """
        Accepts either a dict or a json string
        :param q: The query to write either as a dict or a json string
        :return: Returns None if the json string cannot be parsed or if the dict cannot be serialized.
        """
        q_json = None
        if isinstance(q, dict):
            try:
                q_json = json.dumps(q)
            except json.JSONDecodeError:
                return None

        if isinstance(q, str):
            try:
                q_dict = json.loads(q)
            except json.JSONDecodeError:
                logger.error("Failed to convert string to json")
                return None
            q_json = json.dumps(q_dict)
        if q_json:
            redis_conn.set(self.feed_query_key, q_json)
            return q_json
        else:
            return None

    def get_feed_query(self):
        """
        If a feed query has been saved, return it. Otherwise returns None.
        :return:
        """
        return redis_conn.get(self.feed_query_key)


class UserRFYFeedConfig(UserFeedConfig):
    def __repr__(self):
        return "UserRFYFeedConfig:<user_uuid:%s, mesh_terms_key:%s interests_key: %s>" % (self.user_uuid,
                                                                                          self.mesh_terms_key,
                                                                                          self.interests_key)

    def __init__(self, user_uuid, feed_type_uuid):
        super().__init__(user_uuid=user_uuid, feed_type_uuid=feed_type_uuid)
        self.user_uuid = user_uuid
        self.mesh_terms_key = f"user:rfy:mesh:{self.user_uuid}"
        self.interests_key = f"user:rfy:interests:{self.user_uuid}"
        self.post_eof_interests = f"user:rfy:interests:posteof:{self.user_uuid}"

    def get_user_interests(self) -> List:
        return list(redis_conn.smembers(self.interests_key))

    def get_post_eof_interests(self) -> List:
        return list(redis_conn.smembers(self.post_eof_interests))

    def delete_user_interests(self):
        redis_conn.delete(self.interests_key)
        redis_conn.delete(self.post_eof_interests)

    def update_user_interests(self, interests: List):
        """
        This call does not update the list, it replaces it.
        :param interests:
        :return:
        """
        interests_list = self._is_populated_list(interests)
        if not interests_list:
            return
        redis_conn.delete(self.interests_key)
        redis_conn.sadd(self.interests_key, *interests_list)

    def set_post_eof_interests(self, interests: List):
        interests_list = self._is_populated_list(interests)
        if not interests_list:
            return
        redis_conn.delete(self.post_eof_interests)
        redis_conn.sadd(self.post_eof_interests, *interests_list)


class UserSponsoredContentStore(UserDataCache):
    def __init__(self, user_uuid):
        self.user_uuid = user_uuid
        self.sponsored_content_views = f"user:sponsoredcontent:views:{self.user_uuid}"
        self.sponsored_content_queue_key = f"user:sponsoredcontent:queue:{self.user_uuid}"
        self.sponsored_content_cursor_key = f"user:sponsoredcontent:cursor:{self.user_uuid}"
        self.sponsored_content_regen_lock = f"user:sponsoredcontent:regen:{self.user_uuid}"
        self.sponsored_content_target_key = f"user:sponsoredcontent:target:{self.user_uuid}"
        super().__init__(user_uuid=user_uuid)

    def set_user_target(self, targetTree=None, targetCountry: str = None, targetIsVerified: bool = None):
        """
        Sets a hashmap in redis with these keys
        :param targetTree:
        :param targetCountry:
        :param targetIsVerified:
        :return:
        """
        targetMap = self.get_user_target()
        if targetTree and isinstance(targetTree, list):
            targetMap.update({'targetTree': targetTree})
        if targetIsVerified is True:
            targetMap.update({'targetIsVerified': True})
        elif targetIsVerified is False:
            targetMap.update({'targetIsVerified': False})
        if targetCountry:
            targetMap.update({'targetCountry': targetCountry})
        redis_conn.set(self.sponsored_content_target_key, json.dumps(targetMap))

    def get_user_target(self):
        try:
            targetMap = redis_conn.get(self.sponsored_content_target_key)
        except ResponseError:
            logger.exception("Failed to get targetMap, likely wrong key type, deleting")
            redis_conn.delete(self.sponsored_content_target_key)
            return {}
        if targetMap:
            try:
                return json.loads(targetMap)
            except json.JSONDecodeError:
                redis_conn.delete(self.sponsored_content_target_key)
        return {}

    def get_next_item(self):
        try:
            i = redis_conn.rpop(self.sponsored_content_queue_key)
            return i
        except ResponseError:
            logger.exception("Failed to get next sponsored content item")

    def get_sponcon_queue_len(self):
        return redis_conn.llen(self.sponsored_content_queue_key)

    def get_sponcon_full_queue(self):
        return redis_conn.lrange(self.sponsored_content_queue_key, 0, -1)

    def _write_sponcon_list(self, items):
        if isinstance(items, list):
            if items:

                try:
                    redis_conn.lpush(self.sponsored_content_queue_key, *items)
                except ResponseError:
                    logger.exception("Sponsored content list failed to write")

    def write_sponcon_list(self, items: List):
        existing_sponcon_list = self.get_sponcon_full_queue()
        temp_sponsored_content_list = []
        logger.debug("Got sponsored content list %s", items)
        logger.debug("Sponsored content already viewed is %s", redis_conn.smembers(self.sponsored_content_views))
        if isinstance(items, list):
            for i in items:
                if i in existing_sponcon_list:
                    continue
                if redis_conn.sismember(self.sponsored_content_views, i):
                    continue
                temp_sponsored_content_list.append(i)

        redis_conn.expire(self.sponsored_content_views, time=app_settings.sponsored_content_queue_generation_delay)
        logger.debug("Remaining list to write %s", temp_sponsored_content_list)
        if temp_sponsored_content_list:
            self._write_sponcon_list(items=temp_sponsored_content_list)
