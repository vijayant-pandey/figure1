"""
Event listeners for Mention model to trigger Firestore sync.

Handles:
- Mention creation (after_insert) -> sync to Firestore
- Mention updates (is_read changes) -> sync to Firestore
- Mention deletion (after_delete) -> delete from Firestore
"""
import logging

from sqlalchemy import event
from sqlalchemy.orm import object_session

from figure1.common.models.db import Mention
from figure1.common.firebase import do_firebase_sync
from figure1.common.types import FirebaseAction

logger = logging.getLogger(__name__)


def _add_mention_sync_task(session, mention_uuid, action=FirebaseAction.SET):
    """
    Add a Firestore sync task for a mention to the session's task queue.

    Args:
        session: SQLAlchemy session
        mention_uuid: UUID of the mention to sync
        action: FirebaseAction (SET or DELETE)
    """
    task = do_firebase_sync.si(
        firebasemodel="FirestoreMention",
        uuid=str(mention_uuid),
        action=action
    )

    if isinstance(session.info.get('tasks'), list):
        if task not in session.info['tasks']:
            session.info['tasks'].append(task)
    else:
        session.info['tasks'] = [task]


@event.listens_for(Mention, 'after_insert')
def handle_mention_insert(mapper, connection, target):
    """
    Triggered after a new mention is inserted.
    Syncs the mention to Firestore (userMentionsDB).
    """
    session = object_session(target)
    if session is None:
        logger.warning("No session found for mention insert, skipping sync")
        return

    logger.info(f"Mention {target.mention_uuid} inserted, adding sync task")
    _add_mention_sync_task(session, target.mention_uuid, action=FirebaseAction.SET)


@event.listens_for(Mention.is_read, 'set', active_history=True, raw=True)
def handle_mention_is_read_change(target, value, old, initiator):
    """
    Triggered when mention.is_read is changed (e.g., marking as read).
    Syncs the updated mention to Firestore.
    """
    if target.transient or not target.session:
        logger.debug("Target is transient, will be handled by after_insert")
        return

    if value == old:
        logger.debug("is_read was not modified, do nothing")
        return

    logger.info(f"Mention {target.object.mention_uuid} is_read changed to {value}, adding sync task")
    _add_mention_sync_task(target.session, target.object.mention_uuid, action=FirebaseAction.SET)


@event.listens_for(Mention, 'after_delete')
def handle_mention_delete(mapper, connection, target):
    """
    Triggered after a mention is deleted.
    Deletes the mention from Firestore.
    """
    session = object_session(target)
    if session is None:
        logger.warning("No session found for mention delete, skipping sync")
        return

    logger.info(f"Mention {target.mention_uuid} deleted, adding delete task")
    _add_mention_sync_task(session, target.mention_uuid, action=FirebaseAction.DELETE)
