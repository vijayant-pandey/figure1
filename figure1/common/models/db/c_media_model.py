import logging
import os
import uuid

from typing import Optional
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, Enum, Text, ForeignKey, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import make_transient

from figure1.common.types import MediaType, MediaModel, MediaModelByCase
from figure1.core import Base, HasCreateUpdateDeleteTime
from figure1.common.utils import case_image_path, VimeoClient
from figure1.exceptions import VimeoError
from .c_case_model import Content


class Media(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "c_media"

    media_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    case_uuid = Column(UUID(as_uuid=True), index=True)
    content_uuid = Column(UUID(as_uuid=True), ForeignKey(Content.content_uuid), index=True)
    type = Column(Enum(MediaType), nullable=False)
    legacy_id = Column(Text, index=True)
    filename = Column(Text)
    display_order = Column(Integer, default=0)
    width = Column(Integer, default=0)
    height = Column(Integer, default=0)
    original_filename = Column(Text)
    is_feed_card_media = Column(Boolean, nullable=False, default=False)
    video_url = Column(Text)
    video_url_generated_at = Column(DateTime(timezone=True))
    filename_exists = Column(Boolean, nullable=True, default=True)
    original_filename_exists = Column(Boolean, nullable=True, default=True)
    checked_at = Column(DateTime(timezone=True), default=None, nullable=True)

    @staticmethod
    def create(content_uuid,
               media_type,
               session,
               filename=None,
               original_filename=None,
               display_order=0,
               width=None,
               height=None,
               is_feed_card_media=False,
               filename_exists=None,
               original_filename_exists=None,
               checked_at=None,
               skip_commit=False):
        media = Media()
        media.media_uuid = uuid.uuid4()
        media.content_uuid = content_uuid
        media.type = media_type
        media.filename = filename
        media.original_filename = original_filename
        media.display_order = display_order
        media.width = width
        media.height = height
        media.is_feed_card_media = is_feed_card_media
        media.checked_at = checked_at
        media.filename_exists = filename_exists
        media.original_filename_exists = original_filename_exists
        media.regenerate_video_url()

        session.add(media)
        session.flush()

        return media

    def as_dict(self):
        return self.as_object().dict()

    def clone(self, session, content_uuid=None, case_uuid=None):
        make_transient(self)
        self.media_uuid = uuid.uuid4()

        if content_uuid:
            self.content_uuid = content_uuid

        if case_uuid:
            self.case_uuid = case_uuid

        session.add(self)
        session.flush()
        return self

    def as_object(self) -> MediaModel:
        return MediaModel.from_orm(self)

    @staticmethod
    def as_case_object(case_uuid, session) -> MediaModelByCase:
        """
        Returns an object containing the feedCard as a standalone object, and a dictionary keyed by content_uuid each
        containing an ordered list of media for that content item.
        :param case_uuid:
        :param session:
        :return:
        """
        feed_card_media = None
        content_media = {}
        for c in session.query(Media, Content) \
                .filter(Content.case_uuid == case_uuid) \
                .join(Media, Content.content_uuid == Media.content_uuid).all():
            m = c[0]
            if m.is_feed_card_media:
                feed_card_media = m.as_object()
            else:
                media_ob = m.as_object()
                if media_ob.contentUuid in content_media:
                    content_media[media_ob.contentUuid].append(media_ob)
                else:
                    content_media.update({media_ob.contentUuid: [media_ob]})
        for content_item in content_media.keys():
            sorted(content_media[content_item], key=lambda display: display.displayOrder)
            if not feed_card_media:
                feed_card_media = content_media[content_item][0]
        return MediaModelByCase(caseUuid=case_uuid, feedCard=feed_card_media, contentMedia=content_media)

    @property
    def url(self):
        if self.type == MediaType.IMAGE:
            base_url = os.environ.get('FIGURE1_IMGIX_URL', 'https://figure1-pro-prod.imgix.net/')
            return f"{base_url}{case_image_path}/{self.filename}"
        elif self.type == MediaType.IMAGE_SERIES:
            return f"https://app.figure1.com/image/series?seriesToken={self.legacy_id}"
        elif self.type == MediaType.VIDEO:
            return self.video_url
        else:
            return None

    @staticmethod
    def get_feed_card_media(content_uuid, session) -> Optional['Media']:
        """
        Returns the feed card media associated with the content_uuid, or None if missing.
        """
        return session.query(Media) \
            .filter(Media.content_uuid == content_uuid,
                    Media.is_feed_card_media.is_(True),
                    Media.deleted_at.is_(None)) \
            .one_or_none()

    @staticmethod
    def get_thumbnail_media(content_uuid, session) -> Optional[MediaModel]:
        """
        Returns the feed card media if it exists for the content_uuid, or the first display_order image not.
        """
        media = Media.get_feed_card_media(content_uuid=content_uuid, session=session)
        if media:
            return media.as_object()

        media = session.query(Media) \
            .filter(Media.content_uuid == content_uuid,
                    Media.display_order == 0,
                    Media.deleted_at.is_(None)) \
            .one_or_none()
        if media:
            return media.as_object()

        return None

    def regenerate_video_url(self):
        def remove_video_url():
            self.video_url = None
            self.video_url_generated_at = None

        if not self.filename or self.type != MediaType.VIDEO:
            remove_video_url()
            return

        try:
            v = VimeoClient().get_video(video_id=self.filename)
        except VimeoError as ve:
            logging.error("Failed to get video url: %s", ve)
            remove_video_url()
            raise

        if not v:
            remove_video_url()
        else:
            self.video_url = v.get('link')
            self.height = v.get('height')
            self.width = v.get('width')
            self.video_url_generated_at = datetime.now(tz=timezone.utc)
