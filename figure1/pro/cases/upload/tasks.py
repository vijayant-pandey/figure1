import logging
import os
import uuid
import piexif
import hashlib

from urllib3.util import parse_url
from PIL import Image
from PIL.Image import Image as ImageClass
from google.api_core.exceptions import ServiceUnavailable
from typing import Union
from io import BytesIO

from figure1.common.elasticsearch import add_or_update_case
from figure1.core import FirebaseTaskBase, celery_app
from figure1.common.models.db import MediaType, Case, Media, Content
from figure1.common.helpers import CaseManagement
from figure1.common.types import CaseUploadModel, CaseState
from figure1.common.models.firebase.user_drafts_db import FirebaseUserDraftsDB
from figure1.common.utils import s3_utils, case_image_original_path, case_image_path
from figure1.configuration import app_settings
from figure1.exceptions import S3Error, CaseNotFound


def _rotate_image_from_exif(image):
    if "exif" in image.info:
        exif_dict = piexif.load(image.info["exif"])

        if piexif.ImageIFD.Orientation in exif_dict.get("0th", {}):
            orientation = exif_dict["0th"].pop(piexif.ImageIFD.Orientation)

            if orientation == 2:
                image = image.transpose(Image.FLIP_LEFT_RIGHT)
            elif orientation == 3:
                image = image.rotate(180)
            elif orientation == 4:
                image = image.rotate(180).transpose(Image.FLIP_LEFT_RIGHT)
            elif orientation == 5:
                image = image.rotate(-90, expand=True).transpose(Image.FLIP_LEFT_RIGHT)
            elif orientation == 6:
                image = image.rotate(-90, expand=True)
            elif orientation == 7:
                image = image.rotate(90, expand=True).transpose(Image.FLIP_LEFT_RIGHT)
            elif orientation == 8:
                image = image.rotate(90, expand=True)

    return image


def _process_image(original_image, temp_dir=None, temp_file=None) -> ImageClass:
    image: ImageClass = Image.open(original_image.get('Body'))
    image = _rotate_image_from_exif(image=image)
    if temp_dir and temp_file:
        os.makedirs(temp_dir, exist_ok=True)
        image.save(temp_file, format='png', exif=None)
    return image


@celery_app.task(bind=True,
                 base=FirebaseTaskBase,
                 autoretry_for=(ServiceUnavailable,),
                 name='figure1.frontend.sync_draft_state')
def sync_draft_state(self, user_uid, draft_uid, case_uuid, state):
    for update in FirebaseUserDraftsDB.sync_draft(firebase_db=self.fs_client,
                                                  user_uid=user_uid,
                                                  draft_uid=draft_uid,
                                                  case_uuid=case_uuid,
                                                  state=state):
        doc = self.fs_client.document(update.get('path'))
        self.batch.set(doc, update.get('data'), merge=True)

    self.batch.commit()


@celery_app.task(bind=True,
                 base=FirebaseTaskBase,
                 autoretry_for=(ServiceUnavailable,),
                 name='figure1.frontend.add_image_to_draft')
def add_image_to_draft(self, original_filename, file_hash, temp_dir, user_uid, draft_uid, index):
    filename = file_hash + ".png"
    temp_file = os.path.join(temp_dir, filename)

    original_image = s3_utils.download_from_s3(path=f'{case_image_original_path}/{original_filename}')
    image = _process_image(original_image=original_image, temp_dir=temp_dir, temp_file=temp_file)
    upload_path = f'{case_image_path}/{filename}'
    s3_utils.upload_to_s3(source_path=temp_file, upload_path=upload_path)

    media = _get_new_draft_media(fs_client=self.fs_client,
                                 user_uid=user_uid,
                                 draft_uid=draft_uid,
                                 url=app_settings.figure1_imgix_url + upload_path,
                                 index=index,
                                 filename=filename,
                                 original_filename=original_filename,
                                 width=image.width,
                                 height=image.height)
    for update in FirebaseUserDraftsDB.sync_media(firebase_db=self.fs_client,
                                                  user_uid=user_uid,
                                                  draft_uid=draft_uid,
                                                  media=media):
        doc = self.fs_client.document(update.get('path'))
        self.batch.set(doc, update.get('data'), merge=True)

    self.batch.commit()


@celery_app.task(bind=True,
                 base=FirebaseTaskBase,
                 autoretry_for=(CaseNotFound,),
                 name='figure1.frontend.process_submitted_case')
def process_case_media_on_submission(self, case_uuid, submission_data: CaseUploadModel):
    """

    :param self:
    :param case_uuid:
    :param submission_data:
    :return:
    :exception CaseNotFound: Retry since this likely indicates the transaction hasn't committed
    """
    case = Case.get_case(case_uuid=case_uuid, raise_exception=True)
    for content in case.content:
        self.session.query(Media).filter(Media.content_uuid == content.content_uuid).delete()
        self.session.flush()
        for media in submission_data.media:
            if media.type is not MediaType.IMAGE:
                logging.error("Media type %s is not image", media.type)
                continue
            logging.error("Path is %s", media.url.path)
            logging.error("Decoded to %s", parse_url(media.url))
            image_ = s3_utils.download_from_s3(path=media.url.path.strip('/'))
            processed_image = _process_image(original_image=image_)
            saved_object = BytesIO()
            processed_image.save(saved_object, format='png', exif=None)
            saved_object.seek(0)
            file_hash = hashlib.blake2s(saved_object.read()).hexdigest()
            saved_object.seek(0)
            upload_path = f'{case_image_path}/{file_hash}.png'
            s3_utils.upload_stream_to_s3(upload_path=upload_path, file_stream=saved_object)
            saved_object.close()
            m = Media()
            m.media_uuid = uuid.uuid4()
            m.content_uuid = content.content_uuid
            m.case_uuid = case_uuid
            m.width = processed_image.width
            m.height = processed_image.height
            m.filename = f'{file_hash}.png'
            m.type = MediaType.IMAGE
            m.display_order = media.displayOrder
            m.is_feed_card_media = False
            m.original_filename = media.url.path
            self.session.add(m)
            self.session.flush()
    self.session.commit()
    add_or_update_case(case_uuid, session=self.session)


