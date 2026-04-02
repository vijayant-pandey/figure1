import logging
import re
from typing import Tuple

from celery.canvas import Signature
from celery.canvas import group

from figure1.core import managed_session
from figure1.core import translate_client
from figure1.common.helpers import CaseManagement
from figure1.common.elasticsearch import add_or_update_case
from figure1.common.models.db import User
from figure1.common.models.db import CaseSpecialtyV2
from figure1.common.models.db import CaseLabel
from figure1.common.models.db import Media
from figure1.common.models.db import Content
from figure1.common.models.db import Case
from figure1.common.models.db import ContentUpdate
from figure1.common.models.firebase.user_drafts_db import FirebaseUserDraftsDB
from figure1.exceptions import CaseError
from figure1.notifications import log_case_state_changed_task
from figure1.common.slack_client import SlackClient
from figure1.common.slack_client import SlackColour
from figure1.common.slack_client import SlackIcon
from figure1.common.types import CaseClassification
from figure1.common.types import CaseState
from figure1.common.types import CaseType
from figure1.common.types import CaseUploadModel
from figure1.common.types import ContentType
from figure1.common.types import FeedCardType
from figure1.common.types import Locale
from figure1.common.types.case import ContentUpdateType
from figure1.common.types.user_profiles import UserProfileRoute
from figure1.common.utils import generate_presigned_s3_upload_url
from figure1.configuration import app_settings
from .tasks import sync_draft_state
from .tasks import process_case_media_on_submission


_user_not_found_error = {
    'error': f'User was not found',
    'code': 404
}
logger = logging.getLogger(__name__)
translate = translate_client()


@managed_session
def _populate_username_mention(match_obj, session=None):
    username = match_obj.group(1)

    each_user = User.get_user_by_username(username,
                                          session,
                                          raise_exception=False,
                                          include_deleted=False)
    user_profile_link = UserProfileRoute.PROFILE_NOT_FOUND_ROOT.value
    if each_user:
        each_user_uuid = str(each_user.user_uuid)
        user_profile_link = UserProfileRoute.PROFILE_DETAIL_ROOT.value + "/" + each_user_uuid

    return "[@" + username + "](" + user_profile_link + ")"


def refresh_media_upload_url(user_uid, draft_uid):
    presigned_url = generate_presigned_s3_upload_url(upload_path=f"drafts/{user_uid}/{draft_uid}/",
                                                     expires_in=600,
                                                     include_filename=True)
    FirebaseUserDraftsDB.refresh_media_upload_url(user_uid=user_uid,
                                                  draft_uid=draft_uid,
                                                  upload_url=presigned_url)
    return {'media_upload_url': presigned_url,
            "media_download_domain": app_settings.figure1_imgix_url}


@managed_session
def create_new_content_item(case_uuid, session, **kwargs) -> Content:
    return CaseManagement.create_content(case_uuid=case_uuid,
                                         session=session,
                                         **kwargs)


@managed_session
def create_new_case(session, state, language, is_paging_case, request_help,
                    author_uuid, group_uuid, case_type, is_anonymous, case_classification: CaseClassification) -> Case:
    return CaseManagement.create_case(session=session,
                                      state=state,
                                      is_paging_case=is_paging_case,
                                      request_help=request_help,
                                      author_uuid=author_uuid,
                                      language=language,
                                      group_uuid=group_uuid,
                                      case_type=case_type,
                                      is_anonymous=is_anonymous,
                                      case_classification=case_classification)


@managed_session
def update_content_item(content_uuid, session, **kwargs) -> Content:
    return CaseManagement.update_content(content_uuid=content_uuid, session=session, **kwargs)


@managed_session
def update_case(case_uuid, session, **kwargs) -> Case:
    return CaseManagement.update_case(case_uuid=case_uuid,
                                      session=session,
                                      **kwargs)


