import logging
import random
import string
import datetime
from elasticsearch.exceptions import RequestError

from figure1.configuration import es_settings
from figure1.common.models.db import ElasticsearchToken
from figure1.core import managed_session, firestore_client, configure_environment, TaskBase, celery_app

from figure1.core import es

logger = logging.getLogger('elasticsearch.tasks')

max_retry_count = es_settings.connect_retry_count
retry_wait = es_settings.connect_retry_wait

elasticsearch_hosts = es_settings.hosts
elasticsearch_cloud_id = es_settings.cloud_id
elasticsearch_api_key = es_settings.api_key


@celery_app.task(name='figure1.service.elasticsearch_key_rotator')
def elasticsearch_key_rotation():
    if not elasticsearch_cloud_id:
        logger.warning("Elasticsearch token authentication is disabled for non-cloud deployments")
        return
    do_refresh_token()


@celery_app.task(name='figure1.service.elasticsearch_user_rotator', autoretry_for=(RequestError,), max_retries=3)
def elasticsearch_credential_startup():
    if not elasticsearch_cloud_id:
        logger.warning("Elasticsearch credentials are not used for non-cloud deployments")
        return
    try:
        create_role()
        create_user()
    except RequestError as req_err:
        logger.error(f"Caught error {req_err} creating user")
        raise RequestError


def create_role(role_name='read_public_index'):
    es.security.put_role(name=role_name, body={
        "indices": [
            {
                "names": ["public_*"],
                "privileges": ["read"]
            }
        ]
    })


@managed_session
def create_user(user_name='public_user', session=None):
    def generate_password(length=30):
        letters = string.ascii_letters
        return ''.join(random.choice(letters) for i in range(length))

    pw = generate_password()
    try:
        es.security.put_user(username=user_name, body={
            "roles": ["read_public_index"],
            "password": pw
        })
        tk = es.security.get_token(body={
            "grant_type": "password",
            "username": user_name,
            "password": pw
        })
    except RequestError as req_err:
        logger.error(f"Failed to create user and generate token {req_err}")
        raise RequestError
    ElasticsearchToken.set_refresh_token(session=session,
                                         old_refresh_token=tk['refresh_token'],
                                         new_refresh_token=tk['refresh_token'])
    do_refresh_token(session=session)


@managed_session
def do_refresh_token(session=None):
    t = ElasticsearchToken.get_refresh_token(session=session)
    if not t:
        elasticsearch_credential_startup.apply_async(countdown=10)
        logger.error("No refresh token found, called credential startup")
        return
    try:
        new_token = es.security.get_token(body={
            "grant_type": "refresh_token",
            "refresh_token": t['refresh_token']
        })
    except RequestError as re:
        logger.error(f"Failed to refresh token - fall back to regenerate user {re}")
        elasticsearch_credential_startup.delay()
        raise RequestError

    ElasticsearchToken.set_refresh_token(session=session, old_refresh_token=t['refresh_token'],
                                         new_refresh_token=new_token['refresh_token'])
    expires_time = datetime.datetime.utcnow() + datetime.timedelta(seconds=1200)

    configure_environment()
    fs = firestore_client()

    doc = fs.collection('configurationDB').document('elasticsearchConfig')
    update_config = {
        'elasticsearchAuth': {
            'access_token': new_token['access_token'],
            'expiration': expires_time.strftime('%s')
        }
    }

    es_doc = doc.get()
    if es_doc:
        es_doc = es_doc.to_dict()
        if es_doc and 'elasticsearchCloudId' not in es_doc:
            update_config.update({'elasticsearchCloudId': elasticsearch_cloud_id})
    else:
        update_config.update({'elasticsearchCloudId': elasticsearch_cloud_id})
    doc.set(update_config, merge=True)


class ElasticsearchTaskBase(TaskBase):

    @property
    def es_client(self):
        logger.info("Returning es connector")
        return es
