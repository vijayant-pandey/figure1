import logging
from datetime import datetime
from datetime import timezone

import boto3
import botocore.exceptions
from celery import chain
from sqlalchemy import or_
from sqlalchemy.engine import Row
from sqlalchemy.orm import Session

from figure1.admin.moderation.cases import propagate_case_state_update
from figure1.common.activities.user_profile_activities import update_profile_cases_task
from figure1.common.elasticsearch import update_case_reaction
from figure1.common.firebase import do_firebase_sync
from figure1.common.helpers import CaseManagement
from figure1.common.models.db import Case
from figure1.common.models.db import CaseLabel
from figure1.common.models.db import CaseProgress
from figure1.common.models.db import CaseReaction
from figure1.common.models.db import CaseReport
from figure1.common.models.db import Content
from figure1.common.models.db import ContentUpdate
from figure1.common.models.db import Label
from figure1.common.models.db import Media
from figure1.common.models.db import User
from figure1.common.models.db import UserSavedCase
from figure1.common.models.db.c_content_update_model import ContentUpdateTranslations
from figure1.common.models.firebase import CaseProgressData
from figure1.common.models.firebase import CaseProgressStateModel
from figure1.common.models.firebase import FirebaseCollectionManager
from figure1.common.models.firebase import FirestoreCaseProgressState
from figure1.common.types import CMEContentPositionModel
from figure1.common.types import CMETypes
from figure1.common.types import CaseState
from figure1.common.types import CaseType
from figure1.common.types import FirebaseAction
from figure1.common.types import Locale
from figure1.common.types import Reaction
from figure1.common.types.case import ContentUpdateType
from figure1.common.utils.date_utils import utc_now
from figure1.configuration import app_settings
from figure1.core import TaskBase
from figure1.core import celery_app
from figure1.core import managed_session
from figure1.core import translate_client
from figure1.events import AggregationEvents
from figure1.exceptions import S3Error
from figure1.exceptions.case import CaseTranslationError
from figure1.exceptions.user import InsufficientPermissions
from figure1.notifications import log_case_update_task
from figure1.notifications import log_reaction_and_notify_user_task
from figure1.notifications import send_event_cme_completed_to_user_task
from figure1.pro.cme import upload_cme_certificate
from figure1.tools.cases import translate_case_content

fb = FirebaseCollectionManager()
logger = logging.getLogger(__name__)


def _update_case_detail(case_uuid, return_task=False):
    sync_case = chain(
        do_firebase_sync.si(uuid=case_uuid, firebasemodel="CommentV2", merge=False),
        do_firebase_sync.si(uuid=case_uuid, firebasemodel="CaseDetailV2", merge=False)
    )
    if return_task:
        return sync_case
    sync_case.apply_async()


def _update_case_reaction_counts(case_uuid, reactions_by_user, update_doc=None):
    """
    Updates the number of reactions in the case detail view in firestore.
    :param case_uuid:
    :param update_doc: the reactions map relative to the top level case document
    :return: None
    """
    fb.set_fs_client(documents=[case_uuid], collections=['casesDBv2'])
    update_case_reaction(case_uuid=case_uuid, reaction=reactions_by_user)
    if update_doc:
        fb.set(update_doc, merge=True)


def _translate_content_update_given_languages(text, update_uuid, languages, session):
    translate = translate_client()

    if not translate:
        logger.error("Translate api is disabled, can not translate update %s ", update_uuid)
        return

    for each_language in languages:
        each_language_code = Locale.get_from_code(each_language).language_code
        translated_content_update = translate.translate(target_language=each_language_code,
                                                        values=text)['translatedText']
        ContentUpdateTranslations.create(
            update_uuid=update_uuid,
            text=translated_content_update,
            language=each_language,
            session=session,
        )


def check_aws_images(s3_client, image, path):
    s3_bucket = app_settings.s3_upload_bucket
    if not s3_bucket:
        raise S3Error(msg='No bucket defined')

    try:
        s3_client.head_object(Bucket=s3_bucket, Key=f'cases/{path}/{image}', )
        return True
    except botocore.exceptions.ClientError:
        return False


