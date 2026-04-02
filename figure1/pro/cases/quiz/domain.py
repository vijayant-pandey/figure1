import logging

from sqlalchemy import and_
from figure1.common.firebase import do_firebase_sync
from figure1.exceptions import UserUIDNotFound
from figure1.core import managed_session
from figure1.common.models.db import User, QuestionOption, QuestionVote, Content, AnonymousUser
from figure1.common.types import MediaModel
from figure1.common.models.firebase import QuizStateModel, QuizContentItem, QuizOption, \
    FirestoreCaseProgressState


def _get_user_uuid(user_uid, session):
    try:
        user_uuid = User.get_user_uuid_by_uid(user_uid=user_uid, session=session, raise_exception=True)
    except UserUIDNotFound:
        u = AnonymousUser()
        u.user_uid = user_uid
        session.merge(u)
        user = session.query(AnonymousUser).get(user_uid)
        user_uuid = str(user.user_uuid)
    return user_uuid


@managed_session
def submit_quiz_selection(user_uid, content_uuid, option_uuid, free_form_text, session):
    """
    Updates quiz selection for a user and pushes update to firestore.

    :param user_uid:
    :param content_uuid:
    :param option_uuid:
    :param session:
    :return: {}
    """

    user_uuid = _get_user_uuid(user_uid=user_uid, session=session)
    option = session.query(QuestionOption) \
        .filter(QuestionOption.content_uuid == content_uuid,
                QuestionOption.question_option_uuid == option_uuid) \
        .one_or_none()
    if not option:
        return {'error': f'Question option {option_uuid} was not found belonging to content {content_uuid}'}

    options = []
    for o in session.query(QuestionOption).filter(QuestionOption.content_uuid == content_uuid).all():
        options.append(QuizOption.from_orm(o))

    QuestionVote.create(question_option_uuid=option_uuid,
                        user_uuid=user_uuid,
                        free_form_text=free_form_text,
                        session=session)

    content_item = session.query(Content).filter(Content.content_uuid == content_uuid).one_or_none()
    if not content_item:
        return {"error": "Content item not found"}

    ci = []
    for content in session.query(Content) \
            .filter(Content.case_uuid == content_item.case_uuid) \
            .all():
        media_list = []
        if content.media:
            for m in content.media:
                media_list.append(MediaModel.from_orm(m))
        quiz_content_item = QuizContentItem.from_orm(content)

        if str(content.content_uuid) == content_uuid:
            quiz_content_item.userVote = option_uuid
            quiz_content_item.userFreeFormText = free_form_text
            quiz_content_item.options = options
        ci.append(quiz_content_item)
    case_uuid = str(content_item.case_uuid)
    qm = QuizStateModel(content_items=ci, case_uuid=str(content_item.case_uuid))
    state = FirestoreCaseProgressState(user_uid=user_uid, content=qm, case_uuid=str(content_item.case_uuid))
    state.firestore_write()
    task = do_firebase_sync.si(uuid=case_uuid, firebasemodel="CaseDetailV2", merge=False)
    return {'task': task, 'success': 'Quiz answer submitted'}


@managed_session
def reset_quiz(user_uid, content_uuid, session):
    user_uuid = _get_user_uuid(user_uid=user_uid, session=session)

    for vote in session.query(QuestionVote) \
            .join(QuestionOption, QuestionOption.question_option_uuid == QuestionVote.question_option_uuid) \
            .filter(QuestionVote.user_uuid == user_uuid,
                    QuestionOption.content_uuid == content_uuid) \
            .all():
        vote.mark_deleted()
    content_item = session.query(Content).filter(Content.content_uuid == content_uuid).one_or_none()
    if not content_item:
        return {"error": "Content item not found"}
    FirestoreCaseProgressState(user_uid=user_uid,
                               case_uuid=str(content_item.case_uuid)).firestore_reset(content_uuid=content_uuid)

    # TODO: update quiz votes in ES

    return {'success': 'Quiz reset'}
