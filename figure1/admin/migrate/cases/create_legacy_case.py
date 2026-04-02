import logging
import uuid
from enum import IntEnum
from typing import Dict, Any, Optional
from uuid import uuid4

from datetime import timezone
from sqlalchemy.orm import Session

from figure1.core import managed_session
from figure1.common.models.db import LegacyCase, LegacyComment, Media, MediaType, TaggingState, LegacyUser
from figure1.common.types import Locale
from .prequel_model import CasesPrequelModel

logger = logging.getLogger("figure1.migrate.cases.create_legacy_case")


class LegacyContentType(IntEnum):
    IMAGE = 0
    IMAGE_SET = 1
    IMAGE_SERIES = 2
    TEXT = 3
    VIDEO = 4


def _create_media_for_legacy_case(case_uuid,
                                  media_type,
                                  legacy_id,
                                  filename,
                                  session,
                                  display_order=0,
                                  width=None,
                                  height=None):
    """
    Creates an entry in c_media.  If it already exists, do nothing.
    """
    m = session.query(Media).filter(Media.legacy_id == legacy_id,
                                    Media.filename == filename,
                                    Media.type == media_type,
                                    Media.display_order == display_order).one_or_none()
    if m:
        return m

    media = Media()
    media.media_uuid = uuid.uuid4()
    media.case_uuid = case_uuid
    media.type = media_type
    media.legacy_id = legacy_id
    media.filename = filename
    media.display_order = display_order
    media.width = width
    media.height = height

    session.add(media)
    return media


@managed_session
def _create_media(case_uuid: str,
                  case_dict: Dict[str, Any],
                  prequel_model: CasesPrequelModel,
                  session: Session = None):
    """
    Creates media entries based on legacy case data.  Unlike case and comments, the c_media entries are not separate
    between legacy and pro.
    """
    content_type = case_dict["contentType"]
    media_dicts = []
    if content_type is int(LegacyContentType.IMAGE):
        media_id = case_dict["url"]
        if not media_id or media_id == float('inf'):
            logger.error("Blank or infinite media id")
            return
        media_id = str(media_id)
        if not session.query(Media).filter(Media.legacy_id == media_id).filter(
                Media.case_uuid == case_uuid).first():
            m = _create_media_for_legacy_case(case_uuid=case_uuid,
                                              media_type=MediaType.IMAGE,
                                              legacy_id=media_id,
                                              filename=prequel_model.get_image_filename(media_id),
                                              display_order=0,
                                              width=case_dict["width"],
                                              height=case_dict["height"],
                                              session=session)
            media_dicts.append(m.as_dict())

    elif content_type is int(LegacyContentType.IMAGE_SET):
        for i, image in enumerate(case_dict["imageSet"]):
            media_id = image["imageID"]
            if not media_id or media_id == float('inf'):
                logger.error("Blank or bad image set media_id")
                continue
            media_id = str(media_id)
            if not session.query(Media).filter(Media.legacy_id == media_id).filter(
                    Media.case_uuid == case_uuid).first():
                m = _create_media_for_legacy_case(case_uuid=case_uuid,
                                                  media_type=MediaType.IMAGE,
                                                  legacy_id=media_id,
                                                  filename=prequel_model.get_image_filename(media_id),
                                                  display_order=i,
                                                  width=image["width"],
                                                  height=image["height"],
                                                  session=session)
                media_dicts.append(m.as_dict())

    elif content_type is int(LegacyContentType.IMAGE_SERIES):
        media_id = case_dict["imageSeries"]
        if not media_id or media_id == float('inf'):
            logger.error("Blank or infinite image series media id")
            return
        media_id = str(media_id)
        if not session.query(Media).filter(Media.legacy_id == media_id).filter(
                Media.case_uuid == case_uuid).first():
            m = _create_media_for_legacy_case(case_uuid=case_uuid,
                                              media_type=MediaType.IMAGE_SERIES,
                                              legacy_id=media_id,
                                              display_order=0,
                                              width=case_dict["width"],
                                              height=case_dict["height"],
                                              filename=None,
                                              session=session)
            media_dicts.append(m.as_dict())
    elif content_type is int(LegacyContentType.VIDEO):
        video_id = str(case_dict["video"]["id"])
        if not video_id:
            logger.error("Blank video id")
            return
        if not session.query(Media).filter(Media.legacy_id == video_id).filter(
                Media.case_uuid == case_uuid).first():
            m = _create_media_for_legacy_case(case_uuid=case_uuid,
                                              media_type=MediaType.VIDEO,
                                              legacy_id=video_id,
                                              display_order=0,
                                              filename=video_id,
                                              session=session)
            m.regenerate_video_url()
            media_dicts.append(m.as_dict())


