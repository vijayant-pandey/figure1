"""
Domain logic for mention processing and storage.
"""
import logging
import re
from datetime import datetime
from typing import List, Dict, Optional

from figure1.common.models.db import Mention, User
from figure1.core import managed_session

logger = logging.getLogger('figure1.mentions')


def calculate_mention_position(text: str, username: str) -> int:
    """
    Calculate the position of @username in the text.
    Returns the index of the @ symbol, or 0 if not found.

    Args:
        text: The text containing mentions
        username: The username to find (without @)

    Returns:
        Position of @ symbol in text, or 0 if not found
    """
    pattern = r'@' + re.escape(username) + r'\b'
    match = re.search(pattern, text, re.IGNORECASE)
    return match.start() if match else 0


@managed_session
def process_and_store_mentions(
    mentions: List[Dict],
    text: str,
    mentioning_user_uid: str,
    comment_uuid: Optional[str] = None,
    content_uuid: Optional[str] = None,
    case_uuid: Optional[str] = None,
    session=None
) -> List[str]:
    """
    Process a list of mentions and store them in the database.

    Args:
        mentions: List of mention dicts with keys: username, userUuid, userUid, displayName
        text: The text containing the mentions (comment or case update text)
        mentioning_user_uid: Firebase UID of the user creating the mention
        comment_uuid: UUID of the comment (if mention is in a comment)
        content_uuid: UUID of the content (if mention is in case content)
        case_uuid: UUID of the case (if mention is in a case)
        session: Database session (provided by decorator)

    Returns:
        List of created mention UUIDs

    Raises:
        ValueError: If mentioning user not found or invalid data
    """
    if not mentions:
        logger.info("No mentions to process")
        return []

    created_mention_uuids = []

    try:
        # Look up the mentioning user by their Firebase UID
        mentioning_user = session.query(User).filter(
            User.user_uid == mentioning_user_uid
        ).first()

        if not mentioning_user:
            raise ValueError(f"Mentioning user not found with uid: {mentioning_user_uid}")

        logger.info(f"Processing {len(mentions)} mentions from user {mentioning_user.username}")

        # Process each mention
        for mention_data in mentions:
            try:
                username = mention_data.get('username')
                mentioned_user_uuid = mention_data.get('userUuid')

                if not username or not mentioned_user_uuid:
                    logger.warning(f"Skipping invalid mention data: {mention_data}")
                    continue

                # Calculate position of @username in text
                position = calculate_mention_position(text, username)

                # Create the Mention record
                mention = Mention(
                    mentioned_user_uuid=mentioned_user_uuid,
                    mentioning_user_uuid=mentioning_user.user_uuid,
                    comment_uuid=comment_uuid,
                    content_uuid=content_uuid,
                    case_uuid=case_uuid,
                    position=position,
                    is_read=False,
                    created_at=datetime.utcnow()
                )

                session.add(mention)
                session.flush()  # Flush to get the UUID

                created_mention_uuids.append(str(mention.mention_uuid))

                logger.info(
                    f"Created mention: {mention.mention_uuid} - "
                    f"@{username} (mentioned_user_uuid={mentioned_user_uuid}) "
                    f"by {mentioning_user.username} at position {position}"
                )

            except Exception as e:
                logger.error(f"Error processing individual mention {mention_data}: {e}")
                # Continue processing other mentions even if one fails
                continue

        # Commit all mentions at once
        session.commit()

        logger.info(
            f"Successfully created {len(created_mention_uuids)} mention records"
        )

        # TODO: Trigger notification system for each mention
        # This should be implemented in Phase 5
        # For now, mentions are stored and can be retrieved via GET /api/pro/mentions

    except Exception as e:
        logger.exception(f"Error processing mentions: {e}")
        raise

    return created_mention_uuids


@managed_session
def get_mentions_for_comment(comment_uuid: str, session=None) -> List[Dict]:
    """
    Get all mentions associated with a comment.

    Args:
        comment_uuid: UUID of the comment
        session: Database session (provided by decorator)

    Returns:
        List of mention dicts
    """
    try:
        mentions = session.query(Mention).filter(
            Mention.comment_uuid == comment_uuid
        ).all()

        return [{
            'mention_uuid': str(m.mention_uuid),
            'mentioned_user_uuid': str(m.mentioned_user_uuid),
            'mentioning_user_uuid': str(m.mentioning_user_uuid),
            'position': m.position,
            'is_read': m.is_read,
            'created_at': m.created_at.isoformat() if m.created_at else None
        } for m in mentions]

    except Exception as e:
        logger.exception(f"Error fetching mentions for comment {comment_uuid}: {e}")
        return []


@managed_session
def get_mentions_for_case(case_uuid: str, session=None) -> List[Dict]:
    """
    Get all mentions associated with a case.

    Args:
        case_uuid: UUID of the case
        session: Database session (provided by decorator)

    Returns:
        List of mention dicts
    """
    try:
        mentions = session.query(Mention).filter(
            Mention.case_uuid == case_uuid
        ).all()

        return [{
            'mention_uuid': str(m.mention_uuid),
            'mentioned_user_uuid': str(m.mentioned_user_uuid),
            'mentioning_user_uuid': str(m.mentioning_user_uuid),
            'position': m.position,
            'is_read': m.is_read,
            'created_at': m.created_at.isoformat() if m.created_at else None
        } for m in mentions]

    except Exception as e:
        logger.exception(f"Error fetching mentions for case {case_uuid}: {e}")
        return []
