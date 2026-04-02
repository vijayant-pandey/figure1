from pydantic import BaseModel, validator, Field
from typing import Optional, List

from figure1.core import FirestoreSyncBase


class AnswerModel(BaseModel):
    answerUuid: str = Field(alias='answer_uuid')
    answerText: str = Field(alias='answer_text')
    answerSuggestedText: Optional[str] = Field(alias='answer_suggested_text')
    nextQuestion: Optional[str] = Field(alias='next_question')
    hasExtraInput: Optional[bool] = Field(alias='has_extra_input')
    displayOrder: Optional[int] = Field(alias='answer_display_order')

    @validator('answerUuid', 'nextQuestion', pre=True)
    def stringify_uuid(cls, value):
        if value is not None:
            return str(value)

    class Config:
        orm_mode = True


class AnswerGroupModel(BaseModel):
    answerGroupUuid: str = Field(alias='answer_group_uuid', exclude=True)
    questionUuid: str = Field(alias='question_uuid', exclude=True)
    answerGroupHeading: str = Field(alias='answer_group_heading')
    displayOrder: int = Field(alias='answer_group_display_order')
    answers: List[AnswerModel] = Field(alias='answers')

    @validator('answerGroupUuid', 'questionUuid', pre=True)
    def stringify_uuid(cls, value):
        if value is not None:
            return str(value)

    class Config:
        orm_mode = True


class QuestionModel(FirestoreSyncBase):
    questionUuid: str = Field(alias='question_uuid')
    questionSetUuid: str = Field(alias='question_set_uuid')
    questionSetLabel: str = Field(alias='question_set_label')
    questionType: str = Field(alias='question_type')
    displayOrder: Optional[int] = Field(alias='display_order')
    questionText: str = Field(alias='question_text')
    nextQuestion: Optional[str] = Field(alias='next_question')
    answerGroups: Optional[List[AnswerGroupModel]] = Field(alias='answer_groups')

    @validator('questionUuid', 'nextQuestion', 'questionSetUuid', pre=True)
    def stringify_uuid(cls, value):
        if value is not None:
            return str(value)
        return value

    class Config:
        orm_mode = True

    def generate_firestore_document(self, session=None) -> dict:
        return self.dict()

    @property
    def firestore_doc_reference(self):
        return self.fs_client.collection('questionDB') \
            .document('question') \
            .collection(self.questionSetUuid) \
            .document(self.questionUuid)

    def firestore_write(self, session=None, merge=True, fs_doc=None):
        super().firestore_write(merge=True)


class QuestionMetaDataModel(FirestoreSyncBase):
    questionSetLabel: Optional[str] = Field(alias='question_set_label')
    questionSetUuid: str = Field(alias='question_set_uuid')
    displayName: str = 'CME'
    questions: Optional[List[QuestionModel]] = Field(exclude=True)

    @validator('questionSetUuid', pre=True)
    def stringify_uuid(cls, value):
        if value is not None:
            return str(value)
        return value

    class Config:
        orm_mode = True

    def generate_firestore_document(self, session=None) -> dict:
        return {self.questionSetLabel: self.dict()}

    @property
    def firestore_doc_reference(self):
        return self.fs_client.collection('questionDB') \
            .document('question')

    def firestore_write(self, session=None, merge=True, fs_doc=None):
        super().firestore_write(merge=True)
