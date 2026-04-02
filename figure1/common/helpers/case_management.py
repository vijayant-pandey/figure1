import logging
import uuid
from itertools import zip_longest

from sqlalchemy.orm import Session

from pydantic import BaseModel
from pydantic import validator, root_validator
from typing import Optional
from figure1.core import translate_client
from figure1.common.types import CaseState, CommentState, Locale, MediaType, CaseType, CaseClassification
from figure1.common.utils import s3_utils, case_image_path, case_image_original_path
from figure1.common.models.db import CmeCertificateTemplate, Label, GroupMember
from figure1.common.models.db.c_case_label_model import CaseLabel
from figure1.common.models.db.c_case_model import Case, \
    CaseAuthor, \
    Content, \
    Features, \
    ContentExtension, \
    SponsoredContent, \
    ContentTranslation
from figure1.common.models.db.c_case_reaction_model import CaseReaction
from figure1.common.models.db.c_case_report_model import CaseReport
from figure1.common.models.db.c_case_specialty_model import CaseSpecialtyV2
from figure1.common.models.db.c_comment_model import Comment, CommentReport
from figure1.common.models.db.c_content_update_model import ContentUpdate, ContentUpdateTranslations
from figure1.common.models.db.c_media_model import Media
from figure1.common.models.db.c_question_model import QuestionOption, QuestionVote
from figure1.common.models.db.user_models.u_user_saved_case_model import UserSavedCase
from figure1.exceptions.user import GroupMemberNotFound

logger = logging.getLogger('figure1.helpers.case_management')


class CaseFields(BaseModel):
    state: Optional[CaseState]
    is_paging_case: Optional[bool]
    rejection_reason: Optional[str]
    case_type: Optional[CaseType] = CaseType.STATIC
    cme1_credits: Optional[float] = 0.25
    passing_score: Optional[int] = 1
    group_uuid: Optional[str]
    request_help: Optional[bool]
    has_diagnosis: Optional[bool]
    is_anonymous: Optional[bool]
    language: Optional[str]
    case_classification: Optional[CaseClassification] = CaseClassification.MEDICAL

    class Config:
        extra = 'ignore'

    @validator('language', pre=True)
    def validate_language(cls, value):
        return Locale.get_from_code(value).code

    @root_validator
    def validate_all_fields(cls, values):
        if values.get('group_uuid') is not None and values.get('is_paging_case') is True:
            raise ValueError("A group case cannot be a paging case")
        return values


