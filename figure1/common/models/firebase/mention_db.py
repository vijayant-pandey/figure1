"""
Firestore sync for user mentions.

Handles syncing mention data from Postgres to Firestore.
Mentions are stored in userMentionsDB/{userUid}/mentions/{mentionUuid}
"""
import logging
from typing import Optional
from pydantic import Field, validator

from figure1.common.models.db import Mention, User, Comment, Content, Case
from figure1.core import FirestoreSyncBase
from figure1.common.types import FirebaseAction

logger = logging.getLogger('figure1.firebase.mention')


class FirestoreMention(FirestoreSyncBase):
    """
    Handles syncing a mention to Firestore.

    Mentions are synced to: userMentionsDB/{mentionedUserUid}/mentions/{mentionUuid}
    """
    mentionUuid: str = Field(alias='mention_uuid')
    mentionedUserUid: str = Field(alias='mentioned_user_uid')

    @validator('mentionUuid', pre=True)
    def stringify_mention_uuid(cls, value):
        return str(value)

    @property
    def firestore_doc_reference(self):
        """
        Returns the Firestore document reference for this mention.
        Path: userMentionsDB/{mentionedUserUid}/mentions/{mentionUuid}
        """
        return self.fs_client \
            .collection('userMentionsDB') \
            .document(self.mentionedUserUid) \
            .collection('mentions') \
            .document(self.mentionUuid)

    def generate_firestore_document(self, session=None) -> dict:
        """
        Generate the Firestore document data for this mention.

        Returns:
            dict: The mention data to be synced to Firestore
        """
        if session is None:
            raise ValueError("Session is required")

        # Fetch the mention from Postgres
        mention = session.query(Mention).get(self.mentionUuid)
        if not mention:
            logger.warning(f"Mention {self.mentionUuid} not found in database")
            return {}

        # Build the base mention document
        mention_doc = {
            'mentionUuid': str(mention.mention_uuid),
            'mentionedUserUuid': str(mention.mentioned_user_uuid),
            'mentioningUserUuid': str(mention.mentioning_user_uuid),
            'position': mention.position,
            'isRead': mention.is_read,
            'readAt': mention.read_at.isoformat() if mention.read_at else None,
            'createdAt': mention.created_at.isoformat() if mention.created_at else None,
            'updatedAt': mention.updated_at.isoformat() if mention.updated_at else None,
        }

        # Add context about where the mention occurred
        if mention.comment_uuid:
            mention_doc['commentUuid'] = str(mention.comment_uuid)
            comment = session.query(Comment).get(mention.comment_uuid)
            if comment:
                mention_doc['commentText'] = comment.text[:200] if comment.text else ""  # Preview

        if mention.content_uuid:
            mention_doc['contentUuid'] = str(mention.content_uuid)

        if mention.case_uuid:
            mention_doc['caseUuid'] = str(mention.case_uuid)
            case = session.query(Case).get(mention.case_uuid)
            if case:
                mention_doc['caseTitle'] = case.title if case.title else ""

        # Add mentioning user info
        mentioning_user = session.query(User).get(mention.mentioning_user_uuid)
        if mentioning_user:
            mention_doc['mentioningUser'] = {
                'userUuid': str(mentioning_user.user_uuid),
                'userUid': mentioning_user.user_uid,
                'username': mentioning_user.username,
                'displayName': mentioning_user.display_name or mentioning_user.username,
            }

        return mention_doc

    @staticmethod
    def sync(firebase_db, row_uuid, action, columns=None, session=None):
        """
        Static sync method called by the Celery task system.

        Args:
            firebase_db: Firebase client
            row_uuid: The mention_uuid
            action: FirebaseAction (SET or DELETE)
            columns: Optional list of columns that changed
            session: Database session

        Returns:
            list: List of sync operations to perform
        """
        logger.debug(f"Syncing mention {row_uuid} with action {action}")

        if session is None:
            raise ValueError("Session is required for mention sync")

        # Fetch the mention
        mention = session.query(Mention).get(row_uuid)
        if not mention:
            logger.warning(f"Mention {row_uuid} not found for sync")
            return []

        # Fetch the mentioned user to get their user_uid
        mentioned_user = session.query(User).get(mention.mentioned_user_uuid)
        if not mentioned_user or not mentioned_user.user_uid:
            logger.warning(f"Mentioned user {mention.mentioned_user_uuid} not found or has no user_uid")
            return []

        # Create the path for Firestore
        path = firebase_db.collection('userMentionsDB') \
            .document(mentioned_user.user_uid) \
            .collection('mentions') \
            .document(str(mention.mention_uuid)) \
            .path

        # Create the sync object
        sync_object = FirestoreMention(
            mention_uuid=mention.mention_uuid,
            mentioned_user_uid=mentioned_user.user_uid
        )

        # Return the appropriate action
        if action is FirebaseAction.SET:
            data = sync_object.generate_firestore_document(session=session)
            if data:
                return [{
                    "path": path,
                    "action": FirebaseAction.SET,
                    "data": data
                }]
            else:
                return []
        elif action is FirebaseAction.DELETE:
            return [{
                "path": path,
                "action": FirebaseAction.DELETE
            }]
        else:
            logger.error(f"Unsupported action for mention={row_uuid}, action={action}")
            return []
