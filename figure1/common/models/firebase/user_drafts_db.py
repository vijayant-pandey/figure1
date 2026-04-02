import logging

from figure1.common.types import FirebaseAction
from figure1.core import FirebaseClient
from figure1.configuration import app_settings
from figure1.exceptions import DraftNotFound

logger = logging.getLogger(__name__)


class FirebaseUserDraftsDB:

    @staticmethod
    def sync_draft(firebase_db, user_uid, draft_uid, case_uuid, state, rejection_reason=None):
        data = {
            "caseUuid": str(case_uuid),
            "state": state.name.lower(),
        }
        if rejection_reason:
            data['rejectionReason'] = rejection_reason.name.lower()
            data['rejectionReasonMessage'] = rejection_reason.message

        return [{
            "path": FirebaseUserDraftsDB.get_path(firebase_db=firebase_db, user_uid=user_uid, draft_uid=draft_uid),
            "action": FirebaseAction.SET,
            "data": data
        }]

    @staticmethod
    def sync_media(firebase_db, user_uid, draft_uid, media):
        return [{
            "path": FirebaseUserDraftsDB.get_path(firebase_db=firebase_db, user_uid=user_uid, draft_uid=draft_uid),
            "action": FirebaseAction.SET,
            "data": {
                "media": media
            }
        }]

    @staticmethod
    def refresh_media_upload_url(user_uid, draft_uid, upload_url, firebase_db=None):
        if not firebase_db:
            firebase_db = FirebaseClient().fs_client
        doc_path = FirebaseUserDraftsDB.get_configured_client(firebase_db=firebase_db,
                                                              user_uid=user_uid,
                                                              draft_uid=draft_uid)
        doc_path.set({"media_upload_url": upload_url,
                      "media_download_domain": app_settings.figure1_imgix_url}, merge=True)

    @staticmethod
    def sync_rejection_reason(firebase_db, user_uid, draft_uid, reason):
        return [{
            "path": FirebaseUserDraftsDB.get_path(firebase_db=firebase_db, user_uid=user_uid, draft_uid=draft_uid),
            "action": FirebaseAction.SET,
            "data": {
                "rejectionReason": reason.name.lower(),
            }
        }]

    @staticmethod
    def get_configured_client(firebase_db, user_uid, draft_uid):
        return firebase_db.collection('userDraftsDB') \
            .document(user_uid) \
            .collection('all') \
            .document(draft_uid)

    @staticmethod
    def get_path(firebase_db, user_uid, draft_uid):
        return FirebaseUserDraftsDB.get_configured_client(firebase_db=firebase_db,
                                                          user_uid=user_uid,
                                                          draft_uid=draft_uid).path

    @staticmethod
    def get_collection(firebase_db, user_uid):
        return firebase_db.collection('userDraftsDB') \
            .document(user_uid) \
            .collection('all')

    @staticmethod
    def get_draft_uid(fs_client, case_uuid, user_uid):
        collection = FirebaseUserDraftsDB.get_collection(firebase_db=fs_client,
                                                         user_uid=user_uid)
        docs = collection.where('caseUuid', '==', str(case_uuid)).get()
        if not docs:
            logger.error("Couldn't find any drafts with case_uuid: %s", case_uuid)
            raise DraftNotFound(case_uuid=case_uuid)
        if len(docs) > 1:
            logging.warning("Found multiple drafts with case_uuid: %s", case_uuid)

        return docs[0].id