def _get_new_draft_media(fs_client, user_uid, draft_uid, url, index, filename, original_filename, width, height):
    path = FirebaseUserDraftsDB.get_path(firebase_db=fs_client, user_uid=user_uid, draft_uid=draft_uid)
    doc = fs_client.document(path).get()
    new_media = {
        "url": url,
        "filename": filename,
        "original_filename": original_filename,
        "index": index,
        "type": MediaType.IMAGE.name.lower(),
        "width": width,
        "height": height,
        "upload_completed": True,
    }
    # No existing media
    if not doc.exists:
        new_media['index'] = 0
        return [new_media]

    # Media index not provided
    media = doc.to_dict().get('media', [])
    if index is None:
        new_media['index'] = max(m.get('index') for m in media) + 1 if media else 0
        media.append(new_media)
        return media

    # Media at index not found
    i = next((i for i, m in enumerate(media) if m.get('index') == index), None)
    if i is None:
        media.append(new_media)
        return media

    # Media at index exists
    old_filename = media[i].get('filename')
    old_original_filename = media[i].get('original_filename')
    if old_filename != filename:
        if old_filename:
            s3_utils.delete_from_s3(path=f'{case_image_path}/{old_filename}')
        if old_original_filename:
            s3_utils.delete_from_s3(path=f'{case_image_original_path}/{old_original_filename}')

    media[i] = new_media
    return media


@celery_app.task(bind=True,
                 base=FirebaseTaskBase,
                 autoretry_for=(ServiceUnavailable,),
                 name='figure1.frontend.remove_media')
def remove_media(self, user_uid, draft_uid, index):
    path = FirebaseUserDraftsDB.get_path(firebase_db=self.fs_client,
                                         user_uid=user_uid,
                                         draft_uid=draft_uid)
    doc = self.fs_client.document(path).get()
    if not doc.exists:
        return {'error': 'Could not find firestore document for user_uid and draft_uid'}

    media = doc.to_dict().get('media')
    m = next((m for m in media if m.get('index') == index), None)
    if not m:
        return {'error': 'Could not find media matching index in draft'}

    if m.get('filename'):
        s3_utils.delete_from_s3(path=f'{case_image_path}/{m.get("filename")}')
    if m.get('original_filename'):
        s3_utils.delete_from_s3(path=f'{case_image_original_path}/{m.get("original_filename")}')

    # Update Firestore
    new_media = [_get_media_with_updated_index(m, index) for m in media if m.get('index') != index]
    self.batch.set(self.fs_client.document(path), {'media': new_media}, merge=True)
    self.batch.commit()


def _get_media_with_updated_index(media_item, deleted_index):
    if media_item.get('index') > deleted_index:
        media_item['index'] -= 1
    return media_item


def _get_case_by_media(condition, session):
    case = session.query(Case) \
        .join(Media, Media.case_uuid == Case.case_uuid) \
        .filter_by(**condition).first()

    return case


def _get_content_by_media(condition, session):
    content = session.query(Content) \
        .join(Media, Media.content_uuid == Content.content_uuid) \
        .filter_by(**condition).first()

    return content


def _if_delete_media(condition, session):
    # Don't delete a media item if it is associated with a case(case.state not in [DRAFT, REJECTED])
    case = _get_case_by_media(condition, session)
    if case and case.state not in (CaseState.DRAFT, CaseState.REJECTED):
        return False

    # Don't delete a media item if it is associated with a content
    content = _get_content_by_media(condition, session)
    if content:
        return False

    return True


@celery_app.task(bind=True,
                 base=FirebaseTaskBase,
                 autoretry_for=(ServiceUnavailable,),
                 name='figure1.frontend.delete_draft')
def delete_draft(self, user_uid, draft_uid):
    path = FirebaseUserDraftsDB.get_path(firebase_db=self.fs_client,
                                         user_uid=user_uid,
                                         draft_uid=draft_uid)
    doc = self.fs_client.document(path)
    doc_object = doc.get()
    if not doc_object.exists:
        return {'error': 'Could not find firestore document for user_uid and draft_uid'}
    doc_dict = doc_object.to_dict()

    doc.delete()

    for m in doc_dict.get('media', []):
        filename, original_filename = m.get('filename'), m.get('original_filename')
        try:
            if filename and _if_delete_media({"filename": filename}, self.session):
                s3_utils.delete_from_s3(path=f'{case_image_path}/{filename}')
            if original_filename and _if_delete_media({"original_filename": original_filename}, self.session):
                s3_utils.delete_from_s3(path=f'{case_image_original_path}/{original_filename}')
        except S3Error:
            pass

    case_uuid = doc_dict.get('caseUuid', None)
    if case_uuid:
        CaseManagement.delete_case(case_uuid=case_uuid, session=self.session, destructive=False)
