import enum
import uuid
from sqlalchemy import String, Index, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, backref

from .group_models import Groups
from figure1.common.types import Locale
from sqlalchemy import Column, ARRAY, Text, Integer, Boolean, JSON, ForeignKey, DateTime
from figure1.core import managed_session, Base, HasCreateUpdateDeleteTime


class FeedKind(enum.Enum):
    EVERYTHING = 'everything'
    MADE_FOR_YOU = 'made_for_you'
    SEARCH = 'search'
    TOPIC = 'topic'
    GROUP = 'group'


class FeedType(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "f_feed_type"
    feed_type_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), nullable=False, primary_key=True, index=True)
    kind = Column(Enum(FeedKind), nullable=False, index=True)
    name = Column(String, nullable=True, index=True)
    label = Column(String, nullable=False, index=True, unique=True)
    __table_args__ = (Index('idx_f_feed_type_kind_name', 'kind', 'name', unique=True),)

    @staticmethod
    def create(kind, label, name, skip_commit=False, session=None):
        t = session.query(FeedType) \
            .filter(FeedType.kind == kind, FeedType.label == label) \
            .one_or_none()
        if t:
            t.name = name
            session.add(t)
            return t

        t = FeedType()
        t.feed_type_uuid = uuid.uuid4()
        t.kind = kind
        t.name = name
        t.label = label
        session.add(t)
        session.flush()
        return t

    def as_dict(self):
        return {
            'feedTypeUuid': str(self.feed_type_uuid),
            'kind': self.kind.name.lower(),
            'name': self.name,
            'label': self.label,
        }

    @staticmethod
    def get_everything_uuid(session):
        t = session.query(FeedType).filter(FeedType.kind == FeedKind.EVERYTHING).one()
        return str(t.feed_type_uuid)

    @staticmethod
    def get_made_for_you_uuid(session):
        t = session.query(FeedType).filter(FeedType.kind == FeedKind.MADE_FOR_YOU).one()
        return str(t.feed_type_uuid)

    @staticmethod
    def get_feed_from_type_uuid(feed_type_uuid, session):
        return session.query(FeedType).get(feed_type_uuid)

    @staticmethod
    def get_name_for_uuid(feed_type_uuid, session):
        feed = FeedType.get_feed_from_type_uuid(feed_type_uuid=feed_type_uuid, session=session)
        if feed:
            return feed.name
        return None

    @staticmethod
    def get_kind_for_uuid(feed_type_uuid, session):
        feed = FeedType.get_feed_from_type_uuid(feed_type_uuid=feed_type_uuid, session=session)
        if feed:
            return feed.kind
        return None


