"""
Defines the Data Model for Case, CaseComments and CaseRaw
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID

from figure1.core import managed_session, Base, HasCreateUpdateTime

from sqlalchemy.sql.expression import func


class LegacyCaseQueue(Base, HasCreateUpdateTime):
    __tablename__ = "q_legacy_case_queue"

    legacy_case_id = Column(String, nullable=False, primary_key=True)
    case_uuid = Column(UUID(as_uuid=True), nullable=True)
    follower_count = Column(Integer, nullable=True)
    likes = Column(Integer, nullable=True)
    vote_count = Column(Integer, nullable=True)
    comment_count = Column(Integer, nullable=True)
    propagated_at = Column(DateTime(timezone=True), nullable=True, index=True)

    @managed_session
    def create_or_update(self, legacy_case_id, follower_count=0, vote_count=0, comment_count=0, likes=0, session=None):
        case = session.query(LegacyCaseQueue).filter(LegacyCaseQueue.legacy_case_id == legacy_case_id).one_or_none()
        if not case:
            case = LegacyCaseQueue()
            case.legacy_case_id = legacy_case_id
        case.follower_count = follower_count
        case.vote_count = vote_count
        case.comment_count = comment_count
        case.likes = likes
        session.add(case)


class LegacyUserQueue(Base, HasCreateUpdateTime):
    __tablename__ = "q_legacy_user_queue"

    legacy_user_id = Column(String, nullable=False, primary_key=True)
    user_uuid = Column(UUID(as_uuid=True))
    last_accessed = Column(DateTime(timezone=True))
    verified = Column(Boolean, nullable=True)
    propagated_at = Column(DateTime(timezone=True), index=True)
    comm_prefs_propagated_at = Column(DateTime(timezone=True), index=True)

    @staticmethod
    def create_or_update(legacy_user_id, last_accessed, verified, session):
        user = session.query(LegacyUserQueue).get(legacy_user_id)
        if not user:
            user = LegacyUserQueue()
            user.legacy_user_id = legacy_user_id
        user.last_accessed = last_accessed
        user.verified = verified
        session.add(user)

    @staticmethod
    def get_cursor(session):
        q = session.query(LegacyUserQueue).order_by(LegacyUserQueue.legacy_user_id.asc()).first()
        return q.legacy_user_id if q else None


class ElasticSearchIndex(Base, HasCreateUpdateTime):
    __tablename__ = "es_index"

    index_name = Column(String, nullable=False, primary_key=True)
    index_alias = Column(String, nullable=False)
    is_active = Column(Boolean, default=False)
    is_complete = Column(Boolean, default=False)

    @managed_session
    def create(self, index_alias, index_name, session=None):
        idx = ElasticSearchIndex()
        idx.index_alias = index_alias
        idx.index_name = index_name
        session.add(idx)
        session.commit()

    @managed_session
    def get_active_index(self, index_alias, session=None):
        idx = session.query(ElasticSearchIndex) \
            .filter(ElasticSearchIndex.index_alias == index_alias) \
            .filter(ElasticSearchIndex.is_active.is_(True)).one_or_none()
        if idx:
            return idx.as_dict()
        return None

    @managed_session
    def set_active_index(self, index_alias, index_name, session=None):
        session.query(ElasticSearchIndex) \
            .filter(ElasticSearchIndex.index_alias == index_alias) \
            .filter(ElasticSearchIndex.is_active.is_(True)) \
            .update({'is_active': False, 'is_complete': False})

        session.query(ElasticSearchIndex) \
            .filter(ElasticSearchIndex.index_alias == index_alias) \
            .filter(ElasticSearchIndex.index_name == index_name) \
            .update({'is_active': True})
        session.commit()

    def as_dict(self):
        return {
            'index_name': str(self.index_name),
            'index_alias': self.index_alias,
            'is_active': self.is_active,
            'is_complete': self.is_complete
        }


class ElasticSearchQueue(Base, HasCreateUpdateTime):
    __tablename__ = "es_index_queue"
    case_uuid = Column(UUID(as_uuid=True), nullable=False, primary_key=True)
    index_alias = Column(String, nullable=False)
    index_name = Column(String, nullable=False, primary_key=True)
    indexed = Column(Boolean, nullable=False, default=False)

    @managed_session
    def create(self, case_uuid, index_alias, index_name, session=None):
        es = ElasticSearchQueue()
        es.case_uuid = case_uuid
        es.index_alias = index_alias
        es.index_name = index_name
        session.add(es)
        return es

    @managed_session
    def get_batch(self, index_name, batch_size=200, session=None):

        q = session.query(ElasticSearchQueue, func.text('order by created_at ASC')) \
            .filter(ElasticSearchQueue.indexed.is_(False)) \
            .filter(ElasticSearchQueue.index_name == index_name)
        if batch_size:
            q.limit(batch_size)
        for ret in q.all():
            yield ret[0].case_uuid

    @managed_session
    def update_indexed(self, index_alias, index_name, case_id_list, session=None):
        for upd in session.query(ElasticSearchQueue) \
                .filter(ElasticSearchQueue.case_uuid.in_(case_id_list)) \
                .filter(ElasticSearchQueue.index_name == index_name) \
                .filter(ElasticSearchQueue.index_alias == index_alias) \
                .all():
            upd.indexed = True
        session.commit()

    @managed_session
    def remove_complete(self, session=None):
        session.query(ElasticSearchQueue).filter(ElasticSearchQueue.indexed.is_(True)).delete()
        session.commit()

    @managed_session
    def get_queue_size(self, index_name, session=None):
        q = session.query(func.count(ElasticSearchQueue.case_uuid)) \
            .filter(ElasticSearchQueue.index_name == index_name) \
            .filter(ElasticSearchQueue.indexed.is_(False)) \
            .scalar()
        return q

    def as_dict(self):
        return {
            'case_uuid': str(self.case_uuid),
            'idx_alias': self.index_alias,
            'idx_name': self.index_name
        }
