import uuid
import logging
from typing import List
from sqlalchemy import Column, ForeignKey, Text, Boolean, Integer, String
from sqlalchemy.orm import Session, relationship
from sqlalchemy.dialects.postgresql import UUID
from figure1.core import Base, HasCreateUpdateDeleteTime, HasCreateTime
from .c_content_update_model import Content
from .c_case_model import Case
from .user_models import User

logger = logging.getLogger(__name__)


class QAnswerOption(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "c_question_answer_option"
    question_uuid = Column(UUID(as_uuid=True), ForeignKey('c_question.question_uuid'))
    answer_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    answer_text = Column(Text)
    answer_suggested_text = Column(Text)
    has_extra_input = Column(Boolean, default=False)
    next_question = Column(UUID(as_uuid=True), ForeignKey('c_question.question_uuid'))
    answer_group_uuid = Column(UUID(as_uuid=True), ForeignKey('c_answer_group.answer_group_uuid'))
    answer_display_order = Column(Integer)
    answer_group = relationship('QAnswerGroup', backref='answers')


class QAnswerGroup(Base, HasCreateUpdateDeleteTime):
    __tablename__ = 'c_answer_group'
    answer_group_uuid = Column(UUID(as_uuid=True), primary_key=True)
    question_uuid = Column(UUID(as_uuid=True), ForeignKey('c_question.question_uuid'))
    answer_group_heading = Column(Text)
    answer_group_display_order = Column(Integer)


class Question(Base, HasCreateUpdateDeleteTime):
    """
    Currently this is only used for caseCME questions.

    All questions require a next_question entry to be valid unless it is the last question. If there is a chain
     of questions, the last one is the one with no next_question entry.
    A given set of questions can have multiple endpoints.
    """
    __tablename__ = "c_question"
    question_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    question_set_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), nullable=False)
    question_set_label = Column(Text, nullable=True)
    question_text = Column(Text)
    question_type = Column(Text)
    next_question = Column(UUID(as_uuid=True), nullable=True)
    display_order = Column(Integer, nullable=True)
    answer_groups = relationship(QAnswerGroup)

    @staticmethod
    def create_question(question_set_label=None,
                        question_set_uuid=None,
                        question_text=None,
                        next_question=None,
                        question_type=None,
                        display_order=None) -> 'Question':
        """

        :param question_set_label: The label for the question set, should be the same for a given set, but not enforced
        :type question_set_label: str

        :param question_set_uuid: The uuid identifying a set of questions
        :type question_set_uuid: str

        :param question_text: The text of the question
        :type question_text: str

        :param next_question: The question_uuid of the question that comes next
        :type next_question: str

        :param display_order: The display order for this question
        :type display_order: int

        :return:
        """
        question = Question()
        question.question_uuid = uuid.uuid4()
        if question_set_uuid is None:
            logger.info("Creating new question set")
            question.question_set_uuid = uuid.uuid4()
        else:
            question.question_set_uuid = question_set_uuid
        if question_set_label:
            question.question_set_label = question_set_label
        if question_text:
            question.question_text = question_text
        if next_question:
            question.next_question = next_question
        if display_order is not None:
            question.display_order = display_order
        if question_type is not None:
            question.question_type = question_type

        return question

    def create_answer_group(self,
                            answer_group_heading=None,
                            answer_group_display_order=None) -> QAnswerGroup:
        answer_group = QAnswerGroup()
        answer_group.question_uuid = self.question_uuid
        answer_group.answer_group_uuid = uuid.uuid4()

        if answer_group_heading is not None:
            answer_group.answer_group_heading = answer_group_heading

        if answer_group_display_order is not None:
            answer_group.answer_group_display_order = answer_group_display_order

        self.answer_groups.append(answer_group)

        return answer_group

    def create_answer(self,
                      answer_group: QAnswerGroup,
                      answer_text=None,
                      answer_suggested_text=None,
                      answer_display_order=None,
                      next_question=None,
                      has_extra_input=False):
        if not isinstance(answer_group, QAnswerGroup):
            raise ValueError("Answer must have an answer group")

        if answer_text is None:
            raise ValueError("Answer must have text associated with it")
        answer = QAnswerOption()
        answer.answer_uuid = uuid.uuid4()
        answer.question_uuid = self.question_uuid
        answer.answer_group_uuid = answer_group.answer_group_uuid
        answer.answer_text = answer_text
        answer.has_extra_input = has_extra_input
        if answer_suggested_text:
            answer.answer_suggested_text = answer_suggested_text
        if next_question is not None:
            answer.next_question = next_question
        if answer_display_order is not None:
            answer.answer_display_order = answer_display_order
        answer_group.answers.append(answer)
        return answer_group

    @staticmethod
    def get_questions(question_set_uuid, session=None) -> List['Question']:
        """
        Takes a question set uuid and returns a list of question objects
        :param question_set_uuid:
        :param session:
        :return:
        """
        return session.query(Question) \
            .filter(Question.question_set_uuid == question_set_uuid, Question.deleted_at.is_(None)) \
            .all()

    def link_questions(self, next_question_uuid):
        self.next_question = next_question_uuid
        return self


