import logging

from elasticsearch.exceptions import NotFoundError
from firebase_admin.auth import delete_user
from firebase_admin.exceptions import NotFoundError as FireBaseNotFound

from figure1.common.elasticsearch import add_or_update_user
from figure1.common.elasticsearch import delete_es_user
from figure1.common.helpers import UserDocument
from figure1.common.models.firebase.groups_db import FirestoreGroupMember
from figure1.common.types import CmeDegreeTypeOptions
from figure1.common.types import FirebaseAction
from figure1.core import firebase_app
from figure1.core import FirestoreSyncBase
from figure1.exceptions import UserNotFound


class UserDBSync(FirestoreSyncBase):
    """
    As implemented, this is temporary. The full sync should run through this model, but I don't have time to
    convert it at the moment.
    """
    userUid: str
    degreeType: CmeDegreeTypeOptions

    class Config:
        use_enum_values = True

    def generate_firestore_document(self, session=None) -> dict:
        return dict(degreeType=self.degreeType)

    @property
    def firestore_doc_reference(self):
        return self.fs_client.collection('usersDB').document(self.userUid)


class FirebaseUsersDB:
    def __init__(self, path, user, columns=None):
        self._path = path
        self._user = user
        self._columns = columns

    def set(self):
        return [{
            "path": self._path,
            "action": FirebaseAction.SET,
            "data": self._user
        }]

    def set_followers(self):
        logging.info(f"Set followers")
        return {
            "path": self._path,
            "action": FirebaseAction.SET,
            "data": self._user,
        }

    @property
    def delete(self):
        return [{
            "path": self._path,
            "action": FirebaseAction.DELETE
        }]

    @staticmethod
    def sync(firebase_db, user_uuid, action, columns=None, session=None):
        logger = logging.getLogger(__name__)
        try:
            elasticsearch_user_detail = UserDocument.elasticsearch_user_detail(user_uuid=user_uuid,
                                                                               session=session)
        except UserNotFound:
            return None

        if action is FirebaseAction.DELETE:
            u = UserDocument.get_deleted_user(user_uuid=user_uuid, session=session)
            if not u:
                return None
            path = firebase_db.collection('usersDB').document(str(u.user_uid)).path
            try:
                delete_es_user(user_uuid=user_uuid)
            except NotFoundError:
                logger.info("User not found in elasticsearch")
            if str(u.user_uid):
                try:
                    delete_user(uid=str(u.user_uid), app=firebase_app())
                except FireBaseNotFound:
                    logger.error("No user in firebase with this uid")
            else:
                return None
            sync_object = FirebaseUsersDB(path=path, user=u, columns=columns)
            return sync_object.delete
        elif action is FirebaseAction.SET:
            try:
                u = UserDocument.get_full_profile(user_uuid=user_uuid, session=session)
                if u.get('verificationUpdatedAt'):
                    u.pop('verificationUpdatedAt')
                if u.get('verificationCreatedAt'):
                    u.pop('verificationCreatedAt')

            except UserNotFound:
                return []
            add_or_update_user(user_uuid=user_uuid, user_detail=elasticsearch_user_detail)
            if not u.get('userUid'):
                return []

            if not u.get('userHiddenFromSearch'):
                for each_group in u.get('groups', []):
                    FirestoreGroupMember(group_uuid=each_group['groupUuid'], user_uuid=u['userUuid']) \
                        .firestore_write(session=session)

            path = firebase_db.collection('usersDB').document(u.get('userUid')).path
            sync_object = FirebaseUsersDB(path=path, user=u, columns=columns)
            return sync_object.set()
        else:
            logger.error(f"Unsupported action for row={user_uuid}, action={action}")
            return []
