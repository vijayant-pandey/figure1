import logging
import uuid

from figure1.admin.moderation.tagging import fetch_mesh_tags_task
from figure1.admin.moderation.tagging.domain import set_mesh_terms
from figure1.common.elasticsearch import add_or_update_case
from figure1.common.elasticsearch import delete_case as delete_es_case
from figure1.common.elasticsearch import update_case_fields
from figure1.common.elasticsearch import update_moderation_case_detail
from figure1.common.firebase import do_firebase_sync
from figure1.common.helpers import CaseManagement
from figure1.common.models.db import Case
from figure1.common.models.db import CaseEdit
from figure1.common.models.db import CaseLabel
from figure1.common.models.db import CaseMediaEdit
from figure1.common.models.db import CaseNote
from figure1.common.models.db import Content
from figure1.common.models.db import ContentExtension
from figure1.common.models.db import ContentUpdate
from figure1.common.models.db import Label
from figure1.common.models.db import Media
from figure1.common.models.db import SponsoredContent
from figure1.common.models.db import User
from figure1.common.types import CaseRejectionReason
from figure1.common.types import CaseState
from figure1.common.types import ModerationCaseEdit
from figure1.common.types.case import ContentUpdateType
from figure1.common.types.endpoints import PartnerCaseUpdate
from figure1.common.utils import case_image_path
from figure1.common.utils import s3_utils
from figure1.configuration import app_settings
from figure1.core import managed_session
from figure1.events import CaseEvents
from figure1.exceptions import CaseError
from figure1.exceptions import CaseStateError
from .case_transition_handler import propagate_case_state_update
from .tasks import sync_case_rejected_state

logger = logging.getLogger('figure1.moderation.case_edits')


def handle_elasticsearch_moderation_update(session, case_uuid):
    update_moderation_case_detail(case_uuid=case_uuid, session=session)


def _set_case_state(session, case_uuid, state: CaseState):
    case = Case()
    case.case_uuid = case_uuid
    case.state = state
    session.merge(case)
    session.commit()
    propagate_case_state_update(case_uuid=case_uuid)
    if state == CaseState.APPROVED:
        CaseEvents.CASE_APPROVED(case_uuid=case_uuid, session=session)


def _validate(moderator_uid, case_uuid, session, valid_states=None):
    moderator_uuid = User.get_user_uuid_by_uid(user_uid=moderator_uid, session=session, raise_exception=True)
    case = Case.get_case(case_uuid=case_uuid, raise_exception=True, session=session)

    if valid_states and case.state not in valid_states:
        raise CaseStateError(msg=f'State ({case.state.name}) is not valid for this action')

    return {
        'moderator_uuid': moderator_uuid,
        'case': case
    }


@managed_session
def set_case_state(case_uuid, state, session=None):
    try:
        set_state = CaseState.__getitem__(state.upper())
    except KeyError:
        return {'error': f'Failed to create CaseState instance with {state}'}

    return _set_case_state(case_uuid=case_uuid, state=set_state, session=session)


@managed_session
def approve_case(case_uuid, moderator_uid, session=None):
    """
    :param case_uuid: UUID for the case to approve
    :param moderator_uid: UID for the moderator initiating the approval
    """

    res = _validate(moderator_uid=moderator_uid,
                    case_uuid=case_uuid,
                    session=session,
                    valid_states=[CaseState.PENDING_APPROVAL,
                                  CaseState.FLAGGED,
                                  CaseState.EDIT_SUGGESTED,
                                  CaseState.REPORTED])
    if 'error' in res:
        return res
    case = res.get('case')
    moderator_uuid = event_author_uuid = res.get('moderator_uuid')

    case.event_author_uuid = event_author_uuid
    if app_settings.mesh_api_enabled is False:
        case.state = CaseState.PENDING_TAGGING
        set_mesh_terms(mesh_terms=[], case_uuid=case_uuid, session=session)
    else:
        case.state = CaseState.PENDING_NLP
    session.add(case)
    session.commit()

    task = propagate_case_state_update(
        case_uuid=case_uuid,
        moderator_uid=moderator_uid,
        return_task=True)

    if app_settings.mesh_api_enabled is False:
        logger.error("Mesh API disabled, skipping for case %s", case_uuid)
    else:
        task.link(fetch_mesh_tags_task.si(case_uuid=case_uuid))
    task.apply_async()
    return {'success': f"Case sent to mesh tagging"}


