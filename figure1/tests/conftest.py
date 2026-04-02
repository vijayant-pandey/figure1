import os
import string
import uuid
from random import choice
import pytest
from alembic import command
from alembic.config import Config
from flask_jwt_extended import create_access_token
from sqlalchemy import text, create_engine
from sqlalchemy.orm import sessionmaker as sa_sessionmaker, scoped_session
from sqlalchemy_utils import create_database, database_exists, drop_database
from celery import group
from celery.canvas import Signature
from figure1.admin.reference_data import *
from figure1.admin.reference_data.load_blocked_usernames import load_bad_words
from figure1.core import configure_environment, firestore_client, global_session
from figure1.core.db.database_engine import global_engine
from figure1.core.db.sqlalchemy_declarative_base import meta
from figure1.common.elasticsearch import create_new_case_index, \
    case_bulk_updates, \
    switch_cases_index, \
    add_or_update_user, \
    cases_startup, \
    create_new_users_index, \
    switch_user_index_alias
from figure1.core import es
from figure1.common.models.db import CaseSpecialtyV2, MeshTerms, SpecialtyV2, SpecialtyTreeV2
from figure1.common.helpers import WordMatcher
from figure1.common.types import CaseState, SpecialtyTreeModel
from figure1.run import initialize_test_app
from figure1.tests.utils.case import create_test_case
from figure1.tests.utils.user import create_test_user
from figure1.tools import load_topic_data, load_specialty_data
from figure1.configuration import app_settings, test_settings, es_settings
from figure1.tools.specialties import handle_csv_upload

DATABASE = os.path.join(os.path.dirname(__file__), './data')
ALEMBIC_CONFIG = os.path.abspath(os.path.join(os.path.dirname(__file__), './test_alembic.ini'))
alembic_cfg = Config(ALEMBIC_CONFIG)


@pytest.fixture(scope='session')
def celery_parameters():
    return {
        'strict_typing': False,
    }


@pytest.fixture(scope='session')
def celery_worker_parameters():
    return {
        'worker_concurrency': 8,
        'queues': ('frontend', 'backend', 'service', 'celery')
    }


@pytest.fixture(scope='session')
def celery_enable_logging():
    return True


@pytest.fixture(scope='session')
def celery_worker_pool():
    return 'prefork'


@pytest.fixture(scope='session')
def celery_config():
    if app_settings.sentinel_enabled:
        broker_url = ";".join(app_settings.redis_url)
        broker_transport_options = {'master_name': "redismaster"}
        result_backend_transport_options = {'master_name': "redismaster", 'visibility_timeout': 3600}
        return dict(broker_url=broker_url,
                    result_backend=broker_url,
                    broker_transport_options=broker_transport_options,
                    result_backend_transport_options=result_backend_transport_options,
                    accept_content=['pickle', 'json'],
                    allowed_serializers=['pickle', 'json'],
                    task_serializer='pickle',
                    result_serializer='pickle',
                    )

    if os.environ.get("CIRCLECI"):
        return {
            'broker_url': 'redis://127.0.0.1:6379',
            'result_backend': 'redis://127.0.0.1:6379',
            'accept_content': ['pickle', 'json'],
            'allowed_serializers': ['pickle', 'json'],
            'task_serializer': 'pickle',
            'result_serializer': 'pickle',
        }
    else:
        return {
            'broker_url': 'redis://redis:6379',
            'result_backend': 'redis://redis:6379',
            'accept_content': ['pickle', 'json'],
            'allowed_serializers': ['pickle', 'json'],
            'task_serializer': 'pickle',
            'result_serializer': 'pickle',
        }


@pytest.fixture(scope='session')
def celery_includes():
    return [
        'figure1.admin.migrate.cases.tasks',
        'figure1.admin.migrate.users.tasks',
        'figure1.admin.moderation.cases',
        'figure1.admin.reference_data',
        'figure1.common.token_rotator',
        'figure1.pro.verification.tasks',
        'figure1.pro.feeds',
        'figure1.common.models.firebase',
        'figure1.common.firebase',
        'figure1.common.elasticsearch',
    ]


@pytest.fixture(scope="session")
def load_db():
    if app_settings.database_dsn:
        connection_string = app_settings.database_dsn
    else:
        connection_string = 'postgresql://{}:{}@{}:{}/{}'.format(app_settings.db_username,
                                                                 app_settings.db_password.get_secret_value(),
                                                                 app_settings.db_host,
                                                                 app_settings.db_port,
                                                                 app_settings.db_database)

    if database_exists(connection_string):
        drop_database(connection_string)
    create_database(connection_string)

    create_schema = meta
    create_schema.create_all(bind=global_engine)
    if test_settings.migrations:
        alembic_cfg.set_section_option('alembic', 'script_location', 'alembic')
        command.stamp(alembic_cfg, "heads")
        # The downgrade command is set to the earliest migration available in the source tree. Change this when
        # migrations are cleaned up.
        command.downgrade(alembic_cfg, "ab476aa5bda6")
        command.upgrade(alembic_cfg, "heads")

    session = global_session()
    yield session
    session.close()
    global_session.remove()
    create_schema.drop_all(bind=global_engine)