@managed_session
def check_missing_images(session=None, case_uuid=None, new_cases=False, all_cases=True):
    """
    Checks image storage to ensure the image exists. If no argument is passed, all cases are checked. If new_cases
    is set, then only cases that have not been checked before are passed. If a case_uuid is passed, then the content
    items associated with that case are checked.

    For the new_cases and all_cases parameters, every 1000 cases are committed.

    :param case_uuid: Pass in a case_uuid to check all content items associated with this case. For this option,
    the state of the case is not checked.

    :param new_cases: If this parameter is set, then check all cases that have not been checked. This flag filters cases
    for the APPROVED state, no other states are checked.

    :param all_cases: If this parameter is set, then all cases are checked, they are ordered by the oldest last checked
    date to the newest. This flag also filters by case state APPROVED.

    :param session: This is the session being used, if it isn't passed, then the managed session wrapper is used.

    """
    images_path = "images"
    images_original_path = "images-original"
    s3_client = boto3.client('s3')

    def _check_row(row):
        if isinstance(row, Row):
            row = row[0]
        row.checked_at = utc_now(timezone=True)
        if row.filename:
            row.filename_exists = check_aws_images(s3_client=s3_client, image=row.filename, path=images_path)

        if row.original_filename:
            row.original_filename_exists = check_aws_images(s3_client=s3_client, image=row.original_filename,
                                                            path=images_original_path)
        return row

    case_query = session.query(Media).join(Content, Content.content_uuid == Media.content_uuid) \
        .join(Case, Case.case_uuid == Content.case_uuid)

    if case_uuid:
        response = []
        logger.info("Checking case uuid %s ", case_uuid)
        filename_media_content = case_query.filter(Case.case_uuid == case_uuid,
                                                   or_(Media.filename.isnot(None),
                                                       Media.original_filename.isnot(None)))

        if filename_media_content.all():
            for row in filename_media_content:
                updated_row = _check_row(row)
                response.append(updated_row.as_dict())
                session.add(updated_row)
        return response

    elif new_cases:
        logger.info("Checking all unchecked cases")
        new_cases_query = case_query.filter(Case.state == 'APPROVED',
                                            Media.checked_at.is_(None),
                                            Media.filename_exists.is_(None),
                                            or_(Media.filename.isnot(None),
                                                Media.original_filename.isnot(None))) \
            .yield_per(1000)
        for part in session.execute(new_cases_query).partitions(size=1000):
            logger.info("Starting on partition")
            for row in part:
                updated_row = _check_row(row)
                session.add(updated_row)
            logger.info("Finished partition")
            session.commit()
            logger.info("Checked 1000")

    elif all_cases:
        logger.info("Checking all cases")
        all_cases_query = case_query.filter(Case.state == 'APPROVED',
                                            or_(Media.filename.isnot(None), Media.original_filename.isnot(None))) \
            .order_by(Media.checked_at.asc()).yield_per(1000)

        for part in session.execute(all_cases_query).partitions(size=1000):
            for row in part:
                updated_row = _check_row(row)
                session.add(updated_row)
            session.commit()
            logger.info("Checked 1000")
    else:
        logger.error("No directive passed, no cases will be checked")


def check_missing_media(case_uuid=None, new_cases=False, all_cases=False):
    return check_missing_media_task.si(case_uuid=case_uuid, new_cases=new_cases, all_cases=all_cases)


@celery_app.task(bind=True,
                 base=TaskBase,
                 name='figure1.backend.check_missing_media')
def check_missing_media_task(self, case_uuid=None, new_cases=False, all_cases=False):
    return check_missing_images(session=self.session, case_uuid=case_uuid, new_cases=new_cases, all_cases=all_cases)


def case_author_profile(case_uuid, authors_list, update_doc=None):
    """
    updates the number of reactions in the author's profile in firestore.
    :param case_uuid:
    :param authors_list:
    :param update_doc: the reactions map relative to the top level case document
    :return: None
    """
    for author in authors_list:
        fb.set_fs_client(documents=[author, case_uuid],
                         collections=['usersProfileDB', 'activity'])
        fb.set(update_doc, merge=True)


def _update_case_user_activity(case_uuid, user_uuid, update_doc=None, delete_field=None):
    """
    Each case contains a userActivity subcollection which contains a list of user_uuids and 1 or 2 keys in the document.
    One of the keys is 'saved' and should be True if set - this indicates the user_uuid has saved this case. The other
    key is 'reactions' which is present if the user has reacted to this case. It is an array and will have one element
    containing the name of the reaction if set.

    :param case_uuid:
    :param user_uuid:
    :param update_doc:
    :return:
    """
    fb.set_fs_client(documents=[case_uuid, user_uuid], collections=['casesDBv2', 'userActions'])
    u = fb.get().to_dict()
    if u and delete_field:
        fb.delete(field_name=delete_field)
    if update_doc:
        fb.set(update_doc)


