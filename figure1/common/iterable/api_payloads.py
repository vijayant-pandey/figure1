from enum import Enum
from typing import List
from typing import Optional

from pydantic import BaseModel
from pydantic import EmailStr


class IterableSupportedWebHooks(Enum):
    emailSubscribe = 'emailSubscribe'
    emailUnsubscribe = 'emailUnSubscribe'
    hostedUnsubscribeClick = 'hostedUnsubscribeClick'
    emailSend = 'emailSend'


class IterableUpdateEmail(BaseModel):
    currentEmail: EmailStr
    newEmail: EmailStr


class IterableEmailSubscribe(BaseModel):
    messageTypeIds: List[int] = []
    messageTypeId: Optional[int]
    email: EmailStr


class IterableWebHookBase(BaseModel):
    email: EmailStr
    eventName: IterableSupportedWebHooks
    dataFields: Optional[IterableEmailSubscribe]

    class Config:
        use_enum_values = True
