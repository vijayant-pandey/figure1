import os
import uuid
from sqlalchemy import Column, ForeignKey, Text, Boolean, or_
from sqlalchemy.dialects.postgresql import UUID

from figure1.core import Base, HasCreateUpdateDeleteTime
from figure1.common.utils import case_image_path
from .c_media_model import Media
from .c_case_model import Content
from .user_models import User


class CaseEdit(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "m_case_edit"

    edit_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    content_uuid = Column(UUID(as_uuid=True), ForeignKey(Content.content_uuid), index=True)
    moderator_uuid = Column(UUID(as_uuid=True), ForeignKey(User.user_uuid))
    title = Column(Text, nullable=True)
    caption = Column(Text, nullable=True)
    language = Column(Text, nullable=True)
    diagnosis = Column(Text, nullable=True)
    edit_approved = Column(Boolean, default=False, nullable=True)
    edit_applied = Column(Boolean, default=False, nullable=True)
    edit_updated_by = Column(UUID(as_uuid=True), ForeignKey(User.user_uuid))

    @staticmethod
    def create(content_uuid,
               moderator_uuid,
               session,
               title=None,
               caption=None,
               language=None,
               diagnosis=None):
        """
        If the content_uuid exists in an edit and that edit hasn't been applied, then update that edit. Otherwise,
        create a new edit entry
        """
        ce = session.query(CaseEdit).filter(CaseEdit.content_uuid == content_uuid,
                                            or_(CaseEdit.edit_applied.is_(False),
                                                CaseEdit.edit_applied.is_(None))
                                            ) \
            .one_or_none()
        if ce:
            if title:
                ce.title = title
            if caption:
                ce.caption = caption
            if language:
                ce.language = language
            if diagnosis is not None:
                ce.diagnosis = diagnosis
        else:
            ce = CaseEdit()
            ce.edit_uuid = uuid.uuid4()
            ce.content_uuid = content_uuid
            ce.moderator_uuid = moderator_uuid
            ce.title = title
            ce.caption = caption
            ce.language = language
            ce.diagnosis = diagnosis

        return session.merge(ce)

    @staticmethod
    def apply_edit(edit_uuid, moderator_uuid, session):
        session.query(CaseEdit).filter(CaseEdit.edit_uuid == edit_uuid) \
            .update({'edit_approved': True, 'edit_updated_by': moderator_uuid, 'edit_applied': True})
        try:
            session.commit()
        except Exception as e:
            session.rollback()
            raise e

    @staticmethod
    def reject_edit(edit_uuid, moderator_uuid, session):
        session.query(CaseEdit).filter(CaseEdit.edit_uuid == edit_uuid) \
            .update({'edit_approved': False, 'edit_updated_by': moderator_uuid, 'edit_applied': False})
        edit = session.query(CaseEdit).get(edit_uuid)
        edit.mark_deleted()
        try:
            session.commit()
        except Exception as e:
            session.rollback()
            raise e

    def as_dict(self):
        return {
            'editUuid': str(self.edit_uuid),
            'contentUuid': str(self.content_uuid),
            'moderatorUuid': str(self.moderator_uuid),
            'title': str(self.title),
            'caption': str(self.caption),
            'language': str(self.language),
            'diagnosis': str(self.diagnosis),
            'createdAt': str(self.created_at),
            'updatedAt': str(self.updated_at),
        }

    def as_firestore_dict(self, session):
        moderator = session.query(User).filter(User.user_uuid == self.moderator_uuid).one_or_none()
        if not moderator:
            return None

        dict = {
            'createdAt': str(self.created_at),
            'updatedAt': str(self.updated_at),
            'editUuid': str(self.edit_uuid),
            'moderatorUuid': str(self.moderator_uuid),
            'moderatorUid': moderator.user_uid,
            'moderatorUsername': moderator.username,
        }
        if self.title:
            dict['title'] = self.title
        if self.caption:
            dict['caption'] = self.caption
        if self.language:
            dict['language'] = self.language
        if self.diagnosis is not None:
            dict['diagnosis'] = self.diagnosis
        return dict


class CaseMediaEdit(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "m_case_media_edit"

    media_edit_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    media_uuid = Column(UUID(as_uuid=True), ForeignKey(Media.media_uuid), index=True)
    moderator_uuid = Column(UUID(as_uuid=True), ForeignKey(User.user_uuid))
    filename = Column(Text, nullable=True)
    edit_approved = Column(Boolean, default=False, nullable=True)
    edit_applied = Column(Boolean, default=False, nullable=True)
    edit_updated_by = Column(UUID(as_uuid=True), ForeignKey(User.user_uuid))

    @staticmethod
    def create(media_uuid, moderator_uuid, session, filename, skip_commit=False):

        ce = session.query(CaseMediaEdit).filter(CaseMediaEdit.media_uuid == media_uuid,
                                                 or_(CaseMediaEdit.edit_applied.is_(False),
                                                     CaseMediaEdit.edit_applied.is_(None))
                                                 ) \
            .one_or_none()
        if not ce:
            ce = CaseMediaEdit()
            ce.media_edit_uuid = uuid.uuid4()
        ce.media_uuid = media_uuid
        ce.moderator_uuid = moderator_uuid
        ce.filename = filename
        return session.merge(ce)

    @staticmethod
    def apply_edit(media_edit_uuid, moderator_uuid, session):
        cme = CaseMediaEdit()
        cme.media_edit_uuid = media_edit_uuid
        cme.edit_applied = True
        cme.edit_approved = True
        cme.edit_updated_by = moderator_uuid
        return session.merge(cme)

    @staticmethod
    def reject_edit(media_edit_uuid, moderator_uuid, session):
        cme = CaseMediaEdit()
        cme.media_edit_uuid = media_edit_uuid
        cme.edit_applied = False
        cme.edit_approved = False
        cme.edit_updated_by = moderator_uuid
        cme.mark_deleted()
        return session.merge(cme)

    def as_dict(self):
        return {
            'createdAt': str(self.created_at),
            'updatedAt': str(self.updated_at),
            'mediaEditUuid': str(self.media_edit_uuid),
            'mediaUuid': str(self.media_uuid),
            'moderatorUuid': str(self.moderator_uuid),
            'filename': str(self.filename),
        }

    def as_firestore_dict(self, session):
        moderator = session.query(User).filter(User.user_uuid == self.moderator_uuid).one_or_none()
        if not moderator:
            return None

        base_url = os.environ.get('FIGURE1_IMGIX_URL', 'https://figure1-pro-prod.imgix.net/')
        url = f"{base_url}{case_image_path}/{self.filename}"

        return {
            'createdAt': str(self.created_at),
            'editUuid': str(self.media_edit_uuid),
            'mediaUuid': str(self.media_uuid),
            'moderatorUuid': str(self.moderator_uuid),
            'moderatorUid': moderator.user_uid,
            'moderatorUsername': moderator.username,
            'filename': self.filename,
            'url': url
        }