@managed_session
def reject_case(case_uuid, moderator_uid, reason, session=None):
    res = _validate(moderator_uid=moderator_uid,
                    case_uuid=case_uuid,
                    session=session)
    if 'error' in res:
        return res
    case = res.get('case')
    moderator_uuid = event_author_uuid = res.get('moderator_uuid')

    suppress_user_notification = reason == CaseRejectionReason.DELETE_NO_EMAIL
    case_state = CaseState.REJECTED if reason.allow_revision else CaseState.DELETED

    case.event_author_uuid = event_author_uuid
    case.rejection_reason = reason
    if reason.allow_revision:
        case.state = case_state
        sync_case_rejected_state.apply(kwargs=dict(user_uid=case.authors[0].user_uid, case=case))
    else:
        CaseManagement.delete_case(case_uuid=case_uuid, session=session, destructive=True)
        delete_es_case(case_uuid=case_uuid)

    session.commit()
    propagate_case_state_update(
        case_uuid=case_uuid,
        moderator_uid=moderator_uid,
        suppress_user_notification=suppress_user_notification)
    do_firebase_sync.delay(uuid=case_uuid, firebasemodel="CaseDetailV2")

    # todo: email user
    return {'success': f"Case rejected"}


@managed_session
def flag_case(case_uuid, moderator_uid, session=None):
    res = _validate(moderator_uid=moderator_uid,
                    case_uuid=case_uuid,
                    session=session)
    if 'error' in res:
        return res
    case = res.get('case')
    event_author_uuid = res.get('moderator_uuid')

    case.event_author_uuid = event_author_uuid
    case.state = CaseState.FLAGGED

    propagate_case_state_update(case_uuid=case_uuid, moderator_uid=moderator_uid)

    return {'success': f"Case flagged"}


@managed_session
def remove_paging_from_case(case_uuid, moderator_uid, session=None):
    res = _validate(moderator_uid=moderator_uid,
                    case_uuid=case_uuid,
                    session=session)
    case = res.get('case')
    event_author_uuid = res.get('moderator_uuid')
    case.event_author_uuid = event_author_uuid
    if case.is_paging_case is False:
        raise CaseError(msg="error, case is not a paging case", return_code=422)
    CaseManagement.update_case(case_uuid=case_uuid,
                               session=session,
                               is_paging_case=False)
    session.flush()
    add_or_update_case(case_uuid=case_uuid, session=session)
    return {'success': 'paging is removed from case'}


@managed_session
def add_case_note(case_uuid, moderator_uid, text, session=None):
    res = _validate(moderator_uid=moderator_uid,
                    case_uuid=case_uuid,
                    session=session)
    if 'error' in res:
        return res
    moderator_uuid = res.get('moderator_uuid')
    case = res.get('case')

    CaseNote.create(case_uuid=case.case_uuid, moderator_uuid=moderator_uuid, text=text, session=session)

    handle_elasticsearch_moderation_update(session=session, case_uuid=str(case.case_uuid))

    return {'success': f"Case note added"}


