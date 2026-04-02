from typing import List, Union, Optional

from pydantic import BaseModel, Field, validator

from figure1.core import FirestoreSyncBase
from figure1.common.types import MediaModel


class QuizOption(BaseModel):
    isAnswer: bool = Field(alias="is_answer")
    questionOptionUuid: str = Field(alias="question_option_uuid")
    displayOrder: int = Field(alias="display_order")

    @validator('questionOptionUuid', pre=True)
    def stringify_uuid(cls, value):
        return str(value)

    class Config:
        orm_mode = True


class QuizContentItem(BaseModel):
    contentUuid: str = Field(alias="content_uuid")
    title: Optional[str]
    caption: Optional[str]
    contentType: str = Field(alias="content_type")
    displayOrder: int = Field(alias="display_order")
    userVote: Optional[str]
    userFreeFormText: Optional[str]
    options: Optional[List[QuizOption]]
    media: List[Optional[MediaModel]]

    class Config:
        orm_mode = True

    @validator('contentUuid', 'userVote', pre=True)
    def stringify_uuid(cls, value):
        return str(value)

    @validator('contentType', pre=True)
    def convert_enum(cls, value):
        if hasattr(value, 'name'):
            return value.name.lower()
        return value.lower()

    def as_firestore_dict(self):
        return self.dict(exclude_none=True)


class QuizStateModel(BaseModel):
    content_items: List[QuizContentItem]

    def as_firestore_dict(self):
        d = {}
        for i in self.content_items:
            d.update({i.contentUuid: i.as_firestore_dict()})
        return d


class CaseProgressData(BaseModel):
    contentPosition: Optional[int] = Field(alias="content_position")
    completedAt: Optional[str] = Field(alias="completed_at")

    class Config:
        orm_mode = True

    @validator('completedAt', pre=True)
    def stringify_datetime(cls, value):
        return str(value) if value else None

    def as_firestore_dict(self):
        return self.dict(exclude_none=False)


class CaseProgressStateModel(BaseModel):
    case_data: CaseProgressData

    class Config:
        orm_mode = True


class FirestoreUserState(FirestoreSyncBase):
    """
    Writes general user state data such as last seen time etc
    """
    user_uid: Optional[str]
    lastSeen: Optional[str] = Field(alias='last_seen')

    @property
    def firestore_doc_reference(self):
        return self.fs_client \
            .collection('usersDB') \
            .document(self.user_uid) \
            .collection('stateDB') \
            .document('state')

    def generate_firestore_document(self, session=None) -> dict:
        return self.dict()

    def firestore_reset(self):
        self.firestore_doc_reference.delete()

    @validator('lastSeen', pre=True)
    def stringify_uuid(cls, value):
        return str(value) if value else None

    class Config:
        orm_mode = True


class FirestoreCaseProgressState(FirestoreSyncBase):
    case_uuid: str
    user_uid: str
    content: Union[QuizStateModel, CaseProgressStateModel, None] = None

    @validator('case_uuid', pre=True)
    def stringify_uuid(cls, value):
        return str(value) if value else None

    @property
    def firestore_doc_reference(self):
        return self.fs_client \
            .collection('usersDB') \
            .document(self.user_uid) \
            .collection('stateDB') \
            .document(self.case_uuid)

    def generate_firestore_document(self, session=None) -> dict:
        fs_doc = {}
        if hasattr(self.content, 'content_items'):
            fs_doc.update({**self.content.as_firestore_dict()})
        if hasattr(self.content, 'case_data'):
            fs_doc.update({"case": self.content.case_data.as_firestore_dict()})
        return fs_doc

    def firestore_reset(self, content_uuid):
        self.fs_client.set({content_uuid: {'userVote': None}}, merge=True)