@managed_session
def update_case_with_single_content(user_uid: str,
                                    draft_uid: str,
                                    data: CaseUploadModel,
                                    state: CaseState,
                                    session=None) -> Tuple[Signature, str]:
    task_group = []
    public_notifications_enabled = data.groupUuid is None and not data.isAnonymous
    user = User.get_user_by_uid(user_uid=user_uid, session=session, raise_exception=True)
    author_uuid = user.user_uuid
    language = None
    if translate:
        if data.caption:
            detected_caption_lang = translate.detect_language(values=data.caption)
            if detected_caption_lang.get("confidence") > 0.95:
                language = Locale.get_from_code(detected_caption_lang.get("language"))

        if data.title:
            detected_title_lang = translate.detect_language(values=data.title)
            if detected_title_lang.get("confidence") > 0.95:
                language = Locale.get_from_code(detected_title_lang.get("language"))

    if not language:
        language = Locale.EN_US.code
    else:
        language = language.code

    if data.caption:
        data.caption = re.sub(r'@\b([A-Za-z0-9_-]*)\b',
                              _populate_username_mention,
                              data.caption)

    if data.caseUuid:
        content_item = Content.get_first_content_item(case_uuid=data.caseUuid, session=session)
        if not content_item:
            raise CaseError(msg='Failed to find content item to update', rc=500, case_uuid=data.caseUuid)
        case = update_case(case_uuid=data.caseUuid,
                           session=session,
                           state=state,
                           is_paging_case=data.paging,
                           language=language,
                           request_help=data.requestHelp,
                           case_type=CaseType.STATIC,
                           is_anonymous=data.isAnonymous)
        session.flush()
        content = update_content_item(content_uuid=content_item.content_uuid,
                                      session=session,
                                      title=data.title,
                                      caption=data.caption,
                                      case_uuid=data.caseUuid)
        session.flush()
    else:
        case = create_new_case(session=session,
                               state=state,
                               language=language,
                               is_paging_case=data.paging,
                               request_help=data.requestHelp,
                               author_uuid=author_uuid,
                               group_uuid=data.groupUuid,
                               case_type=CaseType.STATIC,
                               is_anonymous=data.isAnonymous,
                               case_classification=data.caseClassification,
                               )
        session.flush()

        content = create_new_content_item(case_uuid=case.case_uuid,
                                          session=session,
                                          title=data.title,
                                          caption=data.caption,
                                          is_feed_card=True,
                                          display_order=0,
                                          content_type=ContentType.CONTENT,
                                          feed_card_type=FeedCardType.BASIC,
                                          group_uuid=data.groupUuid,
                                          public_notifications_enabled=public_notifications_enabled)
        session.flush()

    _update_specialties(case_uuid=case.case_uuid,
                        specialty_uuids=data.specialtyUuids,
                        session=session)
    _update_labels(case_uuid=case.case_uuid,
                   label_uuids=data.labelUuids,
                   session=session)
    session.flush()

    ContentUpdate.create(session=session,
                         content_uuid=content.content_uuid,
                         text=data.diagnosis,
                         update_type=ContentUpdateType.DIAGNOSIS,
                         skip_commit=True)

    if data.postProcessMedia is True:
        if state == CaseState.PENDING_APPROVAL:
            task_group.append(process_case_media_on_submission.si(case_uuid=case.case_uuid, submission_data=data))
    else:
        logger.error("Deprecated call - do not use")
        _update_media(content_uuid=content.content_uuid,
                      media=data.media,
                      session=session)

    session.flush()
    task_group.append(sync_draft_state.si(user_uid=user_uid,
                                          draft_uid=draft_uid,
                                          case_uuid=case.case_uuid,
                                          state=state))

    if state == CaseState.PENDING_APPROVAL:
        if language != Locale.EN_US:
            CaseManagement.translate_case(session=session, case_uuid=case.case_uuid, source_language=language)

        add_or_update_case(case_uuid=case.case_uuid, session=session)
        task_group.append(log_case_state_changed_task.si(case_uuid=case.case_uuid))
        SlackClient().send_message(message="A new case has been submitted for moderation",
                                   colour=SlackColour.GREEN,
                                   icon=SlackIcon.ROCKET,
                                   channel=app_settings.slack_channel_moderation_notifications,
                                   entity=user)
    return group(task_group), str(case.case_uuid)


def _update_specialties(case_uuid, specialty_uuids, session):
    existing_specialties = session.query(CaseSpecialtyV2) \
        .filter(CaseSpecialtyV2.case_uuid == case_uuid) \
        .all()
    for case_specialty in existing_specialties:
        if case_specialty.specialty_uuid not in specialty_uuids:
            case_specialty.mark_deleted()
    for specialty_uuid in specialty_uuids:
        CaseSpecialtyV2.create(case_uuid=case_uuid,
                               specialty_uuid=specialty_uuid,
                               session=session)


def _update_labels(case_uuid, label_uuids, session):
    existing_labels = session.query(CaseLabel) \
        .filter(CaseLabel.case_uuid == case_uuid) \
        .all()
    for case_label in existing_labels:
        if case_label.label_uuid not in label_uuids:
            case_label.mark_deleted()
    for label_uuid in label_uuids:
        CaseLabel.create(case_uuid=case_uuid,
                         label_uuid=label_uuid,
                         skip_commit=True,
                         session=session)


def _update_media(content_uuid, media, session):
    existing_media = session.query(Media) \
        .filter(Media.content_uuid == content_uuid)
    for m in existing_media:
        media_filenames = [x.filename for x in media]
        if m.filename not in media_filenames:
            m.mark_deleted()
    for m in media:
        Media.create(content_uuid=content_uuid,
                     media_type=m.type,
                     filename=m.filename,
                     original_filename=m.originalFilename,
                     display_order=m.displayOrder,
                     width=m.width,
                     height=m.height,
                     session=session,
                     skip_commit=True)