def get_case(case_uuid, return_task=False):
    task = _update_case_detail(case_uuid, return_task=return_task)
    if return_task:
        return {'success': 'Case detail update request sent', 'task': task}
    return {'success': 'Case detail update request sent'}


@managed_session
def save_case(user_uid, case_uuid, save_state, session=None):
    """
    There are two updates to firestore - the first saves the feed item into the users saved cases collection, the
    second updates the userActions collection on the case document in CaseDBv2.
    The update to the user's saved cases collection is asynchronous, however the update to the case is synchronous.

    An entry is created in the UserSavedCase table, if the flush fails, then we do not try to sync to firestore and
    the exception is re-raised. The same happens for the deleting a saved case.
    The sync does not depend on the UserSavedCase table being up to date to work, it simply syncs the case as it exists
     in elasticsearch.

    :param user_uid:
    :param case_uuid:
    :param save_state:
    :param session:
    :return:
    """

    user = User.get_user_by_uid(user_uid=user_uid, session=session, raise_exception=True)
    case = Case.get_case(case_uuid=case_uuid, raise_exception=True)
    user_uuid, group_uuid = user.user_uuid, case.group_uuid

    if group_uuid and group_uuid not in (each.group_uuid for each in user.group_member):
        raise InsufficientPermissions(msg='Only case group members can save/unsave a case.')

    if save_state:
        sc = UserSavedCase.create(case_uuid=case_uuid, user_uuid=user_uuid, session=session)
        task = do_firebase_sync.si(firebasemodel='FirebaseUserSavedCasesDB',
                                   uuid=(sc.user_uuid, sc.case_uuid),
                                   action=FirebaseAction.SET)
        task.link(AggregationEvents.ON_CASE_SAVE_TASK.value.si(user_uuid=user_uuid))

        _update_case_user_activity(case_uuid=case_uuid, user_uuid=str(user_uuid), update_doc={'saved': True})
        return {'success': f"Case saved", "task": task}

    else:
        sc = UserSavedCase.delete(case_uuid=case_uuid, user_uuid=user_uuid, session=session)
        if not sc:
            return {"success": "No case found to delete", "task": None}
        else:
            _update_case_user_activity(case_uuid=case_uuid, user_uuid=str(user_uuid), delete_field='saved')
            task = do_firebase_sync.si(firebasemodel='FirebaseUserSavedCasesDB',
                                       uuid=(sc.user_uuid, sc.case_uuid),
                                       action=FirebaseAction.DELETE)

        return {'success': f"Case unsaved", "task": task}


@managed_session
def report_case(user_uid, case_uuid, report_text, session=None):
    user_uuid = User.get_user_uuid_by_uid(user_uid=user_uid, session=session, raise_exception=True)
    case = Case.get_case(case_uuid=case_uuid, raise_exception=True)

    case.state = CaseState.REPORTED
    CaseReport.create(case_uuid=case_uuid, user_uuid=user_uuid, text=report_text, session=session)

    task = propagate_case_state_update(case_uuid=case_uuid,
                                       suppress_user_notification=True,
                                       return_task=True)
    session.add(case)

    return {'success': f"Case reported", "task": task}


@managed_session
def submit_case_reaction(user_uid, case_uuid, reaction: Reaction, value: bool, session):
    """
    Takes a reaction to a case and adds it in the CaseReaction table and updates it in firestore on the
    case table.
    The update is for both all_reaction counts and for userActions which tracks case activity by user.

    If there is a database problem, DatabaseError is caught and re-raised, firestore is not updated
    :param user_uid:
    :param case_uuid:
    :param reaction:
    :param value:
    :param session:
    :return:
    """

    user = User.get_user_by_uid(user_uid=user_uid, session=session, raise_exception=True)
    case = Case.get_case(case_uuid=case_uuid, raise_exception=True)
    user_uuid, group_uuid = user.user_uuid, case.group_uuid

    if group_uuid and group_uuid not in (each.group_uuid for each in user.group_member):
        raise InsufficientPermissions(msg='Only the case group members can react to a case.')

    if value is True:
        CaseReaction.set_reaction(case_uuid=case_uuid,
                                  user_uuid=user_uuid,
                                  reaction=reaction,
                                  session=session)
        _update_case_user_activity(case_uuid=case_uuid, user_uuid=str(user_uuid),
                                   update_doc={'reactions': [reaction.value]}, delete_field='reactions')

    else:
        CaseReaction.unset_reaction(case_uuid=case_uuid, user_uuid=user_uuid, session=session)
        _update_case_user_activity(case_uuid=case_uuid, user_uuid=str(user_uuid), delete_field='reactions')

    firestore_reaction_count = {
        'allReactions': CaseReaction.get_reaction_counts(case_uuid=case_uuid, session=session)
    }

    cr_total = CaseReaction.get_case_reactions(case_uuid=case_uuid, session=session)
    _update_case_reaction_counts(case_uuid=case_uuid, update_doc=firestore_reaction_count, reactions_by_user=cr_total)
    authors_list = [str(a.user_uuid) for a in case.authors]
    case_author_profile(case_uuid=case_uuid, authors_list=authors_list, update_doc=firestore_reaction_count)
    task = AggregationEvents.ON_NEW_REACTION_TASK.value.si(user_uuid=user_uuid)
    task.link(log_reaction_and_notify_user_task.si(user_uuid=str(user_uuid), case_uuid=case_uuid))
    task.link(update_profile_cases_task.si(case_uuid=case_uuid))
    return {'success': f"Case reaction added", "task": task}


