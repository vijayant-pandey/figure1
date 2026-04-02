"""
Common functionality needed for anything reaching out to firebase
"""
import logging
import requests
from typing import Tuple, Optional
from figure1.configuration import FirebaseEnvSettings
from pydantic import BaseModel, HttpUrl, Field, validator, ValidationError
from figure1.configuration import app_settings
import firebase_admin
from firebase_admin import firestore
from firebase_admin.credentials import Certificate
from google.oauth2 import service_account
from google.cloud.firestore import Client
from google.cloud import translate_v2
from google.auth.credentials import AnonymousCredentials, Credentials
from googleapiclient import discovery

logger = logging.getLogger('figure1.firestore_configuration')


class FirestoreAuthenticationModel(FirebaseEnvSettings):
    auth_uri: HttpUrl = 'https://accounts.google.com/o/oauth2/auth'
    token_uri: HttpUrl = 'https://accounts.google.com/o/oauth2/token'
    auth_provider_x509_cert_url: HttpUrl = 'https://www.googleapis.com/oauth2/v1/certs'
    type: str = 'service_account'


def firebase_app():
    return GoogleApi.get_firestore_admin_client()


def firestore_client():
    return GoogleApi.get_firestore_client()


def translate_client():
    return GoogleApi.get_translation_client()


def configure_environment():
    GoogleApi.configure()


class GoogleApi:
    _firestore_client = None
    _firestore_admin_client = None
    _translation_client = None
    _credentials: Credentials = None
    _admin_sdk_credentials: Certificate = None
    _default_database_name = 'default'
    _environment_name = None
    _is_disabled = False
    _firestore_settings = None
    _auth_scopes = [
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/firebase.database",
        "https://www.googleapis.com/auth/cloud-platform",
        "https://www.googleapis.com/auth/datastore",
        "https://www.googleapis.com/auth/cloud-healthcare",
    ]

    def __init__(self):
        GoogleApi.configure()

    def __repr__(self):
        return f'GoogleAPI<environment={self._environment_name}, firestore_settings={self._firestore_settings}>'

    @classmethod
    def configure(cls):
        try:
            GoogleApi._generate_credentials()
        except ValidationError as v:
            logger.critical("Failed to configure google authentication - %s", v.errors())
            cls._is_disabled = True

    @classmethod
    def get_firestore_client(cls):
        if cls._is_disabled:
            return None
        options = {'projectID': f'https://{cls._environment_name}.firebaseio.com/'}
        if cls._firestore_client:
            return cls._firestore_client

        if not cls._admin_sdk_credentials:
            GoogleApi._generate_credentials()

        if cls._admin_sdk_credentials:
            app = firebase_admin.initialize_app(cls._admin_sdk_credentials, options=options)
            cls._firestore_client = firestore.client(app)
        return cls._firestore_client

    @classmethod
    def get_firestore_admin_client(cls):
        if cls._is_disabled:
            return None
        if cls._firestore_settings.get('rtdb_url'):
            databaseURL = f"https://{cls._firestore_settings.get('rtdb_url')}.firebaseio.com/"
        else:
            databaseURL = f'https://{cls._environment_name}.firebaseio.com/'
        options = dict(databaseURL=databaseURL)

        if cls._firestore_admin_client:
            return cls._firestore_admin_client

        if not cls._admin_sdk_credentials:
            GoogleApi._generate_credentials()

        cls._firestore_admin_client = firebase_admin.initialize_app(cls._admin_sdk_credentials,
                                                                    options=options,
                                                                    name=f'{cls._environment_name}-admin')
        return cls._firestore_admin_client

    @classmethod
    def get_translation_client(cls):
        """
        Get a configured translation client or return None if the API is disabled.
        :return: Tra
        """
        if cls._is_disabled:
            return None
        if app_settings.translation_api_enabled:
            if cls._translation_client:
                return cls._translation_client
            if cls._credentials:
                cls._translation_client = translate_v2.Client(credentials=cls._credentials)
                return cls._translation_client
            else:
                GoogleApi.configure()
                return GoogleApi.get_translation_client()
        else:
            return None

    @classmethod
    def is_production(cls):
        if cls._environment_name:
            return True if cls._environment_name == 'figure1-admin' else False
        return False

    @classmethod
    def is_disabled(cls):
        return cls._is_disabled

    @classmethod
    def _generate_credentials(cls):
        if cls._is_disabled:
            return None
        auth_model = cls._configure_environment()
        if auth_model is True:
            cls._credentials = AnonymousCredentials()
            cls._firestore_client = Client(credentials=cls._credentials, project='dummy-project-id')
            return

        cls._environment_name = auth_model.project_id
        cls._credentials = service_account.Credentials.from_service_account_info(auth_model.dict(),
                                                                                 scopes=cls._auth_scopes)
        cls._admin_sdk_credentials = firebase_admin.credentials.Certificate(auth_model.dict())

    @classmethod
    def _configure_environment(cls):
        firebase_config = FirebaseEnvSettings()
        cls._firestore_settings = firebase_config.dict()

        if firebase_config.firestore_emulator_host:
            return True

        return FirestoreAuthenticationModel(**cls._firestore_settings)

    def get_discovery_client(self, api_version='v1', service_name='healthcare'):
        if not self._credentials:
            GoogleApi._generate_credentials()
        return discovery.build(service_name, api_version, credentials=self._credentials)


