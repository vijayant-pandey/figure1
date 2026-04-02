import os
import logging
from sqlalchemy import event
from sqlalchemy import exc
from .sqlalchemy_declarative_base import Base
from .database_engine import managed_session
from .database_engine import global_engine
from .database_engine import global_session

from .database_engine import create_session

from .database_engine import mapper_args
from .database_engine import connection_string
from .database_engine import remove_scoped_session

from .sqlalchemy_declarative_base import HasCreateTime
from .sqlalchemy_declarative_base import HasCreateUpdateDeleteTime
from .sqlalchemy_declarative_base import HasCreateUpdateTime

logger = logging.getLogger('figure1.db.startup')


@event.listens_for(global_engine, "connect")
def _connect(dbapi_connection, connection_record):
    """
    This and the _checkout listener have to be here for tests to pass - I don't know why at this point
    :param dbapi_connection:
    :param connection_record:
    :return:
    """
    connection_record.info['pid'] = os.getpid()


@event.listens_for(global_engine, "checkout")
def _checkout(dbapi_connection, connection_record, connection_proxy):
    pid = os.getpid()
    logger.debug("Checking out connection for pid %s, records %s", pid, connection_record.info)
    if connection_record.info['pid'] != pid:
        connection_record.connection = connection_proxy.connection = None
        raise exc.DisconnectionError(
            "Connection record belongs to pid %s, "
            "attempting to check out in pid %s" %
            (connection_record.info['pid'], pid))
