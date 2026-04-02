import logging
from uuid import UUID
from typing import Optional
from pydantic import BaseModel
from pydantic import validator
from pydantic import ValidationError
from pydantic import Field
from sqlalchemy.orm import Session

from figure1.core import managed_session
from figure1.common.models.db import User
from figure1.common.models.db import Comment
from figure1.common.models.db import CommentFlag
from figure1.common.models.db import CommentReport
from figure1.common.types import CommentState
from figure1.common.types import CommentRejectionReason
from figure1.common.helpers.comment import CommentSync
from figure1.exceptions import CommentNotFound
from figure1.exceptions import AcceptedAnswerError
from figure1.events import CommentEvents


class Validation(BaseModel):
    comment: Comment
    moderatorUuid: str = Field(alias='moderator_uuid')

    class Config:
        arbitrary_types_allowed = True

    @validator('moderatorUuid', pre=True)
    def stringify_uuid(cls, value):
        return str(value)


def _validate(moderator_uid, comment_uuid, session, valid_states=None) -> Optional[Validation]:
    moderator_uuid = User.get_user_uuid_by_uid(user_uid=moderator_uid, session=session, raise_exception=True)
    comment = CommentSync.get_comment(comment_uuid=comment_uuid, session=session)
    if not comment:
        raise CommentNotFound(msg='Comment not found')

    valid = Validation(comment=comment, moderator_uuid=moderator_uuid)
    if not valid_states:
        return valid
    if comment.state not in valid_states:
        raise ValidationError
    return valid


@managed_session
def approve_comment(comment_uuid, moderator_uid, session=None):
    try:
        res = _validate(moderator_uid=moderator_uid,
                        comment_uuid=comment_uuid,
                        valid_states=[CommentState.FLAGGED,
                                      CommentState.PENDING_APPROVAL_FLAGGED,
                                      CommentState.REPORTED,
                                      CommentState.PENDING_APPROVAL,
                                      CommentState.ALERTED],
                        session=session)
    except ValidationError as ve:
        return {'code': 400,
                'error': ve.json()}

    for r in session.query(CommentReport).filter(CommentReport.comment_uuid == comment_uuid).all():
        r.moderator_approved = True
        r.moderator_reviewed = True
        r.moderator_uuid = res.moderatorUuid
    res.comment.state = CommentState.APPROVED
    res.comment.replyable = True
    comment = session.merge(res.comment)

    CommentEvents.COMMENT_UPDATED(comment=comment, session=session)
    return {'success': f"Comment approved"}


@managed_session
def reject_comment(comment_uuid: str,
                   moderator_uid: str,
                   reason: CommentRejectionReason,
                   session: Session = None):
    try:
        res = _validate(moderator_uid=moderator_uid,
                        comment_uuid=comment_uuid,
                        valid_states=[CommentState.FLAGGED,
                                      CommentState.PENDING_APPROVAL_FLAGGED,
                                      CommentState.REPORTED,
                                      CommentState.PENDING_APPROVAL,
                                      CommentState.ALERTED],
                        session=session)
    except ValidationError as ve:
        return {'code': 400,
                'error': ve.json()}

    for r in session.query(CommentReport).filter(CommentReport.comment_uuid == comment_uuid).all():
        r.moderator_approved = False
        r.moderator_reviewed = True
        r.moderator_uuid = res.moderatorUuid
    is_accepted_answer = res.comment.is_accepted_answer
    res.comment.rejection_reason = reason
    res.comment.state = CommentState.REJECTED
    res.comment.replyable = False
    res.comment.is_accepted_answer = False
    session.add(res.comment)
    session.flush()
    suppress_user_notification = reason == CommentRejectionReason.NO_EMAIL
    CommentEvents.COMMENT_DELETED(comment=res.comment,
                                  suppress_user_notification=suppress_user_notification,
                                  moderator_uuid=res.moderatorUuid,
                                  is_accepted_answer=is_accepted_answer,
                                  session=session)
    return {'success': f"Comment rejected"}


@managed_session
def flag_comment(comment_uuid, moderator_uid, session=None):
    try:
        res = _validate(moderator_uid=moderator_uid,
                        comment_uuid=comment_uuid,
                        session=session)
    except ValidationError as ve:
        return {'code': 400,
                'error': ve.json()}

    if res.comment.state in [CommentState.FLAGGED, CommentState.PENDING_APPROVAL_FLAGGED]:
        return {'success': f"Comment already flagged"}

    if res.comment.state == CommentState.PENDING_APPROVAL:
        new_state = CommentState.PENDING_APPROVAL_FLAGGED
    else:
        new_state = CommentState.FLAGGED

    res.comment.state = new_state
    session.add(res.comment)
    session.flush()
    CommentFlag.create(moderator_uuid=res.moderatorUuid,
                       comment_uuid=res.comment.comment_uuid,
                       session=session,
                       skip_commit=True)
    CommentEvents.COMMENT_UPDATED(comment=res.comment, session=session)

    return {'success': f"Comment flagged"}


@managed_session
def set_comments_reviewed_status(moderator_uid, comment_uuids, status, session=None):
    for uuid in comment_uuids:
        res = _validate(moderator_uid=moderator_uid,
                        comment_uuid=uuid,
                        session=session)
        if not res.comment.is_accepted_answer:
            raise AcceptedAnswerError(msg='Only accepted answer can be reviewed')

        is_reviewed = status == 'reviewed'
        res.comment.moderator_reviewed = is_reviewed
        session.add(res.comment)

        if is_reviewed:
            CommentEvents.ACCEPTED_ANSWER_REVIEWED(comment_uuid=res.comment.comment_uuid)
        else:
            CommentEvents.ACCEPTED_ANSWER_PENDING_REVIEW(comment_uuid=res.comment.comment_uuid)

    return {'success': "Successfully updated comments reviewed"}
