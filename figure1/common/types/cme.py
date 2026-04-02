import re
from enum import Enum
from typing import Optional
from typing import Union

from pydantic import BaseModel
from pydantic import Field
from pydantic import HttpUrl
from pydantic import validator
from pydantic import constr

from figure1.common.types.media import MediaModel
from figure1.common.types.questions import AnswerModel
from figure1.core import FirestoreSyncBase


class CMETypes(Enum):
    CASE = 'case_cme'
    ACTIVITY = 'activity'


class CmeDegreeTypeOptions(Enum):
    MD = 'M.D.'
    DO = 'D.O.'


class CmeCertificateStatus(Enum):
    INELIGIBLE = "ineligible"
    GENERATING = "generating"
    COMPLETED = "completed"


class CMEContentPositionModel(BaseModel):
    caseUuid: str = Field(alias='case_uuid')
    userUid: str = Field(alias='user_uid')
    userUuid: Optional[str] = Field(alias='user_uuid')
    contentPosition: Optional[int] = Field(alias='content_position')
    isComplete: Optional[bool] = Field(alias='is_complete')
    degreeType: Union[CmeDegreeTypeOptions, constr(strip_whitespace=True, max_length=10), None] = Field(
        alias='degree_type')
    cmeType: CMETypes = CMETypes.ACTIVITY

    class Config:
        orm_mode = True

    @validator('caseUuid', 'userUuid', pre=True, check_fields=False)
    def stringify_uuid(cls, value):
        return str(value) if value else None

    @validator('degreeType', pre=True)
    def handle_degree_type(cls, value):
        """
        Checks if degree type is valid. Accepts an instance of CmeDegreeTypeOptions, a str, or None.
        If a str is passed, all punctuation and spaces are removed and an attempt is made to match to a degree type in
        CmeDegreeTypeOptions.

        If None is passed, it is returned.

        if an instance of CmeDegreeTypeOptions is passed, the instance is returned.

        :param value: See description
        :type value: Union[CmeDegreeTypeOptions, str, None]

        :raises ValueError: If the passed in value cannot resolve to a CmeDegreeTypeOptions
        """

        if value is None:
            return None

        if isinstance(value, CmeDegreeTypeOptions):
            return value

        if not isinstance(value, str):
            raise ValueError("Degree Type must be a string or a member of DegreeType or None")

        clean_value = re.sub(r'[._\-\s+\"\']+', '', value)
        for dt in CmeDegreeTypeOptions.__members__.values():
            if dt.value.lower() == clean_value.lower():
                return dt
            elif dt.name.lower() == clean_value.lower():
                return dt
        return value


class CmeHubCardModel(BaseModel):
    caseUuid: Optional[str]
    credits: Optional[float] = 0.0
    currentSlide: Optional[int] = 0
    totalSlides: Optional[int] = 0
    completedAt: Optional[str]
    startAt: Optional[str]
    endAt: Optional[str]
    certificateStatus: Optional[CmeCertificateStatus]
    certificateDownloadUrl: Optional[HttpUrl]
    isEligible: Optional[bool]
    shareLink: Optional[HttpUrl]
    title: Optional[str]
    heading: Optional[str]
    media: Optional[MediaModel]
    cmeType: Optional[CMETypes]

    class Config:
        use_enum_values = True


class CMEUserAnswerModel(FirestoreSyncBase):
    caseUuid: str = Field(alias='case_uuid')
    questionUuid: str = Field(alias='question_uuid')
    userAnswerUuid: str = Field(alias='user_answer_uuid')
    userAnswerText: Optional[str] = Field(alias='user_answer_text')
    userUid: Optional[str] = Field(alias='user_uid')
    userUuid: str = Field(alias='user_uuid')
    questionAnswerOption: Optional[AnswerModel] = Field(alias='q_answer_option')

    @validator('caseUuid', 'questionUuid', 'userAnswerUuid', 'userUuid', pre=True)
    def stringify_uuid(cls, value):
        if value is not None:
            return str(value)
        return value

    class Config:
        orm_mode = True

    def generate_firestore_document(self, session=None) -> dict:
        result = self.dict(exclude={'questionAnswerOption'})
        if self.questionAnswerOption:
            result['questionAnswerOption'] = {self.questionAnswerOption.answerUuid: self.questionAnswerOption.dict()}
        return result

    @property
    def firestore_doc_reference(self):
        return self.fs_client.collection('userCmeDB') \
            .document(self.userUid) \
            .collection('completed') \
            .document(self.caseUuid) \
            .collection('answers') \
            .document(self.questionUuid)
