from datetime import datetime
from datetime import timezone

from celery import chain

from figure1.common.firebase import do_firebase_sync
from figure1.common.models.db.c_question_model import QAnswerOption
from figure1.common.models.firebase import UserDBSync
from figure1.common.models.db import CaseCMEUserAnswer
from figure1.common.models.db import CaseProgress
from figure1.common.models.db import Question
from figure1.common.models.db import User
from figure1.notifications import send_event_cme_completed_to_user_task
from figure1.common.types import CMEContentPositionModel
from figure1.common.types import CMETypes
from figure1.common.types import QuestionMetaDataModel
from figure1.common.types import QuestionModel
from figure1.common.types.cme import CMEUserAnswerModel
from figure1.common.types.questions import AnswerModel
from figure1.core import managed_session
from figure1.pro.cme import upload_cme_certificate


@managed_session
def update_questions(question_set_uuid, session=None):
    q = session.query(Question).filter(Question.question_set_uuid == question_set_uuid).first()
    if not q:
        return None

    update_question_db(question_set_uuid=question_set_uuid, session=session)


@managed_session
def create_new_question_set(question_set_object, session=None):
    question_set_label = question_set_object.get('question_set_label')
    question_set_uuid = None
    question_map = {}
    for q in question_set_object.get('questions'):
        if question_set_uuid is None:
            q_inst = Question.create_question(question_set_label=question_set_label,
                                              question_text=q.get('question_text'),
                                              display_order=q.get('display_order'),
                                              question_type=q.get('question_type'))
            question_set_uuid = q_inst.question_set_uuid
            question_map.update({q.get("question_label"): q_inst})
        else:
            q_inst = Question.create_question(question_set_label=question_set_label,
                                              question_text=q.get('question_text'),
                                              display_order=q.get('display_order'),
                                              question_set_uuid=question_set_uuid,
                                              question_type=q.get('question_type'))
            question_map.update({q.get("question_label"): q_inst})
    session.add_all(question_map.values())
    session.flush()
    for q in question_set_object.get('questions'):
        q_inst = question_map.get(q.get('question_label'))
        default_next_question_inst = question_map.get(q.get('next_question_label'))
        if default_next_question_inst is not None:
            q_inst = q_inst.link_questions(default_next_question_inst.question_uuid)
            session.add(q_inst)
        for answer_group in q.get('answer_groups'):
            answer_group_inst = q_inst.create_answer_group(
                answer_group_display_order=answer_group.get('answer_group_display_order'),
                answer_group_heading=answer_group.get('answer_group_heading'))
            for answer in answer_group.get('answers'):
                next_q = answer.get('next_question_label')
                next_question_uuid = None
                if next_q:
                    next_question_instance = question_map.get(next_q)
                    if next_question_instance:
                        next_question_uuid = next_question_instance.question_uuid
                answer_group_inst = q_inst.create_answer(answer_group=answer_group_inst,
                                                         answer_text=answer.get('answer_text'),
                                                         answer_display_order=answer.get(
                                                             'answer_display_order'),
                                                         answer_suggested_text=answer.get(
                                                             'answer_suggested_text'),
                                                         has_extra_input=answer.get('answer_has_extra_input'),
                                                         next_question=next_question_uuid)
            session.add(answer_group_inst)

    session.flush()
    question_list = Question.get_questions(question_set_uuid=question_set_uuid, session=session)
    return QuestionMetaDataModel(questions=question_list,
                                 question_set_label=question_set_label,
                                 question_set_uuid=question_set_uuid)


def update_question_db(question_set_uuid, session):
    question_list = Question.get_questions(question_set_uuid=question_set_uuid, session=session)
    model = QuestionMetaDataModel.from_orm(question_list[0])
    model.questions = [QuestionModel.from_orm(q) for q in question_list]
    model.firestore_write()
    for question in model.questions:
        question.firestore_write()


@managed_session
def submit_user_case_cme_answers(user_uid, case_uuid, questions, session=None, degree_type=None):
    user_uuid = User.get_user_uuid_by_uid(user_uid=user_uid, session=session, raise_exception=True)
    cme_content_position_model = CMEContentPositionModel(user_uid=user_uid,
                                                         user_uuid=user_uuid,
                                                         case_uuid=case_uuid,
                                                         degree_type=degree_type,
                                                         is_complete=True,
                                                         content_position=0,
                                                         cmeType=CMETypes.CASE)

    answers = []
    for q in questions:
        a = CaseCMEUserAnswer.add_user_answer(user_uuid=user_uuid,
                                              case_uuid=case_uuid,
                                              question_uuid=q.get('question_uuid'),
                                              user_answer_text=q.get('answer_text'),
                                              user_answer_uuid=q.get('answer_uuid'))
        answers.append(session.merge(a))

    CaseProgress.create_or_update(user_uuid=user_uuid, case_uuid=case_uuid, session=session, is_complete=True)
    session.flush()
    user_sync_model = UserDBSync(degreeType=cme_content_position_model.degreeType, userUid=user_uid)
    task = chain(upload_cme_certificate.si(cme_content_position=cme_content_position_model),
                 do_firebase_sync.si(firebasemodel='FirebaseUserCmeDB', uuid=str(user_uuid)),
                 send_event_cme_completed_to_user_task.si(case_uuid=case_uuid,
                                                          completed_at=datetime.now(timezone.utc),
                                                          user_uuid=user_uuid,
                                                          is_case_cme=True))
    task.apply_async()
    user_sync_model.firestore_write(merge=True)

    for a in answers:
        model = CMEUserAnswerModel.from_orm(a)
        model.userUid = user_uid
        q_answer_option = session.query(QAnswerOption).get(model.userAnswerUuid)
        model.questionAnswerOption = AnswerModel.from_orm(q_answer_option)
        model.firestore_write(merge=True)
