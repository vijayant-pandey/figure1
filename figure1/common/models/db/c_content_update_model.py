import uuid
from typing import Iterable

from sqlalchemy import Column, ForeignKey, Text, String, Enum, and_
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from figure1.common.types.case import ContentUpdateType
from figure1.core import Base, HasCreateUpdateDeleteTime
from figure1.common.models.db import Content


class ContentUpdate(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "c_content_update"

    update_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    content_uuid = Column(UUID(as_uuid=True), ForeignKey(Content.content_uuid), index=True)
    text = Column(String(100000), nullable=False)
    update_type = Column(Enum(ContentUpdateType), nullable=False, default=ContentUpdateType.UPDATE)
    linked_update_uuid = Column(UUID(as_uuid=True), nullable=True)

    translation = relationship('ContentUpdateTranslations', backref='content_update', uselist=True)

    @staticmethod
    def create(session,
               content_uuid,
               text,
               update_type,
               linked_update_uuid=None,
               skip_commit=False):
        def _create_update():
            u = ContentUpdate()
            u.update_uuid = uuid.uuid4()
            u.content_uuid = content_uuid
            u.text = text
            u.update_type = update_type
            u.linked_update_uuid = linked_update_uuid
            session.add(u)
            return u

        if update_type is ContentUpdateType.DIAGNOSIS:
            u = session.query(ContentUpdate) \
                .filter(ContentUpdate.update_type == ContentUpdateType.DIAGNOSIS,
                        ContentUpdate.content_uuid == content_uuid,
                        ContentUpdate.deleted_at.is_(None)) \
                .one_or_none()
            if u:
                if text:
                    u.text = text
                else:
                    u.mark_deleted()
            elif text:
                u = _create_update()
        elif text:
            u = _create_update()
        else:
            u = None

        if skip_commit:
            return u

        try:
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        return u

    def as_dict(self):
        return {
            'updateUuid': str(self.update_uuid),
            'contentUuid': str(self.content_uuid),
            'text': str(self.text),
            'updateType': str(self.update_type)
        }


class ContentUpdateTranslations(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "c_content_update_translations"

    update_uuid = Column(UUID(as_uuid=True), ForeignKey(ContentUpdate.update_uuid), index=True, primary_key=True)
    language = Column(Text, primary_key=True)
    text = Column(Text, nullable=False)

    @staticmethod
    def get_translated_languages_by_content_uuid(content_uuid, session) -> Iterable[str]:
        """
        Returns an iterable of all translated(for a Content) language codes(e.g., ES_ES, PT_PT) by content_uuid.

        :param session: Session
        :param content_uuid: str
        :return: Iterable[str]
        """
        for translated_language in session.query(ContentUpdateTranslations.language)\
                                          .join(ContentUpdate, and_(ContentUpdate.content_uuid == content_uuid,
                                                ContentUpdate.update_uuid == ContentUpdateTranslations.update_uuid))\
                                          .all():
            yield translated_language[0]

    @staticmethod
    def create(update_uuid,
               text,
               language,
               session):
        content_update_translation = ContentUpdateTranslations()
        content_update_translation.update_uuid = update_uuid
        content_update_translation.language = language
        content_update_translation.text = text

        return session.merge(content_update_translation)