class HealthCareApi(GoogleApi):
    _api_version = 'v1'
    _service_name = 'healthcare'
    _location = 'us-central1'

    def __init__(self, location=None, project=None):
        super().__init__()
        if location:
            HealthCareApi._location = location
        if project:
            self.nlp_services_name = f'projects/{project}/locations/{HealthCareApi._location}/services/nlp'
        else:
            self.nlp_services_name = f'projects/{self._environment_name}' \
                                     f'/locations/{HealthCareApi._location}/services/nlp'
        self.client = self.get_discovery_client(api_version=self._api_version, service_name=self._service_name)

    def __repr__(self):
        return f'HealthCareAPI<location={self._location}, services_name={self.nlp_services_name}>'

    def _execute(self, req):
        resp = req.execute()
        return resp

    def _parse_response(self, resp) -> Tuple[str, str]:
        """
        The response is broken into two parts, the first part contains the parse results, and the second contains
        all of the vocabulary codes mentioned in the first part.
        We parse the first part to find problems, then look up the vocabulary codes that we found.
        :param resp:
        :return:
        """
        logger.debug("Response from HC API: %s", resp)
        problem_list = []
        procedure_list = []
        medicine_list = []
        for m in resp.get('entityMentions', []):
            if m.get('type') == 'PROBLEM':
                if m.get('confidence', 0) >= 0.9:
                    for le in m.get('linkedEntities', []):
                        problem_list.append(le.get('entityId'))
            if m.get('type') == 'PROCEDURE':
                if m.get('confidence', 0) >= 0.9:
                    for le in m.get('linkedEntities', []):
                        procedure_list.append(le.get('entityId'))
            if m.get('type') == 'MEDICINE':
                if m.get('confidence', 0) >= 0.9:
                    for le in m.get('linkedEntities', []):
                        medicine_list.append(le.get('entityId'))

        for ent in resp.get('entities', []):
            mesh_code = None
            if ent.get('entityId') in problem_list:
                logger.debug("Problem Entity: %s", ent)
                for vocab_code in ent.get('vocabularyCodes', []):
                    if vocab_code.startswith('MSH'):
                        mesh_code = vocab_code.split('/')[1]
                        break
                if mesh_code is None:
                    continue
                yield mesh_code, 'PROBLEM'
            if ent.get('entityId') in procedure_list:
                logger.debug("Procedure Entity: %s", ent)
                for vocab_code in ent.get('vocabularyCodes', []):
                    if vocab_code.startswith('MSH'):
                        mesh_code = vocab_code.split('/')[1]
                        break
                if mesh_code is None:
                    continue
                yield mesh_code, 'PROCEDURE'
            if ent.get('entityId') in medicine_list:
                logger.debug("Medicine Entity: %s", ent)
                for vocab_code in ent.get('vocabularyCodes', []):
                    if vocab_code.startswith('MSH'):
                        mesh_code = vocab_code.split('/')[1]
                        break
                if mesh_code is None:
                    continue
                yield mesh_code, 'MEDICINE'

    def analyze_text(self, text="cardiac arrest") -> Tuple[str, str]:
        req = self.client \
            .projects() \
            .locations() \
            .services() \
            .nlp() \
            .analyzeEntities(nlpService=self.nlp_services_name, body={"documentContent": text})
        resp = self._execute(req)
        return self._parse_response(resp)
