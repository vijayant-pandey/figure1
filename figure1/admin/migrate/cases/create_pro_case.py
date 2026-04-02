import logging
import uuid

from sqlalchemy.orm import Session
from sqlalchemy_utils import Ltree
from typing import List, Optional

from figure1.admin.migrate.cases.prequel_model import CasesPrequelModel
from figure1.common.elasticsearch import add_or_update_case
from figure1.common.helpers import CaseManagement
from figure1.common.models.db import CaseSpecialtyV2, Comment, Media, LegacyComment, ContentExtension, QuestionOption
from figure1.common.models.db import LegacyCase, TaggingState, Case, CaseAuthor, Content, Features
from figure1.common.types import CaseType, CaseState, Locale
from figure1.common.types import ContentType, FeedCardType
from figure1.common.types.comment import CommentState
from figure1.common.activities.user_profile_activities import update_all_activities_task

logger = logging.getLogger("figure1.migrate.cases.create_pro_case")


def _create_content_extension(content: Content,
                              legacy_case: LegacyCase,
                              prequel_model: CasesPrequelModel,
                              session: Session):
    ce = ContentExtension()
    ce.content_extension_uuid = uuid.uuid4()
    ce.external_link_url = legacy_case.external_link
    ce.external_link_text = legacy_case.external_link_text

    if legacy_case.is_quiz:
        legacy_quiz = prequel_model.get_quiz_data(case_id=legacy_case.legacy_id)
        if legacy_quiz:
            content.content_type = ContentType.QUIZ
            ce.question_answer_details = legacy_quiz.get('answerDescription')
            for c in legacy_quiz.get('choices', []):
                qo = QuestionOption()
                qo.question_option_uuid = uuid.uuid4()
                qo.content_uuid = content.content_uuid
                qo.text = c.get('text')
                qo.is_answer = c.get('isAnswer')
                qo.display_order = c.get('id')
                session.add(qo)

    session.add(ce)
    content.extension_uuid = ce.content_extension_uuid


def _upsert_pro_case(legacy_case: LegacyCase,
                     prequel_model: CasesPrequelModel,
                     session: Session):
    case = session.query(Case) \
        .filter(Case.case_uuid == legacy_case.case_uuid) \
        .one_or_none()
    if not case:
        case = Case()
        case.case_uuid = legacy_case.case_uuid
        case.state = CaseState.PENDING_NLP

    locale = Locale.get_from_code(legacy_case.language[0:2])

    if legacy_case.is_cm_cme \
            or legacy_case.is_image_series \
            or legacy_case.is_grand_rounds \
            or not locale:
        if not locale:
            logging.info(f"No locale: {legacy_case.legacy_id} {legacy_case.language}")
        case.state = CaseState.UNSUPPORTED
    elif locale is not Locale.EN_US:
        # Non english cases skip tagging since the MeSH api is not able to provide terms
        logging.info(f"Skipping tagging, not required for locale: {locale.code}")
        case.state = CaseState.APPROVED
        update_all_activities_task.delay(user_uuid=str(legacy_case.user_uuid))
    case.language = locale.code if locale else None
    case.is_paging_case = False
    case.case_type = CaseType.STATIC
    if legacy_case.created_at:
        case.created_at = legacy_case.created_at
        case.published_at = legacy_case.created_at
    if legacy_case.updated_at:
        case.updated_at = legacy_case.updated_at
    case.synced_at = None

    session.add(case)
    session.flush()

    content = session.query(Content) \
        .filter(Content.case_uuid == legacy_case.case_uuid) \
        .one_or_none()
    if not content:
        content = Content()
        content.content_uuid = uuid.uuid4()
        content.case_uuid = legacy_case.case_uuid
    content.title = legacy_case.title
    content.caption = legacy_case.caption
    content.content_type = ContentType.CONTENT
    content.display_order = 0
    content.is_feed_card = True
    content.feed_card_type = FeedCardType.BASIC
    if legacy_case.created_at:
        content.created_at = legacy_case.created_at
    if legacy_case.updated_at:
        content.updated_at = legacy_case.updated_at

    session.add(content)
    session.flush()

    if legacy_case.external_link or legacy_case.is_quiz:
        _create_content_extension(content=content,
                                  legacy_case=legacy_case,
                                  prequel_model=prequel_model,
                                  session=session)
    if content.content_type == ContentType.QUIZ:
        case.case_type = CaseType.QUIZ

    session.add(case)
    session.add(content)

    Features.set_default(content_uuid=content.content_uuid,
                         session=session,
                         skip_commit=True)

    CaseAuthor.create(case_uuid=case.case_uuid,
                      author_uuid=legacy_case.user_uuid,
                      skip_commit=True,
                      session=session)

    return case, content


def _migrate_media(legacy_case, content_uuid, session):
    for media in session.query(Media) \
            .filter(Media.case_uuid == legacy_case.case_uuid) \
            .with_for_update() \
            .all():
        media.content_uuid = content_uuid
        media.case_uuid = None


def _migrate_specialties(legacy_case, session):
    if legacy_case.tagged_specialty_uuids:
        for specialty_uuid in legacy_case.tagged_specialty_uuids:
            CaseSpecialtyV2.create(case_uuid=legacy_case.case_uuid,
                                   specialty_uuid=specialty_uuid,
                                   session=session)


def _get_comment_parent(legacy_comment: LegacyComment,
                        comments: List[Comment],
                        session: Session) -> Optional[Comment]:
    if not legacy_comment.parent_id:
        return None
    parent_uuid = session.query(LegacyComment.comment_uuid) \
        .filter(LegacyComment.legacy_id == legacy_comment.parent_id) \
        .one_or_none()
    if not parent_uuid:
        logging.info("Could not find parent for comment %s", str(legacy_comment.parent_id))
        return None
    return next((c for c in comments if c.comment_uuid == parent_uuid[0]), None)


def _migrate_comments(legacy_case, content_uuid, session):
    comments = []
    for lc in session.query(LegacyComment) \
            .filter(LegacyComment.case_uuid == legacy_case.case_uuid) \
            .order_by(LegacyComment.created_at.asc()) \
            .with_for_update() \
            .all():
        c = session.query(Comment) \
            .filter(Comment.comment_uuid == lc.comment_uuid) \
            .one_or_none()
        if not c:
            c = Comment()
            c.comment_uuid = lc.comment_uuid

        c.author_uuid = lc.user_uuid
        c.content_uuid = content_uuid
        c.text = lc.text
        c.language = lc.language
        c.state = CommentState.APPROVED if not lc.deleted else CommentState.DELETED
        c.created_at = lc.created_at
        c.updated_at = lc.created_at
        c.deleted_at = None if not lc.deleted else lc.created_at

        parent = _get_comment_parent(legacy_comment=lc, comments=comments, session=session)
        if parent:
            c.path = Ltree(parent.path.path + "." + c.comment_uuid.hex)
        else:
            c.path = Ltree(c.comment_uuid.hex)
        comments.append(c)
    session.bulk_save_objects(comments)


def upsert_pro_case(legacy_case: LegacyCase,
                    prequel_model: CasesPrequelModel,
                    session: Session) -> Case:
    case, content = _upsert_pro_case(legacy_case=legacy_case,
                                     prequel_model=prequel_model,
                                     session=session)
    session.flush()
    _migrate_comments(legacy_case=legacy_case, content_uuid=content.content_uuid, session=session)
    _migrate_media(legacy_case=legacy_case, content_uuid=content.content_uuid, session=session)
    legacy_case.state = TaggingState.MIGRATED
    session.flush()

    add_or_update_case(case_uuid=case.case_uuid, session=session)

    return case
