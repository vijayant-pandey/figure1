class FeedException(Exception):
    def __init__(self, *args, **kwargs):
        self.feed_type_uuid = kwargs.get('feed_type_uuid', '')
        self.user_uuid = kwargs.get('user_uuid', '')
        self.rc = kwargs.get('return_code', 500)
        self.msg = kwargs.get('msg', 'General Feed Exception raised')


class FeedNotFound(FeedException):
    def __init__(self, *args, **kwargs):
        self.feed_type_uuid = kwargs.get('feed_type_uuid', '')
        self.user_uuid = kwargs.get('user_uuid', '')
        self.rc = kwargs.get('return_code', 404)
        self.msg = kwargs.get('msg', 'Feed not found')

    def __str__(self):
        return "Feed uuid %s, user %s, msg %s" % (self.feed_type_uuid, self.user_uuid, self.msg)

    def __repr__(self):
        return "Feed uuid %s, user %s, rc %s, msg %s" % (self.feed_type_uuid, self.user_uuid, self.rc, self.msg)

    def as_dict(self):
        return {
            'return_code': self.rc,
            'error': self.msg,
            'feed_type_uuid': self.feed_type_uuid,
            'user_uuid': self.user_uuid
        }


class TopicFeedNotFound(FeedNotFound):
    def __str__(self):
        return "Unable to find Topic %s, user %s, msg %s" % (self.feed_type_uuid, self.user_uuid, self.msg)

    def __repr__(self):
        return "Unable to find Topic %s, user %s, rc %s msg %s" \
               % (self.feed_type_uuid, self.user_uuid, self.rc, self.msg)


class MFYNotFound(FeedNotFound):
    def __str__(self):
        return "Unable to find MFY %s, user %s, msg %s" % (self.feed_type_uuid, self.user_uuid, self.msg)

    def __repr__(self):
        return "Unable to find MFY %s, user %s, rc %s, msg %s" \
               % (self.feed_type_uuid, self.user_uuid, self.rc, self.msg)


class EverythingNotFound(FeedNotFound):
    def __str__(self):
        return "Unable to find Everything %s, user %s, msg %s" % (self.feed_type_uuid, self.user_uuid, self.msg)

    def __repr__(self):
        return "Unable to find Everything %s, user %s, rc %s, msg %s" \
               % (self.feed_type_uuid, self.user_uuid, self.rc, self.msg)


class GroupFeedNotFound(FeedNotFound):
    def __str__(self):
        return "Unable to find Group %s, user %s, msg %s" % (self.feed_type_uuid, self.user_uuid, self.msg)

    def __repr__(self):
        return "Unable to find Group %s, user %s, rc %s, msg %s" \
               % (self.feed_type_uuid, self.user_uuid, self.rc, self.msg)


class SearchException(FeedException):
    def __str__(self):
        return "Search of feed %s for user %s failed with message %s" % (self.feed_type_uuid, self.user_uuid, self.msg)

    def __repr__(self):
        return "Search of feed %s for user %s failed, rc %s,  message %s" \
               % (self.feed_type_uuid, self.user_uuid, self.rc, self.msg)

    def as_dict(self):
        return {
            'return_code': self.rc,
            'error': self.msg,
            'feed_type_uuid': self.feed_type_uuid,
            'user_uuid': self.user_uuid
        }