class FeedPreview(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "f_feed_previews"

    feed_type_uuid = Column(UUID(as_uuid=True), ForeignKey(FeedType.feed_type_uuid), primary_key=True)
    last_run_time = Column(DateTime(timezone=True), default=None)
    feed_type = relationship("FeedType", backref="preview")

    @staticmethod
    def add_public_feeds(session):
        for feed in session.query(Topic).filter(Topic.hidden.is_(False), Topic.display_order < 1000).all():
            fp = FeedPreview()
            fp.feed_type_uuid = feed.feed_type_uuid
            fp.last_run_time = None
            session.merge(fp)

        feed = session.query(FeedType).filter(FeedType.kind == FeedKind.EVERYTHING).one_or_none()
        if feed:
            fp = FeedPreview()
            fp.feed_type_uuid = feed.feed_type_uuid
            fp.last_run_time = None
            session.merge(fp)


class Topic(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "f_topic"

    feed_type_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    name = Column(Text, nullable=False)
    label = Column(Text, nullable=False, index=True, unique=True)
    specialty_uuids = Column(ARRAY(UUID(as_uuid=True)), default=[], nullable=False)
    filter_query = Column(JSON, nullable=True)
    sort_fields = Column(JSON, nullable=True)
    expire_query = Column(JSON, nullable=True)
    state_filter = Column(Text, default='APPROVED', nullable=True)
    display_order = Column(Integer, nullable=False)
    hidden = Column(Boolean, nullable=False)
    topic_language = Column(Text, default=Locale.EN_US.code)

    feed_type = relationship('FeedType',
                             backref=backref('topic', uselist=False, viewonly=True),
                             viewonly=True,
                             foreign_keys=feed_type_uuid,
                             primaryjoin="(FeedType.feed_type_uuid==Topic.feed_type_uuid)")

    @staticmethod
    def create_or_update(feed_type_uuid,
                         name,
                         label,
                         specialty_uuids,
                         session,
                         hidden,
                         state_filter='APPROVED',
                         display_order=1000,
                         topic_language=Locale.EN_US.code,
                         filter_query={},
                         expire_query={},
                         sort_fields=[]):

        clean_tl = Locale.EN_US.code
        for tl in Locale.__members__:
            if Locale[tl].code == topic_language:
                clean_tl = Locale[tl].code
            if tl == topic_language:
                clean_tl = Locale[topic_language].code

        t = Topic()
        t.feed_type_uuid = feed_type_uuid
        t.label = label
        t.hidden = hidden
        t.name = name
        t.display_order = display_order
        t.specialty_uuids = specialty_uuids
        t.filter_query = filter_query
        t.expire_query = expire_query
        t.sort_fields = sort_fields
        t.state_filter = state_filter
        t.topic_language = clean_tl
        return session.merge(t)

    def as_dict(self):
        return {
            'feedTypeUuid': str(self.feed_type_uuid),
            'name': self.name,
            'label': self.label,
            'specialtyUuids':
                list(map(lambda s: str(s), self.specialty_uuids)) if self.specialty_uuids else [],
            'filterQuery': self.filter_query,
            'sortFields': self.sort_fields,
            'expireQuery': self.expire_query,
            'displayOrder': self.display_order,
            'hidden': self.hidden,
            'stateFilter': self.state_filter,
            'topicLanguage': self.topic_language
        }

    @staticmethod
    @managed_session
    def get_all_topics_as_dict(session=None, show_hidden=True):
        q = session.query(Topic)
        if not show_hidden:
            q = q.filter(Topic.hidden.is_(False))
        for t in q.all():
            yield t.as_dict()


class GroupFeedDescriptor(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "f_group_feed"

    feed_type_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    group_uuid = Column(UUID(as_uuid=True), ForeignKey(Groups.group_uuid))
    name = Column(Text, nullable=False)
    label = Column(Text, nullable=False, index=True, unique=True)
    specialty_uuids = Column(ARRAY(UUID(as_uuid=True)), default=[], nullable=False)
    filter_query = Column(JSON, nullable=True)
    sort_fields = Column(JSON, nullable=True)
    expire_query = Column(JSON, nullable=True)
    state_filter = Column(Text, default='APPROVED', nullable=True)
    display_order = Column(Integer, nullable=False)
    hidden = Column(Boolean, nullable=False)
    language = Column(Text, default=Locale.EN_US.code)

    feed_type = relationship('FeedType',
                             backref=backref('group_feed', uselist=False, viewonly=True),
                             viewonly=True,
                             foreign_keys=feed_type_uuid,
                             primaryjoin="(FeedType.feed_type_uuid==GroupFeedDescriptor.feed_type_uuid)")
    group = relationship('Groups', backref=backref('group_feed', viewonly=True))

    def as_dict(self):
        return {
            'feedTypeUuid': str(self.feed_type_uuid),
            'groupUuid': str(self.group_uuid),
            'name': self.name,
            'label': self.label,
            'specialtyUuids':
                list(map(lambda s: str(s), self.specialty_uuids)) if self.specialty_uuids else [],
            'filterQuery': self.filter_query,
            'sortFields': self.sort_fields,
            'expireQuery': self.expire_query,
            'displayOrder': self.display_order,
            'hidden': self.hidden,
            'stateFilter': self.state_filter,
            'language': self.language
        }
