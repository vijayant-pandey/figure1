import logging
import uuid
from typing import Optional

from sqlalchemy import Boolean
from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import Enum
from sqlalchemy import Float
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy import orm
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import backref
from sqlalchemy.orm import make_transient
from sqlalchemy.orm import relationship
from sqlalchemy_utils import observes

from figure1.common.types import CaseClassification
from figure1.common.types import CaseRejectionReason
from figure1.common.types import CaseState
from figure1.common.types import CaseType
from figure1.common.types import ContentSection
from figure1.common.types import ContentType
from figure1.common.types import FeaturesModel
from figure1.common.types import FeedCardType
from figure1.common.types import Locale
from figure1.core import Base
from figure1.core import HasCreateUpdateDeleteTime
from figure1.core import HasCreateUpdateTime
from figure1.exceptions import CaseNotFound
from figure1.exceptions import ContentNotFound

logger = logging.getLogger(__name__)


class Case(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "c_case"
    case_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    group_uuid = Column(UUID(as_uuid=True), ForeignKey('g_groups.group_uuid', ondelete='SET NULL'), nullable=True)
    state = Column(Enum(CaseState), nullable=False, index=True)
    published_at = Column(DateTime(timezone=True), default=None, nullable=True, index=True)
    is_paging_case = Column(Boolean, nullable=False)
    rejection_reason = Column(Enum(CaseRejectionReason), nullable=True)
    case_type = Column(Enum(CaseType), nullable=False)
    cme1_credits = Column(Float, nullable=True)
    passing_score = Column(Integer, nullable=True)
    synced_at = Column(DateTime(timezone=True))
    language = Column(Text, nullable=True, default=Locale.EN_US.code)
    request_help = Column(Boolean, nullable=True)
    is_anonymous = Column(Boolean, nullable=True)
    case_classification = Column(Enum(CaseClassification), default=CaseClassification.MEDICAL)
    cme_certificates = relationship("CmeCertificateTemplate")
    content = relationship("Content",
                           order_by="asc(Content.display_order)",
                           primaryjoin="and_(Content.case_uuid == Case.case_uuid, Content.deleted_at == None)",
                           uselist=True,
                           backref=backref("case", uselist=False))
    feed_card = relationship("Content",
                             primaryjoin="and_(Content.case_uuid == Case.case_uuid, "
                                         "Content.deleted_at == None,"
                                         "Content.is_feed_card.is_(True))",
                             uselist=False,
                             viewonly=True)

    labels = relationship("Label",
                          secondary='c_case_label',
                          primaryjoin="and_(CaseLabel.case_uuid == Case.case_uuid, CaseLabel.deleted_at == None)",
                          secondaryjoin="CaseLabel.label_uuid == Label.label_uuid")
    diagnoses = relationship("ContentUpdate",
                             secondary="c_content",
                             primaryjoin="Case.case_uuid == Content.case_uuid",
                             secondaryjoin="and_(ContentUpdate.content_uuid == Content.content_uuid, "
                                           "ContentUpdate.update_type == 'DIAGNOSIS', "
                                           "ContentUpdate.deleted_at == None)",
                             viewonly=True)
    group = relationship('Groups', backref='case')
    specialties = relationship("SpecialtyV2",
                               viewonly=True,
                               primaryjoin="(Case.case_uuid==CaseSpecialtyV2.case_uuid)",
                               secondaryjoin="(CaseSpecialtyV2.specialty_uuid==SpecialtyV2.specialty_uuid)",
                               secondary="c_case_specialty")

    @hybrid_property
    def has_diagnosis(self):
        return len(self.diagnoses) != 0

    @hybrid_property
    def is_case_cme(self):
        for any_label in self.labels:
            if any_label.kind == 'case_cme':
                return True

        return False

    @orm.reconstructor
    def __init__(self):
        self._event_author_uuid = None

    def _generate_history_event(self,
                                case_state,
                                group_uuid=None,
                                event_author_uuid=None):
        event = CaseHistory()
        event.event_uuid = uuid.uuid4()
        event.case_uuid = self.case_uuid
        event.case_state = case_state
        if group_uuid:
            event.group_uuid = group_uuid
        if event_author_uuid:
            event.event_author_uuid = event_author_uuid

        self.case_history.append(event)

    @observes('state', 'group_uuid')
    def on_case_state_or_group_uuid_change(self, state, group_uuid):
        self._generate_history_event(case_state=state,
                                     group_uuid=group_uuid,
                                     event_author_uuid=self.event_author_uuid)

    @property
    def event_author_uuid(self):
        return self._event_author_uuid

    @event_author_uuid.setter
    def event_author_uuid(self, event_author_uuid):
        self._event_author_uuid = event_author_uuid

    def as_dict(self):
        return {
            'caseUuid': str(self.case_uuid),
            'state': self.state.name.lower(),
            'language': self.language,
            'publishedAt': self.published_at,
            'isPagingCase': self.is_paging_case,
            'caseType': self.case_type.name.lower()
        }

    def clone(self, session, group_uuid=None):
        make_transient(self)
        self.case_uuid = uuid.uuid4()

        if group_uuid:
            self.group_uuid = group_uuid

        session.add(self)
        session.flush()

        for content in self.content:
            content.clone(session, case_uuid=self.case_uuid)

        return self

    @staticmethod
    def get_case(case_uuid, raise_exception=False, session=None) -> 'Case':
        """
        session is optional, if passed in, the instance of Case retrieved is bound to that session. This is required if
        modifications are going to be adding to a different session.

        """
        if session:
            c = session.query(Case).get(case_uuid)
        else:
            c = Case.q.get(case_uuid)
        if not c and raise_exception:
            raise CaseNotFound(case_uuid=case_uuid)
        return c


class CaseHistory(Base, HasCreateUpdateTime):
    __tablename__ = "h_case_history"
    event_uuid = Column(UUID(as_uuid=True), primary_key=True, unique=True)
    event_author_uuid = Column(UUID(as_uuid=True), nullable=True)
    case_uuid = Column(UUID(as_uuid=True), ForeignKey(Case.case_uuid))
    case_state = Column(Enum(CaseState), nullable=False)
    group_uuid = Column(UUID(as_uuid=True), nullable=True)
    case = relationship('Case', foreign_keys=case_uuid, backref='case_history')


class Features(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "c_features"

    COMMENTS_ENABLED_DEFAULT = True
    COMMENT_QUEUE_ENABLED_DEFAULT = False
    COMMENT_TABS_ENABLED_DEFAULT = True
    DISMISS_BUTTON_DEFAULT = False
    DISMISS_ON_CLICK_DEFAULT = False
    PUBLIC_NOTIFICATIONS_ENABLED_DEFAULT = True
    REACTIONS_ENABLED_DEFAULT = True
    REPORT_ENABLED_DEFAULT = True
    SAVE_ENABLED_DEFAULT = True
    SHARE_ENABLED_DEFAULT = True
    SHOW_IN_MOBILE_DEFAULT = True
    SHOW_IN_WEB_DEFAULT = True
    SHOW_LABELS_DEFAULT = True
    SHOW_VIEWS_DEFAULT = True
    SIMILAR_CASES_ENABLED_DEFAULT = True
    ZOOM_ENABLED_DEFAULT = True

    features_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    comments_enabled = Column(Boolean, default=COMMENTS_ENABLED_DEFAULT, nullable=False)
    comment_queue_enabled = Column(Boolean, default=COMMENT_QUEUE_ENABLED_DEFAULT, nullable=False)
    comment_tabs_enabled = Column(Boolean, default=COMMENT_TABS_ENABLED_DEFAULT, nullable=False)
    dismiss_button = Column(Boolean, default=DISMISS_BUTTON_DEFAULT, nullable=False)
    dismiss_on_click = Column(Boolean, default=DISMISS_ON_CLICK_DEFAULT, nullable=False)
    public_notifications_enabled = Column(Boolean, default=PUBLIC_NOTIFICATIONS_ENABLED_DEFAULT, nullable=False)
    reactions_enabled = Column(Boolean, default=REACTIONS_ENABLED_DEFAULT, nullable=False)
    report_enabled = Column(Boolean, default=REPORT_ENABLED_DEFAULT, nullable=False)
    save_enabled = Column(Boolean, default=SAVE_ENABLED_DEFAULT, nullable=False)
    share_enabled = Column(Boolean, default=SHARE_ENABLED_DEFAULT, nullable=False)
    show_in_mobile = Column(Boolean, default=SHOW_IN_MOBILE_DEFAULT, nullable=False)
    show_in_web = Column(Boolean, default=SHOW_IN_WEB_DEFAULT, nullable=False)
    show_labels = Column(Boolean, default=SHOW_LABELS_DEFAULT, nullable=False)
    show_views = Column(Boolean, default=SHOW_VIEWS_DEFAULT, nullable=False)
    similar_cases_enabled = Column(Boolean, default=SIMILAR_CASES_ENABLED_DEFAULT, nullable=False)
    zoom_enabled = Column(Boolean, default=ZOOM_ENABLED_DEFAULT, nullable=False)
    is_default = Column(Boolean, nullable=False, index=True)

    @staticmethod
    def create_or_update(content_uuid,
                         session,
                         comments_enabled=COMMENTS_ENABLED_DEFAULT,
                         comment_queue_enabled=COMMENT_QUEUE_ENABLED_DEFAULT,
                         comment_tabs_enabled=COMMENT_TABS_ENABLED_DEFAULT,
                         dismiss_button=DISMISS_BUTTON_DEFAULT,
                         dismiss_on_click=DISMISS_ON_CLICK_DEFAULT,
                         public_notifications_enabled=PUBLIC_NOTIFICATIONS_ENABLED_DEFAULT,
                         reactions_enabled=REACTIONS_ENABLED_DEFAULT,
                         report_enabled=REPORT_ENABLED_DEFAULT,
                         save_enabled=SAVE_ENABLED_DEFAULT,
                         share_enabled=SHARE_ENABLED_DEFAULT,
                         show_in_mobile=SHOW_IN_MOBILE_DEFAULT,
                         show_in_web=SHOW_IN_WEB_DEFAULT,
                         show_labels=SHOW_LABELS_DEFAULT,
                         show_views=SHOW_VIEWS_DEFAULT,
                         similar_cases_enabled=SIMILAR_CASES_ENABLED_DEFAULT,
                         zoom_enabled=ZOOM_ENABLED_DEFAULT,
                         skip_commit=False):
        res = session.query(Content, Features) \
            .filter(Content.content_uuid == content_uuid) \
            .join(Features, Features.features_uuid == Content.features_uuid, full=True) \
            .one_or_none()
        c = res[0]
        f = res[1]
        if not f:
            f = Features()
            f.features_uuid = uuid.uuid4()
            c.features_uuid = f.features_uuid

        f.deleted_at = None
        f.is_default = False
        f.comments_enabled = comments_enabled
        f.comment_queue_enabled = comment_queue_enabled
        f.comment_tabs_enabled = comment_tabs_enabled
        f.dismiss_button = dismiss_button
        f.dismiss_on_click = dismiss_on_click
        f.public_notifications_enabled = public_notifications_enabled
        f.reactions_enabled = reactions_enabled
        f.report_enabled = report_enabled
        f.save_enabled = save_enabled
        f.share_enabled = share_enabled
        f.show_in_mobile = show_in_mobile
        f.show_in_web = show_in_web
        f.show_labels = show_labels
        f.show_views = show_views
        f.similar_cases_enabled = similar_cases_enabled
        f.zoom_enabled = zoom_enabled
        session.add(f)

        if skip_commit:
            return f

        try:
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        return f

    @staticmethod
    def set_default(content_uuid,
                    session,
                    skip_commit=False):
        res = session.query(Content, Features) \
            .filter(Content.content_uuid == content_uuid) \
            .join(Features, Features.features_uuid == Content.features_uuid, full=True) \
            .one()

        c = res[0]
        f = res[1]

        if f and f.is_default:
            return
        elif f:
            f.mark_deleted()

        c.features_uuid = Features.get_default_uuid(session=session)

        if skip_commit:
            return

        try:
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        return

    @staticmethod
    def get_default_uuid(session):
        f = session.query(Features) \
            .filter(Features.is_default.is_(True)) \
            .one_or_none()
        if f:
            return f.features_uuid

        f = Features()
        f.features_uuid = uuid.uuid4()
        f.is_default = True
        f.comments_enabled = Features.COMMENTS_ENABLED_DEFAULT
        f.comment_queue_enabled = Features.COMMENT_QUEUE_ENABLED_DEFAULT
        f.comment_tabs_enabled = Features.COMMENT_TABS_ENABLED_DEFAULT
        f.dismiss_button = Features.DISMISS_BUTTON_DEFAULT
        f.dismiss_on_click = Features.DISMISS_ON_CLICK_DEFAULT
        f.public_notifications_enabled = Features.PUBLIC_NOTIFICATIONS_ENABLED_DEFAULT
        f.reactions_enabled = Features.REACTIONS_ENABLED_DEFAULT
        f.report_enabled = Features.REPORT_ENABLED_DEFAULT
        f.save_enabled = Features.SAVE_ENABLED_DEFAULT
        f.share_enabled = Features.SHARE_ENABLED_DEFAULT
        f.show_in_mobile = Features.SHOW_IN_MOBILE_DEFAULT
        f.show_in_web = Features.SHOW_IN_WEB_DEFAULT
        f.show_labels = Features.SHOW_LABELS_DEFAULT
        f.show_views = Features.SHOW_VIEWS_DEFAULT
        f.similar_cases_enabled = Features.SIMILAR_CASES_ENABLED_DEFAULT
        f.zoom_enabled = Features.ZOOM_ENABLED_DEFAULT
        session.add(f)
        try:
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        return f.features_uuid

    def as_object(self):
        return FeaturesModel.from_orm(self)

    def as_dict(self):
        return self.as_object().dict()


class SponsoredContent(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "c_sponsored_content"

    sponsored_content_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    sponsored_text = Column(Text)
    disclosure_text = Column(Text)
    job_code = Column(Text)

    @staticmethod
    def create_or_update(content_uuid,
                         session,
                         sponsored_text=None,
                         disclosure_text=None,
                         job_code=None,
                         skip_commit=False):
        res = session.query(Content, SponsoredContent) \
            .filter(Content.content_uuid == content_uuid) \
            .join(SponsoredContent,
                  SponsoredContent.sponsored_content_uuid == Content.sponsored_content_uuid, full=True) \
            .one_or_none()
        c = res[0]
        sc = res[1]
        if not sc:
            sc = SponsoredContent()
            sc.sponsored_content_uuid = uuid.uuid4()
            c.sponsored_content_uuid = sc.sponsored_content_uuid

        sc.deleted_at = None
        if sponsored_text:
            sc.sponsored_text = sponsored_text
        if disclosure_text:
            sc.disclosure_text = disclosure_text
        if job_code:
            sc.job_code = job_code
        session.add(sc)

        if skip_commit:
            return sc

        try:
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        return sc

    @staticmethod
    def delete(content_uuid,
               session,
               skip_commit=False):
        res = session.query(Content, SponsoredContent) \
            .filter(Content.content_uuid == content_uuid) \
            .join(SponsoredContent,
                  SponsoredContent.sponsored_content_uuid == Content.sponsored_content_uuid, full=True) \
            .one_or_none()
        c = res[0]
        sc = res[1]
        if not sc:
            return

        c.sponsored_content_uuid = None
        sc.mark_deleted()

        if skip_commit:
            return

        try:
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        return

    def as_dict(self):
        return {
            'sponsoredContentUuid': str(self.sponsored_content_uuid),
            'sponsoredText': self.sponsored_text,
            'disclosureText': self.disclosure_text,
            'jobCode': self.job_code,
        }


class ContentExtension(Base, HasCreateUpdateTime):
    __tablename__ = "c_content_extension"

    content_extension_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    button_text = Column(Text)
    button_url = Column(Text)
    question_answer_details = Column(Text)
    external_link_url = Column(Text)
    external_link_text = Column(Text)
    heading = Column(Text)
    colour = Column(Text)
    isi_link = Column(Text)
    isi_text = Column(Text)
    isi_embedded_content_link = Column(Text)
    feed_card_label = Column(Text)
    feed_card_title = Column(Text)
    references = Column(Text)

    def as_dict(self):
        return {
            "contentExtensionUuid": str(self.content_extension_uuid),
            "buttonText": self.button_text,
            "buttonUrl": self.button_url,
            'externalLinkUrl': self.external_link_url,
            'externalLinkText': self.external_link_text,
            "questionAnswerDetails": self.question_answer_details,
            "heading": self.heading,
            "colour": self.colour,
            "isiLink": self.isi_link,
            "isiText": self.isi_text,
            "isiEmbeddedContentLink": self.isi_embedded_content_link,
            "feedCardLabel": self.feed_card_label,
            "feedCardTitle": self.feed_card_title,
            "references": self.references,
        }


class Content(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "c_content"

    content_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    case_uuid = Column(UUID(as_uuid=True), ForeignKey(Case.case_uuid), index=True)
    sponsored_content_uuid = Column(UUID(as_uuid=True), ForeignKey(SponsoredContent.sponsored_content_uuid))
    extension_uuid = Column(UUID(as_uuid=True), ForeignKey(ContentExtension.content_extension_uuid))
    features_uuid = Column(UUID(as_uuid=True), ForeignKey(Features.features_uuid))
    display_order = Column(Integer, index=True, nullable=False)
    content_type = Column(Enum(ContentType), nullable=False)
    title = Column(String(10000), default=None, nullable=True)
    caption = Column(String(100000), nullable=True)
    is_feed_card = Column(Boolean, nullable=False)
    feed_card_type = Column(Enum(FeedCardType), nullable=True)
    section = Column(Enum(ContentSection), nullable=True)
    has_comments = Column(Boolean, default=False)
    comments = relationship("Comment", backref=backref('content', uselist=False))
    approved_comments_count = Column(Integer, default=0)
    reported_comments_count = Column(Integer, default=0)
    translation = relationship('ContentTranslation', backref='content', uselist=True)
    sponsored_content = relationship("SponsoredContent",
                                     backref=backref("content", uselist=False))
    features = relationship("Features", uselist=False, backref=backref("content", uselist=False))
    extension = relationship("ContentExtension",
                             uselist=False,
                             backref=backref("content", uselist=False))
    updates = relationship("ContentUpdate",
                           backref="content",
                           primaryjoin="and_(ContentUpdate.content_uuid == Content.content_uuid,"
                                       "ContentUpdate.deleted_at == None)",
                           order_by="ContentUpdate.created_at",
                           uselist=True)
    media = relationship("Media",
                         backref="content",
                         primaryjoin="and_(Media.content_uuid == Content.content_uuid, Media.deleted_at == None)",
                         order_by="Media.display_order",
                         uselist=True)

    accepted_answer = relationship("Comment",
                                   primaryjoin="and_(Comment.content_uuid == Content.content_uuid,"
                                               "Comment.is_accepted_answer.is_(True))",
                                   viewonly=True,
                                   uselist=False)

    def as_dict(self):
        return {
            'contentUuid': str(self.content_uuid),
            'caseUuid': str(self.case_uuid),
            'title': self.title,
            'caption': self.caption,
            'contentType': self.content_type.name.lower(),
            'displayOrder': self.display_order,
            'isFeedCard': self.is_feed_card,
            'feedCardType': self.feed_card_type.name.lower() if self.feed_card_type else None,
            'section': self.section.name.lower() if self.section else None,
        }

    def clone(self, session, case_uuid):
        make_transient(self)
        self.content_uuid = uuid.uuid4()

        if not case_uuid:
            raise ValueError("A case uuid is required.")
        self.case_uuid = case_uuid

        session.add(self)
        session.flush()

        for each in self.media:
            each.clone(session, content_uuid=self.content_uuid, case_uuid=self.case_uuid)

        return self

    @staticmethod
    def get_content(content_uuid, raise_exception=False, session=None) -> Optional['Content']:
        """
        session is optional, pass it in if you require the resulting instance to be bound to a specific instance.
        This is often needed if you have to manipulate the object.
        """
        if session:
            c = session.query(Content).get(content_uuid)
        else:
            c = Content.q.get(content_uuid)
        if not c and raise_exception:
            raise ContentNotFound(content_uuid=content_uuid)
        return c

    @staticmethod
    def get_first_content_item(content_uuid=None, case_uuid=None, session=None) -> Optional['Content']:
        """
        Given a content_uuid or a case_uuid return the content item that is first. This is relevant for comments only
        as they should always attach to the first content item.
        :param content_uuid:
        :param case_uuid:
        :param session:
        :return:
        """

        def _check_for_orphaned_comments(content):
            content_comment_uuid = None
            if content is not None:
                for c in content.case.content:
                    if c.has_comments is True:
                        content_comment_uuid = c.content_uuid
                        break
                for c in content.case.content:
                    if content_comment_uuid is None:
                        break
                    if c.has_comments is None or c.has_comments is False:
                        if c.comments:
                            logger.error("Correcting comments with an incorrect content uuid")
                            for comment in c.comments:
                                comment.content_uuid = content_comment_uuid
                        c.has_comments = False
                    else:
                        continue
            return content

        if case_uuid is None and content_uuid is not None:
            content_item = Content.get_content(content_uuid=content_uuid, raise_exception=True, session=session)
            if content_item is not None:
                case_uuid = content_item.case_uuid
            if content_item.has_comments is True:
                return content_item
            if content_item.display_order == 0:
                content_item.has_comments = True
                updated = session.merge(content_item)
                session.flush()
                return _check_for_orphaned_comments(updated)
        q = session.query(Content).filter(Content.case_uuid == case_uuid, Content.display_order == 0)
        content_item = q.one_or_none()
        if content_item:
            if content_item.has_comments is True:
                return content_item
            content_item.has_comments = True
            updated = session.merge(content_item)
            session.flush()
            return _check_for_orphaned_comments(updated)
        return None


class CaseAuthor(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "c_case_author"
    case_uuid = Column(UUID(as_uuid=True), ForeignKey('c_case.case_uuid'), primary_key=True)
    author_uuid = Column(UUID(as_uuid=True), ForeignKey('u_user.user_uuid'), primary_key=True)
    author = relationship("User")

    @staticmethod
    def create(case_uuid, author_uuid, skip_commit=False, session=None):
        ca = CaseAuthor()
        ca.case_uuid = case_uuid
        ca.author_uuid = author_uuid
        ca.deleted_at = None
        return session.merge(ca)

    def as_dict(self):
        return {
            'caseUuid': str(self.case_uuid),
            'authorUuid': str(self.author_uuid),
        }


class ContentTranslation(Base, HasCreateUpdateTime):
    __tablename__ = 'c_content_translation'

    content_uuid = Column(UUID(as_uuid=True), ForeignKey('c_content.content_uuid'), primary_key=True)
    case_uuid = Column(UUID(as_uuid=True), ForeignKey('c_case.case_uuid'))
    source_language = Column(Text, nullable=True, default=Locale.EN_US.code)
    target_language = Column(Text, default=Locale.EN_US.code, primary_key=True)
    title = Column(String(10000), nullable=True)
    caption = Column(String(100000), nullable=True)
