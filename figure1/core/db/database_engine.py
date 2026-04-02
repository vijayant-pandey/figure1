import asyncio
import contextlib
from functools import wraps
import logging
from figure1.configuration import app_settings
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker as sa_sessionmaker, Session, scoped_session
from sqlalchemy import event

logging.getLogger('sqlalchemy.pool')
logger = logging.getLogger('figure1.db.core')
logger.info("Initializing database pool")

# #########################################################################################################
# SQL Alchemy Setup
# #########################################################################################################

if app_settings.database_dsn:
    url_or_dsn = app_settings.database_dsn
    connection_string = app_settings.database_dsn
else:
    url_or_dsn = URL.create(
        "postgresql",
        username=app_settings.db_username,
        password=app_settings.db_password.get_secret_value(),
        host=app_settings.db_host,
        port=app_settings.db_port,
        database=app_settings.db_database,
    )
    connection_string = url_or_dsn.render_as_string(hide_password=False)

global_engine = create_engine(url_or_dsn, pool_size=10, max_overflow=40, echo=False)
session_factory = sa_sessionmaker(bind=global_engine)
global_session = scoped_session(session_factory)

# delete friendly mapper args (shuts down SA warnings about how many rows have been deleted, which are generally
# inaccurate anyway)
mapper_args = dict(confirm_deleted_rows=False)

total_session_connections = 0


@event.listens_for(global_engine, 'checkout')
def new_session_added(dbapi_connection, connection_record, connection_proxy):
    global total_session_connections
    total_session_connections += 1
    logger.debug(f"Total sessions checked out {total_session_connections}")


@event.listens_for(global_engine, 'checkin')
def new_session_removed(dbapi_connection, connection_record):
    global total_session_connections
    total_session_connections -= 1
    logger.debug(f"Total sessions checked out {total_session_connections}")


@contextlib.contextmanager
def create_session() -> Session:
    """
    Contextmanager that will return a session.
    """
    session = global_session()
    try:
        logger.debug("Returning session")
        yield session
        logger.debug("Committing session")
        
        # Check for read-only mode before committing
        if app_settings.read_only_dev_mode:
            read_only_logger = logging.getLogger('figure1.read_only_mode')
            read_only_logger.warning("READ-ONLY MODE: Blocked session.commit() operation")
            session.rollback()  # Rollback instead of commit
            return
            
        session.commit()
        logger.debug("Session committed, returning")

    except Exception as e:
        logger.error("Passing through error after session rollback")
        logger.exception("pass-through exception", exc_info=e)
        session.rollback()
        raise


def remove_scoped_session():
    """
    This is intended to be used at the very end of a request.
    :return:
    """
    logger.debug("Removing session")
    global_session.remove()


def managed_session(func):
    """
    Function decorator that provides a global_session if it isn't provided.
    If you want to reuse a global_session or run the function as part of a
    database transaction, you pass it to the function, if not this wrapper
    will create one and close it for you.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        arg_session = 'session'

        func_params = func.__code__.co_varnames
        func_name = func.__name__
        session_in_args = arg_session in func_params and func_params.index(arg_session) < len(args)
        session_in_kwargs = arg_session in kwargs

        if session_in_kwargs or session_in_args:
            # session was already provided by the ultimate method caller
            logger.debug(f"Session provided to {func_name}, return immediately")
            if not asyncio.iscoroutinefunction(func):
                # func isn't a coroutine so invoke it normally
                return func(*args, **kwargs)
            else:
                # func is a coroutine, so invoke it asynchronously
                async def execute():
                    return await func(*args, **kwargs)

                return execute()
        else:
            # session wasn't provided by ultimate method caller, so provide one
            logger.debug(f"No session provided to {func_name}, creating a new one")
            if not asyncio.iscoroutinefunction(func):
                # func isn't a corutine so invoke it normally
                with create_session() as session:
                    kwargs[arg_session] = session
                    logger.debug(f"Session returned to func {func_name}")
                    return func(*args, **kwargs)
            else:
                # func is a corutine, so invoke it asynchronously
                async def execute():
                    with create_session() as session:
                        kwargs[arg_session] = session
                        return await func(*args, **kwargs)

                return execute()

    return wrapper


@managed_session
def bulk_insert(cls, records, session=None):
    """
    Handles bulk inserts. Records are written in chunks of 10,000
    :param cls: the mapping class
    :param records: the records to write
    :param session: the session to use
    :return: number of records added
    """
    if app_settings.read_only_dev_mode:
        read_only_logger = logging.getLogger('figure1.read_only_mode')
        read_only_logger.warning(f"READ-ONLY MODE: Blocked bulk_insert() operation on {cls.__name__}")
        return 0
        
    add_count = len(records)

    while len(records) > 0:
        chunk = records[:1000]
        records = records[1000:]
        session.bulk_insert_mappings(cls, chunk)

    return add_count


@managed_session
def bulk_update(cls, records, session=None):
    """
    Handles bulk inserts. Records are written in chunks of 10,000
    :param cls: the mapping class
    :param records: the records to write
    :param session: the session to use
    :return: number of records updated
    """
    if app_settings.read_only_dev_mode:
        read_only_logger = logging.getLogger('figure1.read_only_mode')
        read_only_logger.warning(f"READ-ONLY MODE: Blocked bulk_update() operation on {cls.__name__}")
        return 0
        
    update_count = len(records)

    while len(records) > 0:
        chunk = records[:1000]
        records = records[1000:]
        session.bulk_update_mappings(cls, chunk)

    return update_count