@pytest.fixture(scope="module")
def app():
    return initialize_test_app()


@pytest.fixture(scope="module")
def client(app):
    return app.test_client()


@pytest.fixture(scope="module")
def headers(app):
    with app.test_request_context():
        access_token = create_access_token('username')
    return {'Authorization': 'Bearer {}'.format(access_token)}


def _create_case(author_uuid, session):
    case, _ = create_test_case(
        author_uuid=author_uuid,
        is_paging_case=False,
        language='en',
        title="Default case",
        caption="Case Caption",
        state=CaseState.APPROVED,
        session=session)
    mt = MeshTerms()
    mt.case_uuid = case.case_uuid
    mt.approved_terms = ['Test']
    session.add(mt)
    return case


@pytest.fixture(scope="session")
def get_elasticsearch_client():
    return es


@pytest.fixture(scope="session")
def get_firestore_client():
    configure_environment()
    return firestore_client()


@pytest.fixture(scope="session")
def user_specialty(load_db) -> SpecialtyTreeModel:
    session = load_db
    return session.query(SpecialtyTreeV2) \
        .filter(SpecialtyTreeV2.profession_uuid.isnot(None),
                SpecialtyTreeV2.specialty_v2_uuid.isnot(None)) \
        .first().as_object()


@pytest.fixture(scope="session")
def create_case_index():
    startup_task = cases_startup()
    assert isinstance(startup_task.body, Signature)

    case_index_name = create_new_case_index()
    assert case_index_name is not None

    switch_cases_index(index_name=case_index_name)
    concrete_indexes = es.indices.get_alias(name=es_settings.cases_alias)
    assert case_index_name in concrete_indexes
    assert len(list(concrete_indexes.keys())) == 1

    aliases = es.indices.get_alias(index=case_index_name)

    assert es_settings.cases_alias in aliases[case_index_name]['aliases']
    assert 'newcases_public' in aliases[case_index_name]['aliases']
    assert 'newcases_sponsored_content' in aliases[case_index_name]['aliases']

    no_startup_task = cases_startup()
    assert no_startup_task is None
    yield case_index_name
    es.indices.delete(index=case_index_name)


@pytest.fixture(scope="session")
def create_user_es_index():
    index_name = create_new_users_index()
    switch_user_index_alias(index_name)
    yield index_name
    es.indices.delete(index=index_name)


@pytest.fixture(scope="session")
def specialty_data(load_db):
    session = load_db
    load_specialty_data(filename=DATABASE + '/new_specialties_v2.csv', data_type='specialty', apply=True,
                        session=session)
    load_specialty_data(filename=DATABASE + '/specialty_tree_v3.csv', data_type='tree', apply=True, session=session)
    handle_csv_upload(csv_file_path=DATABASE + '/add_professions.csv', upload_type='profession')
    handle_csv_upload(csv_file_path=DATABASE + '/add_specialties.csv', upload_type='specialty')
    handle_csv_upload(csv_file_path=DATABASE + '/add_trees.csv', upload_type='tree')
    session.commit()
    return


@pytest.fixture(scope="session")
def initialize_data(celery_session_worker, load_db, create_case_index, create_user_es_index, specialty_data):
    session = load_db
    load_bad_words(filename=DATABASE + '/bad_words.csv', session=session)
    load_topic_data(filename=DATABASE + '/topics.csv', session=session)
    group_filename = DATABASE + '/com_groups.csv'
    settings_filename = DATABASE + '/com_settings.csv'
    load_communication_groups_from_csv(filename=group_filename, session=session)
    load_communication_settings_from_csv(filename=settings_filename, session=session)

    session.flush()
    g = group(initialize_labels.si(),
              initialize_feed_types.si(),
              initialize_communication_groups.si(),
              sync_topics.si())
    g.apply()
    u = create_test_user(session=session)
    case_uuid = _create_case(author_uuid=u.user_uuid, session=session).case_uuid
    for s in session.query(SpecialtyV2).filter(SpecialtyV2.is_valid_case_tag.is_(True)).all():
        CaseSpecialtyV2.create(case_uuid=case_uuid, specialty_uuid=s.specialty_uuid, session=session)
    session.commit()
