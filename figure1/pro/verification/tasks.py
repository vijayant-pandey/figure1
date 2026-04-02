import logging
from typing import Optional

from google.cloud.firestore_v1 import Client
from requests import HTTPError, ConnectionError
from sqlalchemy.orm import Session

from .model_methods import add_npi_data_from_json, verify_user
from figure1.exceptions import InvalidAPIResponse, NPIAPIError
from figure1.core import celery_app, FirebaseTaskBase
from figure1.common.types import VerificationStatus
from figure1.common.npi import NpiAPI
from figure1.common.npi.api import NPIRequest
from figure1.common.npi.api import NPIResponseItem
from figure1.common.models.db import User, SpecialtyTaxonomyMap, SpecialtyTreeV2

logger = logging.getLogger(__name__)


@celery_app.task(bind=True,
                 base=FirebaseTaskBase,
                 name='figure1.service.get_npi_info',
                 autoretry_for=(HTTPError, ConnectionError, NPIAPIError))
def get_npi_info(self, npi=None, user_uuid=None):
    request = NPIRequest(number=npi)
    r = NpiAPI.get_info(request)

    if r.result_count < 1:
        logger.error("No npi number found, un-verifying user")
        verify_user(user_uuid=user_uuid,
                    verification_status=VerificationStatus.PENDING_MANUAL_VERIFICATION,
                    session=self.session)
    elif r.result_count > 1:
        logger.error("Returned more than 1 result (%d)", r.result_count)
        raise InvalidAPIResponse(npi=npi, user_uuid=user_uuid)
    else:
        add_npi_data_from_json(npi_data=r.results[0],
                               npi_number=npi,
                               user_uuid=user_uuid,
                               session=self.session)
        _sync_npi_data(fs=self.fs_client,
                       user_uuid=user_uuid,
                       npi_data=r.results[0],
                       session=self.session)


@celery_app.task(bind=True,
                 base=FirebaseTaskBase,
                 name='figure1.backend.delete_npi_info',
                 autoretry_for=(HTTPError, ConnectionError))
def delete_npi_info(self, user_uuid=None):
    _sync_delete_npi_data(fs=self.fs_client,
                          user_uuid=user_uuid,
                          session=self.session)


def _sync_npi_data(fs: Client,
                   user_uuid: str,
                   npi_data: NPIResponseItem,
                   session: Session):
    def _capitalize_if_not_none(value: str):
        return value.capitalize() if value else None

    user = User.get_user_by_uuid(user_uuid=user_uuid, session=session, raise_exception=True)

    tree_uuid = None
    tree = None
    if npi_data.taxonomies:
        for taxonomy in npi_data.taxonomies:
            if taxonomy.primary is True:
                map = SpecialtyTaxonomyMap.q.get(taxonomy.code)
                if map:
                    tree_uuid = str(map.specialty_tree_uuid)
                    full_model = SpecialtyTreeV2.q.get((tree_uuid, 'tree',))
                    if full_model:
                        tree = full_model.as_dict()
                else:
                    logger.error("No match found for taxonomy code %s", taxonomy.code)
    doc = fs.collection('usersDB') \
        .document(user.user_uid) \
        .collection('npi') \
        .document(str(npi_data.number))

    doc.set({
        'firstName': _capitalize_if_not_none(npi_data.basic.first_name),
        'middleName': _capitalize_if_not_none(npi_data.basic.middle_name),
        'lastName': _capitalize_if_not_none(npi_data.basic.last_name),
        'npiNumber': npi_data.number,
        'treeUuid': tree_uuid,
        'tree': tree,
    })


def _sync_delete_npi_data(fs: Client, user_uuid: str, session: Session):
    user = User.get_user_by_uuid(user_uuid=user_uuid, session=session, raise_exception=True)
    collct = fs.collection('usersDB') \
        .document(user.user_uid) \
        .collection('npi')

    for each_doc in collct.list_documents():
        each_doc.delete()
