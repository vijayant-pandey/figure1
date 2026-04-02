from ._connection import redis_conn

sponsored_content_available_set_key = "sponsoredcontent:available"


def _split_list(items, max_chunk):
    split_list = [items[i * max_chunk:(i + 1) * max_chunk]
                  for i in range((len(items) + max_chunk - 1) // max_chunk)]
    for i in split_list:
        yield i


def write_list(items, list_key, max_chunk=10000):
    p = redis_conn.pipeline()
    for list_item in _split_list(items, max_chunk):
        p.lpush(list_key, *list_item)
    p.execute()


def write_set(items, set_key, max_chunk=10000):
    p = redis_conn.pipeline()
    for list_item in _split_list(items, max_chunk):
        p.sadd(set_key, *list_item)
    p.execute()
