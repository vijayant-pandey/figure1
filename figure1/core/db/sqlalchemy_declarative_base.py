import datetime
import json
import logging

import pytz
from sqlalchemy import Column, func, MetaData
from sqlalchemy import DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.mutable import MutableDict, Mutable
from sqlalchemy.orm.session import object_session
from sqlalchemy.types import TypeDecorator, CHAR
from sqlalchemy import DDL, event

# must use naming convention since alembic doesn't recognize anonymous constraints
from .database_engine import managed_session, create_session, global_session

logger = logging.getLogger('figure1.read_only_mode')

create_ltree_extension = DDL("CREATE EXTENSION IF NOT EXISTS ltree")
create_crypto_extension = DDL("CREATE EXTENSION IF NOT EXISTS pgcrypto")
create_uuidossp_extension = DDL('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

meta = MetaData(naming_convention={"ix": "ix_%(column_0_label)s",
                                   "uq": "uq_%(table_name)s_%(column_0_name)s",
                                   "ck": "ck_%(table_name)s_%(constraint_name)s",
                                   "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
                                   "pk": "pk_%(table_name)s"
                                   })

event.listen(meta, 'before_create', create_crypto_extension)
event.listen(meta, 'before_create', create_ltree_extension)
event.listen(meta, 'before_create', create_uuidossp_extension)

Base = declarative_base(metadata=meta)
Base.q = global_session.query_property()

CASCADE = 'all, delete-orphan'


class CRUDException(Exception):
    pass


class CRUDObject:
    """
    Subclasses of CRUDObject get save and delete for free
    """

    def save(self):
        """
        Saves an ORM object to the database. If the object is not bound to a global_session,
        then the global global_session is used.
        :return: None
        """
        from figure1.configuration import app_settings
        
        if app_settings.read_only_dev_mode:
            logger.warning(f"READ-ONLY MODE: Blocked save() operation on {self.__class__.__name__}")
            return
            
        session = object_session(self)

        if session is None:
            # object not bound to global_session, so add it to the global global_session
            with create_session() as session:
                session.add(self)
                session.commit()
        else:
            # commit to the database
            session.commit()

    def delete(self):
        """
        If the CRUDObject also inherits from HasDeleteTime then the obejct is marked as deleted. Otherwise, the object
        is actually deleted from the database. Objects must be bound to a global_session to be deleted.
        :return:
        """
        from figure1.configuration import app_settings
        
        if app_settings.read_only_dev_mode:
            logger.warning(f"READ-ONLY MODE: Blocked delete() operation on {self.__class__.__name__}")
            return
            
        if isinstance(self, HasDeleteTime):
            # instance of HasDeleteTime, so just mark it deleted
            self.mark_deleted()
            return

        session = object_session(self)

        if session is None:
            raise CRUDException(
                'Object not bound to a global_session. Object must be bound to a global_session to be deleted.')

        # not an instance of HasDeleteTime, so hard delete
        session.delete(self)


class HasCreateTime(object):
    """Add created_at"""
    created_at = Column(DateTime(timezone=True), default=func.now(), nullable=False, index=True)


class HasCreateEventTime(HasCreateTime):
    """created_at + event_at"""
    event_at = Column(DateTime(timezone=True), nullable=False, index=True)


class HasCreateUpdateTime(HasCreateTime):
    """created_at + updated_at"""
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now(),
                        nullable=False, index=True)


class HasDeleteTime(object):
    """deleted_at"""
    deleted_at = Column(DateTime(timezone=True), default=None, nullable=True, index=True)

    @property
    def is_deleted(self):
        return self.deleted_at is not None

    def mark_deleted(self):
        from figure1.configuration import app_settings
        
        if app_settings.read_only_dev_mode:
            logger.warning(f"READ-ONLY MODE: Blocked mark_deleted() operation on {self.__class__.__name__}")
            return
            
        self.deleted_at = datetime.datetime.now(tz=pytz.utc)


class HasCreateUpdateDeleteTime(HasCreateUpdateTime, HasDeleteTime):
    """created_at + updated_at + deleted_at"""


class TextToID:
    """
    Simple table for mapping text to an ID for more efficient storage
    (i.e. 1 ==> "Foo", 2 ==> "Bar", etc)
    """
    # columns
    id = Column(Integer, primary_key=True)
    text_value = Column(String, nullable=False)

    # methods
    @staticmethod
    @managed_session
    def id_to_text(cls, session=None):
        types = session.query(cls).all()
        return {t.id: t.text_value for t in types}

    @staticmethod
    @managed_session
    def text_to_id(cls, session=None):
        types = session.query(cls).all()
        return {t.text_value: t.id for t in types}


class JsonDict(TypeDecorator):
    impl = CHAR

    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(JSON())
        else:
            return dialect.type_descriptor(String())

    def process_bind_param(self, value, dialect):
        if dialect.name == 'postgresql':
            return value
        if value and value != {}:
            return '"%s"' % json.dumps(value)
        return None

    def process_result_value(self, value, dialect):
        if dialect.name == 'postgresql':
            # TODO: remove the fallback json.loads after everyone blows away test data.
            # We were originally storing double-serialized json strings here.
            # This bug was fixed on 2014-12-10 and does not effect production data.
            if isinstance(value, str):
                return json.loads(value.strip('"'))

            if value is None:  # json.loads("null") == None
                return {}
            return value

        if value:
            return json.loads(value.strip('"'))
        return {}


class UpdatableMutableDict(MutableDict):
    """Just like SQLAlchemy MutableDict, but also notices updates!
    """

    def update(self, *args, **kwargs):
        for k, v in dict(*args, **kwargs).items():
            self.__setitem__(k, v)

    @classmethod
    def coerce(cls, key, value):
        if not isinstance(value, UpdatableMutableDict):
            if isinstance(value, dict):
                return UpdatableMutableDict(value)
            return Mutable.coerce(key, value)
        else:
            return value


# Make JSONType notice changes:
# http://docs.sqlalchemy.org/en/rel_0_9/orm/extensions/mutable.html
UpdatableMutableDict.associate_with(JsonDict)