@managed_session
def add_case_edit(case_edit: ModerationCaseEdit, session=None):

    res = _validate(moderator_uid=case_edit.moderatorUid,
                    case_uuid=case_edit.caseUuid,
                    session=session)

    moderator_uuid = res.get('moderator_uuid')
    case: Case = res.get('case')
    if case_edit.contentUuid:
        content = Content.get_content(content_uuid=case_edit.contentUuid, session=session)
    else:
        content = Content.get_first_content_item(case_uuid=case_edit.caseUuid, session=session)

    ce = CaseEdit.create(content_uuid=content.content_uuid,
                         moderator_uuid=moderator_uuid,
                         caption=case_edit.caption,
                         title=case_edit.title,
                         language=case_edit.language,
                         diagnosis=case_edit.diagnosis,
                         session=session)
    session.flush()
    if case_edit.caseClassification is not None:
        case.case_classification = case_edit.caseClassification
        session.add(case)
        session.flush()
        update_case_fields(case_uuid=case_edit.caseUuid,
                           case_field_name='caseClassification',
                           case_field_value=case_edit.caseClassification.value)
    if case_edit.suggestedEdit is False:
        approve_reject_case_edit(case_uuid=case_edit.caseUuid,
                                 edit_uuid=ce.edit_uuid,
                                 moderator_uid=case_edit.moderatorUid,
                                 action='approve',
                                 session=session)
    else:
        handle_elasticsearch_moderation_update(session=session, case_uuid=case_edit.caseUuid)

    return {'success': f"Case edit added or updated"}


@managed_session
def add_case_media_edit(case_uuid, media_uuid, moderator_uid, file, temp_dir, suggested_edit, session=None):
    res = _validate(moderator_uid=moderator_uid,
                    case_uuid=case_uuid,
                    session=session)
    if 'error' in res:
        return res
    moderator_uuid = res.get('moderator_uuid')
    case = res.get('case')

    res = s3_utils.upload_image_to_s3(file=file, upload_dir=case_image_path, temp_dir=temp_dir)
    if 'error' in res:
        logger.error(f"Failed to upload edited media: {res.get('error')}")
        return res

    cme = CaseMediaEdit.create(media_uuid=media_uuid,
                               moderator_uuid=moderator_uuid,
                               filename=res.get('filename'),
                               session=session)

    if suggested_edit is False:
        logger.info("Not a suggested edit, approving edit %s", cme.as_dict())
        approve_reject_case_media_edit(case_uuid=case_uuid,
                                       media_edit_uuid=cme.media_edit_uuid,
                                       moderator_uid=moderator_uid,
                                       action="approve",
                                       session=session)
    else:
        logger.info("Suggested edit - waiting for approval")
        handle_elasticsearch_moderation_update(session=session, case_uuid=str(case.case_uuid))

    return {'success': f"Case media edit added"}


@managed_session
def approve_reject_case_edit(case_uuid, edit_uuid, moderator_uid, action, session=None):
    """
    Rejecting a case edit sends it back to the moderator, Approving a case edit copies the changes into the content
    entry. This is done by state change.
    Only one edit is allowed per content uuid to prevent unexpected overwrites

    :return:
    """
    res = _validate(moderator_uid=moderator_uid,
                    case_uuid=case_uuid,
                    valid_states=[],
                    session=session)
    if 'error' in res:
        return res
    case = res.get('case')
    moderator_uuid = res.get('moderator_uuid')

    res = session.query(CaseEdit, Content) \
        .filter(CaseEdit.edit_uuid == edit_uuid) \
        .join(Content, Content.content_uuid == CaseEdit.content_uuid) \
        .one_or_none()

    if not res:
        return {'error': f'Could not find edit_uuid {edit_uuid}'}

    edit = res[0]
    content = res[1]

    if action == 'approve':
        if edit.title:
            content.title = str(edit.title)
        if edit.caption:
            content.caption = str(edit.caption)
        if edit.language:
            case.language = edit.language
        if edit.diagnosis is not None:
            ContentUpdate.create(session=session,
                                 content_uuid=content.content_uuid,
                                 text=edit.diagnosis,
                                 update_type=ContentUpdateType.DIAGNOSIS)
        CaseEdit.apply_edit(edit_uuid=edit_uuid, moderator_uuid=moderator_uuid, session=session)
    else:
        CaseEdit.reject_edit(edit_uuid=edit_uuid, moderator_uuid=moderator_uuid, session=session)

    handle_elasticsearch_moderation_update(session=session, case_uuid=case_uuid)

    return {'success': f"Done case edit {action}"}