class CaseManagement:

    @staticmethod
    def allowed_content_arguments():
        return [
            'title',
            'caption',
            'is_feed_card',
            'case_uuid',
            'display_order',
            'content_type',
            'feed_card_type',
            'section'
        ]

    @staticmethod
    def allowed_content_extension_arguments():
        return [
            'button_text',
            'button_url',
            'question',
            'question_answer_details',
            'external_link_url',
            'external_link_text',
            'heading',
            'colour',
            'isi_link',
            'isi_text',
            'isi_embedded_content_link',
            'feed_card_label',
            'feed_card_title',
            'references'
        ]

    @staticmethod
    def allowed_features_arguments():
        return [
            'comments_enabled',
            'comment_queue_enabled',
            'comment_tabs_enabled',
            'dismiss_button',
            'dismiss_on_click',
            'public_notifications_enabled',
            'reactions_enabled',
            'report_enabled',
            'save_enabled',
            'share_enabled',
            'show_in_mobile',
            'show_in_web',
            'show_labels',
            'show_views',
            'similar_cases_enabled',
            'zoom_enabled'
        ]

    @staticmethod
    def allowed_sponsored_content_arguments():
        return [
            'sponsored_text',
            'disclosure_text',
            'job_code',
        ]

    @staticmethod
    def delete_case(case_uuid, session, destructive=False):
        session.query(CaseReaction).filter(CaseReaction.case_uuid == case_uuid).delete()
        for ca in session.query(CaseAuthor).filter(CaseAuthor.case_uuid == case_uuid).all():
            ca.mark_deleted()
        for cl in session.query(CaseLabel).filter(CaseLabel.case_uuid == case_uuid).all():
            cl.mark_deleted()
        for cr in session.query(CaseReport).filter(CaseReport.case_uuid == case_uuid).all():
            cr.mark_deleted()
        for cs in session.query(CaseSpecialtyV2).filter(CaseSpecialtyV2.case_uuid == case_uuid).all():
            cs.mark_deleted()
        for sc in session.query(UserSavedCase).filter(UserSavedCase.case_uuid == case_uuid).all():
            sc.mark_deleted()
        for content in session.query(Content).filter(Content.case_uuid == case_uuid).all():
            CaseManagement.delete_content(content=content,
                                          session=session,
                                          destructive=destructive)
        c = session.query(Case).filter(Case.case_uuid == case_uuid).one()
        c.mark_deleted()
        c.state = CaseState.DELETED

    @staticmethod
    def delete_content(content: Content,
                       session: Session,
                       destructive: bool = False):
        if destructive:
            content.caption = "deleted"
            content.title = "deleted"
        for m in session.query(Media).filter(Media.content_uuid == content.content_uuid).all():
            m.mark_deleted()
            if destructive:
                if m.filename:
                    s3_utils.delete_from_s3(path=f'{case_image_path}/{m.filename}')
                if m.original_filename:
                    s3_utils.delete_from_s3(path=f'{case_image_original_path}/{m.original_filename}')
        for c in session.query(Comment).filter(Comment.content_uuid == content.content_uuid).all():
            c.mark_deleted()
            c.state = CommentState.DELETED
            for cr in session.query(CommentReport).filter(CommentReport.comment_uuid == c.comment_uuid).all():
                cr.mark_deleted()
        for cu in session.query(ContentUpdate).filter(ContentUpdate.content_uuid == content.content_uuid).all():
            cu.mark_deleted()
            if destructive:
                cu.text = "deleted"
        for qo in session.query(QuestionOption).filter(QuestionOption.content_uuid == content.content_uuid).all():
            for qv in session.query(QuestionVote) \
                    .filter(QuestionVote.question_option_uuid == qo.question_option_uuid) \
                    .all():
                qv.mark_deleted()
            qo.mark_deleted()
        content.mark_deleted()

    @staticmethod
    def update_case_cme_label(case_uuid, case_state, group_uuid, session, skip_commit=False):
        cme_label = session.query(Label).filter(Label.kind == 'case_cme').one_or_none()
        if not cme_label:
            logger.error("The case_cme label does not exist.")
        elif case_state == CaseState.APPROVED and not group_uuid:
            CaseLabel.create(case_uuid=case_uuid,
                             label_uuid=cme_label.label_uuid,
                             skip_commit=skip_commit,
                             session=session)
        else:
            CaseLabel.delete(case_uuid=case_uuid,
                             label_uuid=cme_label.label_uuid,
                             skip_commit=skip_commit,
                             session=session)

    @staticmethod
    def create_case(session, state, author_uuid, **kwargs):
        case = Case()
        case_settings = CaseFields.parse_obj(kwargs)
        case_settings.state = state
        case.case_uuid = uuid.uuid4()
        case.event_author_uuid = author_uuid
        if case_settings.group_uuid is not None:
            if not GroupMember.get_by_user_and_group(group_uuid=case_settings.group_uuid,
                                                     user_uuid=author_uuid,
                                                     session=session):
                raise GroupMemberNotFound
        for k, v in case_settings.dict(exclude_none=True).items():
            case.__setattr__(k, v)
        session.add(case)
        session.flush()
        CaseManagement.add_case_author(case_uuid=case.case_uuid, author_uuid=author_uuid, session=session)

        return case

    @staticmethod
    def update_case(case_uuid, session, **kwargs):
        case = session.query(Case).filter(Case.case_uuid == case_uuid).one()
        case_settings = CaseFields.parse_obj(kwargs)
        for k, v in case_settings.dict(exclude_none=True).items():
            case.__setattr__(k, v)
        return session.merge(case)

    @staticmethod
    def translate_case(case_uuid, session, source_language, target_language=Locale.EN_US):
        translate = translate_client()

        if not translate:
            return None

        source_language = Locale.get_from_code(source_language)

        if source_language == target_language:
            return None

        case = session.query(Case).filter(Case.case_uuid == case_uuid).one()
        translated_item = ContentTranslation()

        for c in case.content:
            translated_item.content_uuid = c.content_uuid
            translated_item.case_uuid = case.case_uuid
            translated_item.source_language = source_language.code
            translated_item.target_language = target_language.code
            source_language = source_language.language_code,

            if c.caption:
                translated_item.caption = translate.translate(target_language=target_language.language_code,
                                                              values=c.caption)['translatedText']
            if c.title:
                translated_item.title = translate.translate(target_language=target_language.language_code,
                                                            values=c.title)['translatedText']

            for u in c.updates:
                translated_update = session.query(ContentUpdateTranslations).filter(
                    ContentUpdateTranslations.update_uuid == u.update_uuid,
                    ContentUpdateTranslations.language == target_language.code) \
                    .one_or_none()

                if not translated_update:
                    translated_update = ContentUpdateTranslations()
                translated_update.update_uuid = u.update_uuid
                translated_update.language = target_language.code

                translated_update.text = translate.translate(target_language=target_language.language_code,
                                                             values=u.text)['translatedText']
                session.merge(translated_update)
            session.merge(translated_item)

        session.flush()

    @staticmethod
    def replace_case_author(case_uuid, author_uuid, session):
        session.query(CaseAuthor).filter(CaseAuthor.case_uuid == case_uuid).delete()
        session.flush()
        CaseManagement.add_case_author(case_uuid=case_uuid, author_uuid=author_uuid, session=session)

    @staticmethod
    def add_case_author(case_uuid, author_uuid, session):
        author = CaseAuthor()
        author.author_uuid = author_uuid
        author.case_uuid = case_uuid
        session.add(author)

    @staticmethod
    def delete_case_author(case_uuid, author_uuid, session):
        session.query(CaseAuthor) \
            .filter(CaseAuthor.author_uuid == author_uuid, CaseAuthor.case_uuid == case_uuid) \
            .delete()
        session.flush()

    @staticmethod
    def update_cme_certificates(case_uuid, certificates, session):
        existing = session.query(CmeCertificateTemplate) \
            .filter(CmeCertificateTemplate.case_uuid == case_uuid) \
            .all()

        all_professions = []
        for c in certificates:
            for p in c.get('profession_tree_uuids', []):
                if p:
                    all_professions.append(p)
                    CmeCertificateTemplate.create_or_update(case_uuid=case_uuid,
                                                            profession_uuid=p,
                                                            path=c.get('path'),
                                                            filename=c.get('filename'),
                                                            session=session)

        for c in existing:
            if str(c.profession_uuid) not in all_professions:
                c.mark_deleted()

    @staticmethod
    def create_content(case_uuid, session, **kwargs) -> Content:
        content = Content()
        content.content_uuid = uuid.uuid4()
        content.case_uuid = case_uuid
        content = CaseManagement._set_allowed_args(content, kwargs, CaseManagement.allowed_content_arguments())
        session.add(content)

        Features.set_default(content_uuid=content.content_uuid, session=session)
        CaseManagement.update_content(content_uuid=content.content_uuid, session=session, **kwargs)

        session.commit()
        return content

    @staticmethod
    def update_content(content_uuid, session, **kwargs) -> Content:
        content = session.query(Content).filter(Content.content_uuid == content_uuid).one()

        # Content
        content = CaseManagement._set_allowed_args(content, kwargs, CaseManagement.allowed_content_arguments())
        content.deleted_at = None
        session.add(content)

        # Content Extension
        extension_args = CaseManagement.allowed_content_extension_arguments()
        if any(k in kwargs for k in extension_args):
            if content.extension:
                e = content.extension
            else:
                e = ContentExtension()
                e.content_extension_uuid = uuid.uuid4()
                content.extension_uuid = e.content_extension_uuid

            e = CaseManagement._set_allowed_args(e, kwargs, extension_args)
            session.add(e)

        # Features
        feature_args = CaseManagement.allowed_features_arguments()
        if any(k in kwargs for k in feature_args):
            if content.features and content.features.is_default is False:
                f = content.features
            else:
                f = Features()
                f.features_uuid = uuid.uuid4()
                content.features_uuid = f.features_uuid

            f.is_default = False
            f = CaseManagement._set_allowed_args(f, kwargs, feature_args)
            session.add(f)

        # Sponsored Content
        sponsored_args = CaseManagement.allowed_sponsored_content_arguments()
        if any(k in kwargs for k in sponsored_args):
            if content.sponsored_content:
                s = content.sponsored_content
            else:
                s = SponsoredContent()
                s.sponsored_content_uuid = uuid.uuid4()
                content.sponsored_content_uuid = s.sponsored_content_uuid

            s = CaseManagement._set_allowed_args(s, kwargs, sponsored_args)
            session.add(s)

        CaseManagement._update_media(content_uuid, kwargs.get('media', []), session)
        CaseManagement._update_question_options(content_uuid, kwargs.get('question_options', []), session)
        if 'feed_card_media' in kwargs:
            CaseManagement._update_feed_card_media(content_uuid, kwargs.get('feed_card_media', {}), session)

        session.flush()
        return content

    @staticmethod
    def _set_allowed_args(inst, settings, allowed_arguments):
        for k, v in settings.items():
            if k not in allowed_arguments:
                continue
            if v is not None and v != "":
                setattr(inst, k, v)
            else:
                setattr(inst, k, None)
        return inst

    @staticmethod
    def _update_media(content_uuid, new_media, session):
        current = list(session.query(Media)
                       .filter(Media.content_uuid == content_uuid,
                               Media.is_feed_card_media.is_(False),
                               Media.deleted_at.is_(None))
                       .order_by(Media.display_order)
                       .all())

        for i, data in enumerate(zip_longest(current, new_media)):
            old = data[0]
            new = data[1]
            if new is None:
                old.mark_deleted()
            else:
                if old is None:
                    m = Media()
                    m.media_uuid = uuid.uuid4()
                    m.content_uuid = content_uuid
                else:
                    m = old
                m.display_order = i
                m.type = MediaType[new.get('type').upper()]
                m.filename = new.get('filename')
                m.width = new.get('width')
                m.height = new.get('height')
                m.regenerate_video_url()

                session.add(m)

    @staticmethod
    def _update_feed_card_media(content_uuid, feed_card_media, session):
        """
        If feed_card_media is empty or None, mark existing as deleted. Updates session, but does not commit.

        :param content_uuid:
        :param feed_card_media:
        :param session:
        :return: None
        """
        current = Media.get_feed_card_media(content_uuid=content_uuid, session=session)

        if current and not feed_card_media:
            current.mark_deleted()
            session.add(current)
            return None

        elif not current and not feed_card_media:
            return None

        elif current and feed_card_media:
            m = current

        else:
            m = Media()
            m.media_uuid = uuid.uuid4()
            m.content_uuid = content_uuid

        m.type = MediaType[feed_card_media.get('type').upper()]
        m.filename = feed_card_media.get('filename')
        m.width = feed_card_media.get('width')
        m.height = feed_card_media.get('height')
        m.is_feed_card_media = True
        m.regenerate_video_url()
        session.add(m)
        return None

    @staticmethod
    def _update_question_options(content_uuid, new_options, session):
        def _is_option_equal(old, new):
            return old.text == new.get('text') and old.is_answer == new.get('is_answer')

        current = list(session.query(QuestionOption)
                       .filter(QuestionOption.content_uuid == content_uuid, QuestionOption.deleted_at.is_(None))
                       .order_by(QuestionOption.display_order)
                       .all())

        zipped = zip(current, new_options)
        if (len(current) == len(new_options)) and all(_is_option_equal(t[0], t[1]) for t in zipped):
            # Options have not changed
            return

        # Mark old options as deleted and create new ones, to preserve vote counts
        for o in current:
            o.mark_deleted()
        for i, op in enumerate(new_options):
            q = QuestionOption()
            q.question_option_uuid = uuid.uuid4()
            q.content_uuid = content_uuid
            q.display_order = i
            q.text = op.get('text')
            q.is_answer = op.get('is_answer', False)
            q.is_free_form = op.get('is_free_form', False)
            session.add(q)