@managed_session
def submit_case_update(user_uid, case_uuid, text, diagnosis_text,
                       content_uuid=None, linked_update_uuid=None, resolved=None, session=None):
    logger = logging.getLogger(__name__)

    user_uuid = User.get_user_uuid_by_uid(user_uid=user_uid, session=session, raise_exception=True)
    case = Case.get_case(case_uuid=case_uuid, raise_exception=True)

    # if not any(a.user_uuid == user_uuid for a in case.authors):
    #     return {
    #         'error': 'Invalid user_uid.  Only the case author can submit an update',
    #         'code': 401
    #     }

    current_label = None
    is_diagnosis = False
    if content_uuid:
        content = Content.get_content(content_uuid=content_uuid)
    else:
        content = case.content[0]
    previous_label = session.query(Label.kind).join(CaseLabel, CaseLabel.label_uuid == Label.label_uuid).filter(
        CaseLabel.case_uuid == case_uuid, CaseLabel.deleted_at.is_(None),
        or_(Label.kind == 'unresolved', Label.kind == 'resolved')).one_or_none()

    translated_languages = ContentUpdateTranslations.get_translated_languages_by_content_uuid(
        content_uuid=content.content_uuid, session=session
    )

    if text:
        update = ContentUpdate.create(session=session,
                                      content_uuid=content.content_uuid,
                                      text=text,
                                      update_type=ContentUpdateType.UPDATE,
                                      linked_update_uuid=linked_update_uuid,
                                      skip_commit=True)
        _translate_content_update_given_languages(update.text,
                                                  update.update_uuid,
                                                  translated_languages,
                                                  session=session)
    if diagnosis_text:
        diagnosis = ContentUpdate.create(session=session,
                                         content_uuid=content.content_uuid,
                                         text=diagnosis_text,
                                         update_type=ContentUpdateType.DIAGNOSIS,
                                         linked_update_uuid=linked_update_uuid,
                                         skip_commit=True)
        is_diagnosis = True
        _translate_content_update_given_languages(diagnosis.text,
                                                  diagnosis.update_uuid,
                                                  translated_languages,
                                                  session=session)

    if resolved is not None:
        resolved_uuid = Label.get_resolved(session=session).label_uuid
        unresolved_uuid = Label.get_unresolved(session=session).label_uuid
        if resolved:
            CaseLabel.delete(case_uuid=case_uuid, label_uuid=unresolved_uuid, session=session, skip_commit=True)
            CaseLabel.create(case_uuid=case_uuid, label_uuid=resolved_uuid, session=session, skip_commit=True)
            current_label = "resolved"
        else:
            CaseLabel.delete(case_uuid=case_uuid, label_uuid=resolved_uuid, session=session, skip_commit=True)
            CaseLabel.create(case_uuid=case_uuid, label_uuid=unresolved_uuid, session=session, skip_commit=True)
            current_label = "unresolved"

    task = _update_case_detail(case_uuid=case_uuid, return_task=True)
    if previous_label:
        task.link(log_case_update_task.si(case_uuid=case_uuid,
                                          previous_label=previous_label.kind,
                                          current_label=current_label,
                                          author_uuid=str(user_uuid),
                                          is_diagnosis=is_diagnosis))
    else:
        task.link(log_case_update_task.si(case_uuid=case_uuid,
                                          previous_label=None,
                                          current_label=current_label,
                                          author_uuid=str(user_uuid),
                                          is_diagnosis=is_diagnosis))
    return {
        'success': f"Case update submitted",
        'task': task,
        'content_uuid': str(content.content_uuid)  # Include for mention processing
    }


