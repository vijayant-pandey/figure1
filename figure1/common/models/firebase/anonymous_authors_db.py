import logging
from typing import List

from google.cloud import firestore
from google.cloud.firestore_v1 import DocumentReference
from pydantic.fields import Optional

from figure1 import celery_app
from figure1.common.models.db import Case
from figure1.common.models.db import User
from figure1.common.models.db import CaseAuthor
from figure1.common.models.db import Comment
from figure1.common.types import CommentState
from figure1.core import FirestoreSyncBase
from figure1.core import FirebaseTaskBase


logger = logging.getLogger('figure1.firebase.anonymous_authors_db')


def _get_user_anonymous_case_uuids(user_uuid, session) -> List[str]:
    for each in session.query(Case.case_uuid) \
            .join(CaseAuthor) \
            .filter(Case.is_anonymous.is_(True),
                    CaseAuthor.author_uuid == user_uuid).all():
        yield str(each[0])


def _get_user_anonymous_comment_uuids(user_uuid, session) -> List[str]:
    for each in session.query(Comment.comment_uuid).filter(Comment.author_uuid == user_uuid,
                                                           Comment.is_anonymous.is_(True),
                                                           Comment.state.is_not(CommentState.DELETED),
                                                           Comment.state.is_not(CommentState.REPORTED)).all():
        yield str(each[0])


@celery_app.task(bind=True,
                 base=FirebaseTaskBase,
                 name='figure1.backend.sync_user_anonymous_case')
def sync_user_anonymous_case_task(self, user_uuid, case_uuid):
    """
    Sync user anonymous case to firestore; if case_uuid is None, then sync all user anonymous cases
    :param user_uuid:
    :param case_uuid:
    :return:
    """
    sync_user_anonymous_case(user_uuid=user_uuid, case_uuid=case_uuid, session=self.session)


@celery_app.task(bind=True,
                 base=FirebaseTaskBase,
                 name='figure1.backend.sync_user_anonymous_comment')
def sync_user_anonymous_comment_task(self, user_uuid, comment_uuid):
    """
    Sync user anonymous comment to firestore; if comment_uuid is None, then sync all user anonymous comments
    :param user_uuid:
    :param comment_uuid:
    :return:
    """
    sync_user_anonymous_comment(user_uuid=user_uuid, comment_uuid=comment_uuid, session=self.session)


def sync_user_anonymous_case(user_uuid, case_uuid=None, session=None):
    user = User.get_user_by_uuid(user_uuid=user_uuid,
                                 session=session,
                                 raise_exception=True)
    if not user.user_uid:
        logger.debug("Skipping user anonymous case sync for user without uid: %s", user_uuid)
        return
    user_uid = str(user.user_uid)

    if not case_uuid:
        # Sync all anonymous cases
        anonymous_case_uuids = list(_get_user_anonymous_case_uuids(user_uuid=user_uuid, session=session))
        FirestoreAnonymousAuthor(userUid=user_uid,
                                 anonymousCaseUuids=anonymous_case_uuids).firestore_write(session=session)
    else:
        FirestoreAnonymousAuthor(userUid=user_uid,
                                 anonymousCaseUuids=[case_uuid]).firestore_update(session=session)


def sync_user_anonymous_comment(user_uuid, comment_uuid=None, session=None):
    user = User.get_user_by_uuid(user_uuid=user_uuid,
                                 session=session,
                                 raise_exception=True)
    if not user.user_uid:
        logger.debug("Skipping user anonymous comment sync for user without uid: %s", user_uuid)
        return
    user_uid = str(user.user_uid)

    if not comment_uuid:
        # Sync all anonymous comments
        anonymous_comment_uuids = list(_get_user_anonymous_comment_uuids(user_uuid=user_uuid, session=session))
        FirestoreAnonymousAuthor(userUid=user_uid,
                                 anonymousCommentUuids=anonymous_comment_uuids).firestore_write(session=session)
    else:
        FirestoreAnonymousAuthor(userUid=user_uid,
                                 anonymousCommentUuids=[comment_uuid]).firestore_update(session=session)


class FirestoreAnonymousAuthor(FirestoreSyncBase):
    userUid: str
    anonymousCaseUuids: Optional[List[str]] = None
    anonymousCommentUuids: Optional[List[str]] = None

    def generate_firestore_document(self, session=None) -> dict:
        return self.dict()

    @property
    def firestore_doc_reference(self) -> DocumentReference:
        return self.fs_client.collection('anonymousAuthorsDB').document(self.userUid)

    def generate_firestore_update_document(self, session=None) -> dict:
        update_document = {}
        if self.anonymousCaseUuids:
            update_document['anonymousCaseUuids'] = firestore.ArrayUnion(self.anonymousCaseUuids)
        if self.anonymousCommentUuids:
            update_document['anonymousCommentUuids'] = firestore.ArrayUnion(self.anonymousCommentUuids)

        update_document['userUid'] = self.userUid

        return update_document
