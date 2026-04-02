import logging

from figure1.core import es
from figure1.configuration import es_settings
from figure1.common.models.db import User
from figure1.common.helpers import FeedCard
from figure1.common.types import FirebaseAction


class FirebaseUserSavedCasesDB:
    def __init__(self, path, user_uuid, case_uuid):
        self._path = path
        self.case_uuid = case_uuid
        self.user_uuid = user_uuid

    def set(self, es_client):

        feed_item = es_client.get(index=es_settings.cases_alias, id=self.case_uuid)
        doc = FeedCard.feed_card(feed_item=feed_item, user_uuid=self.user_uuid)
        case_type = doc.get('caseType')
        if isinstance(case_type, str):
            if case_type == 'clinical_moments' or case_type == 'cme':
                feed_card = doc.get('feedCardMedia')
                if feed_card:
                    media = [{'url': feed_card.get('media_url')}]
                    doc.update({'media': media})
        if doc:
            return [{
                "path": self._path,
                "action": FirebaseAction.SET,
                "data": doc
            }]
        else:
            return []

    @property
    def delete(self):
        return [{
            "path": self._path,
            "action": FirebaseAction.DELETE
        }]

    @staticmethod
    def sync(firebase_db, row_uuid, action, columns=None, session=None):
        logger = logging.getLogger(__name__)
        user_uuid = str(row_uuid[0])
        case_uuid = str(row_uuid[1])
        user = User.get_user_by_uuid(user_uuid=user_uuid, session=session, raise_exception=True)

        path = firebase_db.collection('userSavedCasesDB') \
            .document(user.user_uid) \
            .collection('all') \
            .document(case_uuid) \
            .path
        sync_object = FirebaseUserSavedCasesDB(path=path,
                                               user_uuid=user_uuid,
                                               case_uuid=case_uuid)

        if action is FirebaseAction.SET:
            return sync_object.set(es_client=es)
        elif action is FirebaseAction.DELETE:
            return sync_object.delete
        else:
            logger.error(f"Unsupported action for row={row_uuid}, action={action}")
            return []