@managed_session
def approve_reject_case_media_edit(case_uuid,
                                   media_edit_uuid,
                                   moderator_uid,
                                   action,
                                   session=None):
    res = _validate(moderator_uid=moderator_uid,
                    case_uuid=case_uuid,
                    session=session)
    if 'error' in res:
        return res
    moderator_uuid = res.get('moderator_uuid')
    res = session.query(CaseMediaEdit, Media) \
        .filter(CaseMediaEdit.media_edit_uuid == media_edit_uuid) \
        .join(Media, Media.media_uuid == CaseMediaEdit.media_uuid) \
        .one_or_none()
    if not res:
        logger.error("No media edit %s found", media_edit_uuid)
        return {'error': f'Could not find media_edit_uuid {media_edit_uuid}'}

    if action == 'approve':
        logger.info("Approving edit %s", media_edit_uuid)
        cme = CaseMediaEdit.apply_edit(media_edit_uuid=media_edit_uuid,
                                       moderator_uuid=moderator_uuid,
                                       session=session)
        logger.info("Writing media filename %s to uuid %s", cme.filename, cme.media_uuid)
        m = Media()
        m.media_uuid = cme.media_uuid
        m.filename = cme.filename
        new_media = session.merge(m)
        logger.info("New media entry is %s", new_media.as_dict())
    else:
        CaseMediaEdit.reject_edit(media_edit_uuid=media_edit_uuid, moderator_uuid=moderator_uuid, session=session)

    handle_elasticsearch_moderation_update(session=session, case_uuid=case_uuid)

    return {'success': f"Done case media edit {action}"}


@managed_session
def set_case_labels(case_uuid, moderator_uid, label_uuids, session=None):
    _validate(moderator_uid=moderator_uid,
              case_uuid=case_uuid,
              session=session)

    existing = session.query(CaseLabel) \
        .filter(CaseLabel.case_uuid == case_uuid) \
        .all()

    for cl in existing:
        if cl.label_uuid not in label_uuids:
            cl.mark_deleted()

    for uuid in label_uuids:
        if uuid not in existing:
            CaseLabel.create(case_uuid=case_uuid, label_uuid=uuid, session=session, skip_commit=True)

    labels = []
    for uuid in label_uuids:
        if uuid not in existing:
            CaseLabel.create(case_uuid=case_uuid, label_uuid=uuid, session=session, skip_commit=True)
        lbl = session.query(Label).get(uuid)
        if lbl:
            labels.append(lbl.kind)

    update_case_fields(case_uuid=case_uuid, case_field_name="labels", case_field_value=labels)
    return {'success': "Successfully updated case labels"}


@managed_session
def add_partner_case_settings(session, moderator_uid, case_uuid, data):
    res = _validate(moderator_uid=moderator_uid,
                    case_uuid=case_uuid,
                    session=session)

    case = res.get('case')
    case_update = PartnerCaseUpdate.parse_obj(data)
    for content in case.content:
        if content.sponsored_content:
            sp = content.sponsored_content
        else:
            sp = SponsoredContent()
            sp.sponsored_content_uuid = uuid.uuid4()

        if content.extension:
            ce = content.extension
        else:
            ce = ContentExtension()
            ce.content_extension_uuid = uuid.uuid4()

        if case_update.disclosureText:
            if case_update.disclosureText == 'delete':
                sp.disclosure_text = None
            else:
                sp.disclosure_text = case_update.disclosureText
        if case_update.sponsoredText:
            if case_update.sponsoredText == 'delete':
                sp.sponsored_text = None
            else:
                sp.sponsored_text = case_update.sponsoredText
        if case_update.externalLinkUrl:
            if case_update.externalLinkText:
                if case_update.externalLinkText == 'delete':
                    ce.external_link_text = None
                    ce.external_link_url = None
                else:
                    ce.external_link_url = case_update.externalLinkUrl
                    ce.external_link_text = case_update.externalLinkText
            else:
                ce.external_link_url = case_update.externalLinkUrl
                ce.external_link_text = case_update.externalLinkUrl
        content.sponsored_content = sp
        content.extension = ce
        session.add(content)
        session.flush()
    session.commit()
    add_or_update_case(case_uuid=case_uuid, session=session)
