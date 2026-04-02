import logging
import uuid
from typing import Optional

from sqlalchemy import Column, Text, Index, ForeignKey, func, Boolean, Enum, and_
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, remote, foreign, backref, make_transient
from sqlalchemy_utils import LtreeType, Ltree, observes

from figure1.core import Base, HasCreateUpdateDeleteTime, translate_client
from figure1.common.types import Locale, \
    ReportReason, \
    CommentState, \
    CommentModel, \
    ParentCommentModel, \
    CommentRejectionReason
from figure1.exceptions import CommentNotFound


class Comment(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "c_comment"
    comment_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    author_uuid = Column(UUID(as_uuid=True), ForeignKey('u_user.user_uuid'), index=True)
    content_uuid = Column(UUID(as_uuid=True), ForeignKey('c_content.content_uuid'), index=True, nullable=False)
    text = Column(Text, nullable=False)
    language = Column(Text)
    path = Column(LtreeType, nullable=False)
    replyable = Column(Boolean, default=True)
    state = Column(Enum(CommentState), nullable=False, index=True)
    rejection_reason = Column(Enum(CommentRejectionReason), nullable=True)
    edited = Column(Boolean, nullable=True, default=False)
    is_accepted_answer = Column(Boolean, default=False, nullable=True)
    is_anonymous = Column(Boolean, nullable=True)
    moderator_reviewed = Column(Boolean, default=False, nullable=True)

    parent = relationship(
        'Comment',
        primaryjoin=and_(remote(path) == foreign(func.subpath(path, 0, -1)),
                         remote(content_uuid) == foreign(content_uuid)),
        backref=backref("children", uselist=True, sync_backref=False),
        viewonly=True,
        sync_backref=False,
    )

    def _generate_history_event(self, state, text):
        h = CommentHistory()
        h.event_uuid = uuid.uuid4()
        h.comment_uuid = self.comment_uuid
        h.event_author = self.author_uuid
        if state:
            h.comment_state = state.name
        if text:
            h.comment_text = text
        self.comment_history.append(h)

    @observes('text', 'state')
    def on_comment_change(self, text, state):
        self._generate_history_event(state, text)

    @staticmethod
    def _validate_uuid(local_uuid) -> uuid.UUID:
        """
        Make sure the uuid is valid, can be a string or uuid object, but a valid uuid object is always returned.
        :param local_uuid: UUID to check, can be a string or a UUID object
        :raises ValueError: If the uuid is not valid
        :returns: uuid.UUID
        """
        if isinstance(local_uuid, uuid.UUID):
            return local_uuid
        if isinstance(local_uuid, str):
            return uuid.UUID(local_uuid)
        raise ValueError("Invalid uuid")

    @staticmethod
    def create(author_uuid,
               content_uuid,
               text,
               state,
               session,
               language=None,
               parent_uuid=None,
               is_anonymous=False):
        c = Comment()
        c.comment_uuid = uuid.uuid4()
        c.author_uuid = author_uuid
        c.content_uuid = content_uuid
        c.text = text
        c.language = language
        c.state = state
        c.is_anonymous = is_anonymous
        parent = session.query(Comment) \
            .filter(Comment.comment_uuid == parent_uuid) \
            .one_or_none() if parent_uuid else None

        if parent:
            c.path = Ltree(parent.path.path + "." + c.comment_uuid.hex)
        else:
            c.path = Ltree(c.comment_uuid.hex)
        return session.merge(c)

    def as_dict(self):
        return {
            'commentUuid': str(self.comment_uuid),
            'authorUuid': str(self.author_uuid) if self.author_uuid and not self.is_anonymous else None,
            'contentUuid': str(self.content_uuid),
            'text': self.text,
            'language': self.language,
            'path': self.path.path,
            'replyable': self.replyable,
            'createdAt': str(self.created_at),
            'deletedAt': str(self.deleted_at),
            'updatedAt': str(self.updated_at),
            'state': self.state.name.lower(),
            'isAcceptedAnswer': self.is_accepted_answer,
            'isAnonymous': self.is_anonymous,
            'moderatorReviewed': self.moderator_reviewed,
        }

    def as_object(self):
        return CommentModel.from_orm(self)

    def as_tree_object(self):
        return ParentCommentModel.from_orm(self)

    @staticmethod
    def get_comment(comment_uuid, session=None):
        c = session.query(Comment).get(comment_uuid)
        if not c:
            raise CommentNotFound(comment_uuid=comment_uuid)
        return c

    @staticmethod
    def get_content_commenters(content_uuid, session):
        return [str(each.author_uuid) for each in
                session.query(Comment).filter(Comment.content_uuid == content_uuid,
                                              Comment.state == 'APPROVED',
                                              Comment.deleted_at.is_(None)).all()]

    @staticmethod
    def get_comment_count(user_uuid=None, content_uuid=None, include_anonymous=True):
        q = Comment.q.session.query(func.count(Comment.comment_uuid),
                                    Comment.state) \
            .group_by(Comment.state)
        if user_uuid:
            result_dict = dict(approved_comment_count=0,
                               reported_comment_count=0,
                               deleted_comment_count=0)
            user_uuid = Comment._validate_uuid(user_uuid)
            q = q.filter(Comment.author_uuid == user_uuid)
            if not include_anonymous:
                q = q.filter(Comment.is_anonymous.is_not(True))
            for result in q.all():
                if result[1] == CommentState.APPROVED:
                    result_dict.update({'approved_comment_count': result[0]})
                if result[1] == CommentState.REPORTED:
                    result_dict.update({'reported_comment_count': result[0]})
                if result[1] == CommentState.DELETED:
                    result_dict.update({'deleted_comment_count': result[0]})
            return result_dict
        elif content_uuid:
            content_uuid = Comment._validate_uuid(content_uuid)
            q = q.filter(Comment.content_uuid == content_uuid)
            if not include_anonymous:
                q = q.filter(Comment.is_anonymous.is_not(True))
            result_dict = dict(approved_comments_count=0,
                               reported_comments_count=0)
            for result in q.all():
                if result[1] == CommentState.APPROVED:
                    result_dict.update({'approved_comments_count': result[0]})
                if result[1] == CommentState.REPORTED:
                    result_dict.update({'reported_comments_count': result[0]})
            return result_dict
        else:
            return {}

    @staticmethod
    def get_user_aggregate_counts(session):
        """
        Generator method that yields the dicts of user comment counts. Only needed to do a bulk update of user comment
        counts
        """
        result_dict = dict(approved_comment_count=0,
                           reported_comment_count=0,
                           deleted_comment_count=0,
                           author_uuid=None)
        if session is None:
            return
        q = session.query(func.count(Comment.comment_uuid), Comment.state, Comment.author_uuid) \
            .group_by(Comment.author_uuid, Comment.state)
        for result in q.yield_per(1000).all():
            if result[2] is None:
                continue
            else:
                result_dict.update({'author_uuid': result[2]})

            if result[1] == CommentState.APPROVED:
                result_dict.update({'approved_comment_count': result[0]})
            if result[1] == CommentState.REPORTED:
                result_dict.update({'reported_comment_count': result[0]})
            if result[1] == CommentState.DELETED:
                result_dict.update({'deleted_comment_count': result[0]})
            yield result_dict

    @staticmethod
    def get_content_aggregate_counts(session=None):
        """
        Generator method that yields a dict of comment counts by content_uuid. Normally used for bulk updating comment
        counts.

        """
        result_dict = dict(approved_comment_count=0,
                           reported_comment_count=0,
                           deleted_comment_count=0,
                           content_uuid=None)
        if session is None:
            return
        q = session.query(func.count(Comment.comment_uuid), Comment.state, Comment.content_uuid) \
            .group_by(Comment.author_uuid, Comment.state)
        for result in q.yield_per(1000).all():
            if result[2] is None:
                continue
            else:
                result_dict.update({'content_uuid': result[2]})

            if result[1] == CommentState.APPROVED:
                result_dict.update({'approved_comment_count': result[0]})
            if result[1] == CommentState.REPORTED:
                result_dict.update({'reported_comment_count': result[0]})
            if result[1] == CommentState.DELETED:
                result_dict.update({'deleted_comment_count': result[0]})
            yield result_dict


class CommentReport(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "c_comment_report"
    comment_report_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    user_uuid = Column(UUID(as_uuid=True), ForeignKey('u_user.user_uuid'), index=True)
    comment_uuid = Column(UUID(as_uuid=True), ForeignKey(Comment.comment_uuid), index=True, nullable=False)
    text = Column(Text)
    report_reason = Column(Enum(ReportReason))
    language = Column(Text)
    moderator_approved = Column(Boolean, default=False)
    moderator_reviewed = Column(Boolean, default=False)
    moderator_uuid = Column(UUID(as_uuid=True), ForeignKey('u_user.user_uuid'), nullable=True)
    comment = relationship('Comment', backref='report')

    @observes('user_uuid')
    def on_comment_report(self, user_uuid):
        h = CommentHistory()
        h.event_uuid = uuid.uuid4()
        h.comment_uuid = self.comment_uuid
        h.comment_report_record = self.comment_report_uuid
        h.comment_history_description = 'New Comment report'
        if user_uuid:
            h.event_author = user_uuid
        self.comment_history.append(h)

    @observes('report_reason', 'text', 'moderator_uuid', 'moderator_approved', 'moderator_reviewed')
    def on_comment_report_change(self, report_reason, text, moderator_uuid, moderator_approved, moderator_reviewed):
        h = CommentHistory()
        h.event_uuid = uuid.uuid4()
        h.comment_uuid = self.comment_uuid
        h.comment_report_record = self.comment_report_uuid
        if moderator_approved and moderator_uuid:
            h.comment_approved_by = moderator_uuid
        if moderator_reviewed and moderator_uuid:
            h.comment_reviewed_by = moderator_uuid
        if report_reason:
            h.comment_report_reason = report_reason.name
        if text:
            h.comment_report_text = text
        self.comment_history.append(h)

    @staticmethod
    def create_report(user_uuid, comment_uuid, report_reason, text, skip_commit=False, language=None, session=None):
        is_approved = session.query(CommentReport) \
            .filter(CommentReport.comment_uuid == comment_uuid) \
            .filter(CommentReport.moderator_approved).first()
        if is_approved:
            return {'error': 'Comment has been approved by moderators'}

        report = session.query(CommentReport) \
            .filter(CommentReport.comment_uuid == comment_uuid) \
            .filter(CommentReport.user_uuid == user_uuid).one_or_none()
        if report:
            return {'error': 'User has already reported this comment'}
        else:
            report = CommentReport()
            report.comment_report_uuid = uuid.uuid4()
            report.report_reason = report_reason
            report.user_uuid = user_uuid
            report.comment_uuid = comment_uuid
            report.text = text
            if language:
                if not Locale.is_supported(language):
                    logging.error(f"Unsupported language constant {language}")
            else:
                language = Locale.EN_US.code
            report.language = language
            session.add(report)
            cm = session.query(Comment).get(comment_uuid)
            cm.state = CommentState.REPORTED
            session.add(cm)
            session.flush()

        return report


class CommentTranslations(Base, HasCreateUpdateDeleteTime):
    __tablename__ = 't_comment_translations'
    translation_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    comment_uuid = Column(UUID(as_uuid=True), ForeignKey('c_comment.comment_uuid'), index=True)
    language = Column(Text)
    text = Column(Text, nullable=False)
    comment = relationship("Comment", uselist=False, backref=backref("translations", uselist=True))

    @staticmethod
    def translate(comment_uuid, to_language, from_language=None) -> Optional['CommentTranslations']:
        comment = Comment.q.get(comment_uuid)
        if not comment:
            return None
        if not Locale.is_supported(to_language):
            logging.error("Language %s is unsupported", to_language)
            raise Exception("Unsupported Language")
        to_lang = Locale.get_from_code(to_language)
        trans = translate_client()
        if trans is None:
            return None
        logging.info("Translating text %s", comment.text)
        translation = CommentTranslations.q.filter(
            CommentTranslations.comment_uuid == comment_uuid,
            CommentTranslations.language == to_lang.code) \
            .one_or_none()
        translated_text = trans.translate(target_language=to_lang.language_code, values=comment.text)['translatedText']
        if not translation:
            translation = CommentTranslations()
            translation.translation_uuid = uuid.uuid4()
        translation.comment_uuid = comment_uuid
        translation.language = to_lang.code
        translation.text = translated_text
        make_transient(translation)
        return translation

    @staticmethod
    def update_translations(comment_uuid, session):
        for t in session.query(CommentTranslations).filter(CommentTranslations.comment_uuid == comment_uuid):
            updated = CommentTranslations.translate(comment_uuid=comment_uuid, to_language=t.language)
            if updated is None:
                continue
            session.merge(updated)
        session.flush()


class CommentHistory(Base, HasCreateUpdateDeleteTime):
    __tablename__ = 'h_comment_history'
    event_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    event_author = Column(UUID(as_uuid=True), ForeignKey('u_user.user_uuid'), index=True)
    comment_uuid = Column(UUID(as_uuid=True), ForeignKey(Comment.comment_uuid), index=True)
    comment_author = Column(UUID(as_uuid=True), ForeignKey('u_user.user_uuid'), index=True)
    comment_reported_by = Column(UUID(as_uuid=True), ForeignKey('u_user.user_uuid'))
    comment_approved_by = Column(UUID(as_uuid=True), ForeignKey('u_user.user_uuid'))
    comment_reviewed_by = Column(UUID(as_uuid=True), ForeignKey('u_user.user_uuid'))
    comment_report_record = Column(UUID(as_uuid=True), ForeignKey(CommentReport.comment_report_uuid))
    comment_state = Column(Text)
    comment_text = Column(Text, nullable=True)
    comment_report_text = Column(Text, nullable=True)
    comment_report_reason = Column(Text)
    comment_history_description = Column(Text)
    comment = relationship('Comment', foreign_keys=comment_uuid, backref='comment_history')
    comment_report = relationship('CommentReport', foreign_keys=comment_report_record, backref='comment_history')