def _upsert_legacy_comments(legacy_case: LegacyCase,
                            case_dict: Dict[str, Any],
                            session: Session):
    accepted_answer_id = case_dict.get('answer').get('commentId') if case_dict.get('answer') else None

    case_uuid = legacy_case.case_uuid
    case_comments = session.query(LegacyComment).filter(LegacyComment.case_uuid == case_uuid).all()
    comments = []
    for update_comment in case_dict['comments']:
        cm = next((item for item in case_comments if item.legacy_id == update_comment['_id']), None)
        if not cm:
            cm = LegacyComment()
            cm.legacy_id = update_comment.get('_id')
            cm.comment_uuid = uuid4()

        cm.case_uuid = case_uuid
        cm.user_id = update_comment.get('author')
        cm.user_uuid = _get_pro_user_uuid(legacy_id=update_comment.get('author'), session=session)
        cm.case_legacy_id = case_dict.get('_id')
        cm.text = update_comment.get('text')
        cm.language = Locale.EN_US.code
        cm.likes = update_comment.get('voteSum')
        cm.parent_id = update_comment.get('parentID')
        cm.accepted_answer = accepted_answer_id == update_comment.get("_id")
        cm.created_at = update_comment.get('created').replace(tzinfo=timezone.utc),
        cm.edited = update_comment.get('edited', False)
        cm.deleted = update_comment.get('deleted', False)
        comments.append(cm)
    session.bulk_save_objects(comments)


def _get_pro_user_uuid(legacy_id: str, session: Session):
    pro_user = session.query(LegacyUser) \
        .filter(LegacyUser.legacy_id == legacy_id) \
        .one_or_none()
    if not pro_user:
        logger.error(f"Failed to find legacy author %s", legacy_id)
        return None
    return pro_user.user_uuid


def upsert_legacy_case(case_dict: Dict[str, Any],
                       prequel_model: CasesPrequelModel,
                       session: Session) -> Optional[LegacyCase]:
    """
    Creates entries in the following tables based on legacy case data (e.g. from mongo):
     - c_legacy_case
     - c_legacy_comment
     - c_media
    """
    lc = session.query(LegacyCase) \
        .filter(LegacyCase.legacy_id == case_dict['_id']) \
        .one_or_none()
    if not lc:
        lc = LegacyCase()
        lc.case_uuid = uuid.uuid4()

    lc.legacy_id = case_dict['_id']
    lc.created_at = case_dict['created'].replace(tzinfo=timezone.utc)
    lc.updated_at = case_dict.get('modified', case_dict.get('created')).replace(tzinfo=timezone.utc)
    lc.author_id = case_dict['author']
    lc.user_uuid = _get_pro_user_uuid(legacy_id=case_dict['author'], session=session)
    lc.caption = case_dict['caption']
    lc.title = case_dict['title'] if 'title' in case_dict else ""
    lc.likes = case_dict['voteCount']
    lc.follows = case_dict['followCount']
    lc.specialty = case_dict['specialty'] if 'specialty' in case_dict else None
    lc.external_link = case_dict['externalLink'] if case_dict.get('externalLink') else None
    lc.external_link_text = case_dict['externalLinkDisplay'] if case_dict.get('externalLinkDisplay') else None
    lc.language = case_dict['detectedLanguage']
    lc.state = TaggingState.WAITING
    lc.is_grand_rounds = case_dict.get('isGrandRound') is True
    lc.is_image_series = case_dict.get('contentType') == LegacyContentType.IMAGE_SERIES.value
    lc.is_cm_cme = case_dict.get('linkedContentID')
    lc.is_quiz = case_dict.get('hasQuiz')

    session.add(lc)
    session.flush()

    _create_media(case_uuid=str(lc.case_uuid),
                  case_dict=case_dict,
                  prequel_model=prequel_model,
                  session=session)

    _upsert_legacy_comments(legacy_case=lc,
                            case_dict=case_dict,
                            session=session)
    session.flush()
    return lc