@managed_session
def delete_case(case_uuid, user_uid=None, moderator_uid=None, session=None):
    case = Case.get_case(case_uuid=case_uuid, raise_exception=True)
    if moderator_uid:
        acting_uuid = User.get_user_uuid_by_uid(user_uid=user_uid, session=session, raise_exception=True)
    elif user_uid:
        acting_uuid = User.get_user_uuid_by_uid(user_uid=user_uid, session=session, raise_exception=True)
        if not any(a.user_uuid == acting_uuid for a in case.authors):
            return {
                'error': 'Invalid user_uid.  Only the case author can delete a case',
                'code': 401
            }
    else:
        return {'error': 'A user uid or moderator uid is required'}

    case.event_author_uuid = acting_uuid
    CaseManagement.delete_case(case_uuid=case_uuid, session=session, destructive=False)

    session.commit()
    task = do_firebase_sync.si(uuid=case_uuid, firebasemodel="CaseDetailV2")

    return {'success': f"Case deleted", "task": task}


@managed_session
def update_content_position(model: CMEContentPositionModel, session: Session = None):
    task = None
    user_uuid = User.get_user_uuid_by_uid(user_uid=model.userUid,
                                          session=session,
                                          allow_anonymous=True,
                                          raise_exception=True)
    model.userUuid = user_uuid
    model.cmeType = CMETypes.ACTIVITY
    case = Case.get_case(case_uuid=model.caseUuid, raise_exception=True)
    if model.isComplete:
        case_status = session.query(CaseProgress).filter(CaseProgress.case_uuid == model.caseUuid,
                                                         CaseProgress.user_uuid == user_uuid,
                                                         CaseProgress.completed_at.is_(None)).one_or_none()
        if case_status:
            task = send_event_cme_completed_to_user_task.si(case_uuid=case.case_uuid,
                                                            completed_at=datetime.now(timezone.utc),
                                                            user_uuid=user_uuid)

    cp = CaseProgress.create_or_update(user_uuid=user_uuid,
                                       case_uuid=model.caseUuid,
                                       content_position=model.contentPosition,
                                       is_complete=model.isComplete,
                                       session=session)

    data = CaseProgressData.from_orm(cp)
    cpm = CaseProgressStateModel(case_data=data)
    state = FirestoreCaseProgressState(user_uid=model.userUid, content=cpm, case_uuid=model.caseUuid)
    state.firestore_write()

    if cp.completed_at and case.case_type == CaseType.CME and model.degreeType:
        if task:
            task.link(upload_cme_certificate.si(cme_content_position=model))
        else:
            task = upload_cme_certificate.si(cme_content_position=model)

    return {'success': f"Case progress updated", "task": task}


def update_cme_for_anonymous_user(anon_user_uuid, user_uid, user_uuid=None, session=None):
    """
    if there's user_uuid this func will update the db and firestore(stateDB) with the progress of the anonymous user for
    the existing user, else it will only push the progress(stateDB) to firestore for the new user.

    :param anon_user_uuid:
    :param user_uid:
    :param user_uuid:
    :param session:
    :return:
    """
    case_progress = session.query(CaseProgress).filter(CaseProgress.user_uuid == anon_user_uuid).all()
    for case in case_progress:
        if user_uuid:
            cp = CaseProgress.create_or_update(user_uuid=user_uuid,
                                               case_uuid=case.case_uuid,
                                               content_position=case.content_position,
                                               is_complete=case.completed_at,
                                               session=session)
            data = CaseProgressData.from_orm(cp)

        else:
            data = CaseProgressData.from_orm(case)
        cpm = CaseProgressStateModel(case_data=data)
        state = FirestoreCaseProgressState(user_uid=str(user_uid), content=cpm, case_uuid=str(case.case_uuid))
        state.firestore_write()


def do_translate_case(case_uuid, target_language):
    if not Locale.is_supported(target_language):
        logging.error("Language %s is unsupported", target_language)
        raise CaseTranslationError(msg=f"Unsupported Language {target_language}", return_code=400)
    target_language = Locale.get_from_code(target_language)
    translate_case_content(case_uuid, target_language)
    do_firebase_sync.apply(kwargs={'firebasemodel': 'CaseDetailV2', 'uuid': str(case_uuid), 'case_detail_only': True})

    return {'success': 'case translated'}