class QuestionOption(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "c_question_option"

    question_option_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    content_uuid = Column(UUID(as_uuid=True), ForeignKey(Content.content_uuid), index=True)
    display_order = Column(Integer)
    text = Column(Text)
    is_answer = Column(Boolean)
    is_free_form = Column(Boolean)

    @staticmethod
    def create_or_update(text,
                         is_answer,
                         session,
                         content_uuid=None,
                         question_option_uuid=None,
                         is_free_form=False,
                         display_order=None,
                         **kwargs):
        """
        Requires either content_uuid or question_option_uuid. Case CME questions cannot be created through this
        function intentionally, since they are required to have no content_uuid, but should still have a display
        order parameter. CME questions can be updated through this function but this does not update firestore.

        :param text: The text of the question
        :type text: str

        :param is_answer: For multiple choice, this determines if this is the answer
        :type is_answer: bool

        :param session: Database session
        :type session: Session

        :param content_uuid: Optional if the question_option_uuid is provided
        :type content_uuid: str

        :param question_option_uuid: Optional if the content_uuid is provided
        :type question_option_uuid: str

        :param is_free_form: Is free form text accepted
        :type is_free_form: bool

        :param display_order: Integer starting at 0, there can only be one question per increment
        :type display_order: int

        :return:
        """

        if session is None:
            return

        if question_option_uuid is not None:
            qo = session.query(QuestionOption).get(question_option_uuid)
        elif content_uuid is not None:
            if display_order is None:
                highest = session.query(QuestionOption.display_order) \
                    .filter(QuestionOption.content_uuid == content_uuid) \
                    .order_by(QuestionOption.display_order.desc()) \
                    .first()
                if highest:
                    display_order = highest.display_order + 1
                else:
                    display_order = 0

            qo = session.query(QuestionOption) \
                .filter(QuestionOption.content_uuid == content_uuid, QuestionOption.display_order == display_order) \
                .one_or_none()
        else:
            return
        if not qo:
            qo = QuestionOption()
            qo.question_option_uuid = uuid.uuid4()
            qo.content_uuid = content_uuid if content_uuid else None
            qo.display_order = display_order

        qo.deleted_at = None
        qo.text = text
        qo.is_answer = is_answer
        qo.is_free_form = is_free_form

        return session.merge(qo)

    @staticmethod
    def delete(content_uuid, display_order, session, skip_commit=False):
        o = session.query(QuestionOption) \
            .filter(QuestionOption.content_uuid == content_uuid, QuestionOption.display_order == display_order) \
            .one_or_none()
        if not o:
            return

        o.mark_deleted()

        if skip_commit:
            return o

        try:
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        return o

    def as_dict(self):
        return {
            'questionOptionUuid': str(self.question_option_uuid),
            'contentUuid': str(self.content_uuid),
            'displayOrder': self.display_order,
            'text': self.text,
            'isAnswer': self.is_answer,
            'isFreeForm': self.is_free_form
        }


class QuestionVote(Base, HasCreateUpdateDeleteTime):
    __tablename__ = "c_question_vote"

    question_option_uuid = Column(UUID(as_uuid=True), ForeignKey(QuestionOption.question_option_uuid), primary_key=True)
    user_uuid = Column(UUID(as_uuid=True), primary_key=True)
    free_form_text = Column(String(100000))

    @staticmethod
    def create(question_option_uuid, user_uuid, session, free_form_text=None):
        v = QuestionVote()
        v.question_option_uuid = question_option_uuid
        v.user_uuid = user_uuid
        v.free_form_text = free_form_text
        v.deleted_at = None
        return session.merge(v)

    @staticmethod
    def delete(question_option_uuid, user_uuid, session):
        v = QuestionVote()
        v.question_option_uuid = question_option_uuid
        v.user_uuid = user_uuid
        v.mark_deleted()
        return session.merge(v)

    def as_dict(self):
        return {
            'questionOptionUuid': str(self.question_option_uuid),
            'userUuid': str(self.user_uuid),
            'freeFormText': self.free_form_text
        }


class CaseCMEUserAnswer(Base, HasCreateTime):
    __tablename__ = "c_case_cme_user_answer"
    case_user_answer_uuid = Column(UUID(as_uuid=True), default=uuid.uuid4(), primary_key=True)
    case_uuid = Column(UUID(as_uuid=True), ForeignKey(Case.case_uuid), nullable=False)
    question_uuid = Column(UUID(as_uuid=True), ForeignKey(Question.question_uuid), nullable=False)
    user_answer_uuid = Column(UUID(as_uuid=True), ForeignKey(QAnswerOption.answer_uuid), nullable=True)
    user_answer_text = Column(Text)
    user_uuid = Column(UUID(as_uuid=True), ForeignKey(User.user_uuid), nullable=False)

    q_answer_option = relationship('QAnswerOption', foreign_keys='CaseCMEUserAnswer.user_answer_uuid')

    @staticmethod
    def add_user_answer(user_uuid,
                        question_uuid,
                        case_uuid,
                        user_answer_text=None,
                        user_answer_uuid=None) -> 'CaseCMEUserAnswer':
        """
        All fields are required except for user_answer_text or user_answer_uuid. Only one of those are required.
        :param user_uuid:
        :param question_uuid:
        :param case_uuid:
        :param user_answer_text:
        :param user_answer_uuid:
        :return:
        """

        cme_answer = CaseCMEUserAnswer()
        cme_answer.case_user_answer_uuid = uuid.uuid4()
        cme_answer.user_uuid = user_uuid
        cme_answer.case_uuid = case_uuid
        cme_answer.question_uuid = question_uuid

        if user_answer_uuid is not None:
            cme_answer.user_answer_uuid = user_answer_uuid
        if user_answer_text is not None:
            cme_answer.user_answer_text = user_answer_text
        if user_answer_uuid is None and user_answer_text is None:
            raise ValueError("Either user_answer_text or user_answer_uuid is required")
        return cme_answer

    @staticmethod
    def get_question_answers_text_by_display_order(case_uuid, user_uuid, display_order, session) -> List[str]:
        for qa in session.query(CaseCMEUserAnswer)\
                .join(Question, Question.question_uuid == CaseCMEUserAnswer.question_uuid)\
                .filter(CaseCMEUserAnswer.case_uuid == case_uuid,
                        CaseCMEUserAnswer.user_uuid == user_uuid,
                        Question.display_order == display_order)\
                .all():
            if qa.q_answer_option:
                yield qa.q_answer_option.answer_text
            elif qa.user_answer_text:
                yield qa.user_answer_text
