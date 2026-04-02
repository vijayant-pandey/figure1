from enum import Enum
from typing import List
from typing import Optional

from pydantic import BaseModel
from pydantic import EmailStr
from pydantic import root_validator


class IterableModelBase(BaseModel):
    class Config:
        fields = {
            'api_call': {'exclude': True},
            'api_method': {'exclude': True},
        }
        use_enum_values = True


class IterableResponseCode(Enum):
    Success = "Success"
    BadApiKey = "BadApiKey"
    BadParams = "BadParams"
    BadJsonBody = "BadJsonBody"
    QueueEmailError = "QueueEmailError"
    GenericError = "GenericError"
    InvalidEmailAddressError = "InvalidEmailAddressError"
    DatabaseError = "DatabaseError"
    EmailAlreadyExists = "EmailAlreadyExists"
    Forbidden = "Forbidden"


class IterableChannelTypes(Enum):
    Marketing = "Marketing"
    Transactional = "Transactional"


class IterableMessageMedium(Enum):
    Email = "Email"
    SMS = "SMS"
    Push = "Push"


class HttpMethods(Enum):
    POST = "post"
    GET = "get"
    DELETE = "delete"
    PUT = "put"


class UpdateUserSubscriptionsModel(IterableModelBase):
    api_call: str = "/iterable/profile/updateSubscriptions"
    api_method: HttpMethods = "post"
    email: Optional[EmailStr]
    userId: Optional[str]
    emailListIds: Optional[List[int]] = []
    unsubscribedChannelIds: Optional[List[int]] = []
    unsubscribedMessageTypeIds: Optional[List[int]] = []
    subscribedMessageTypeIds: Optional[List[int]] = []
    campaignId: Optional[int] = 0
    templateId: Optional[int] = 0


class MessageType(BaseModel):
    id: int
    createdAt: int
    updatedAt: int
    name: str
    subscriptionPolicy: str
    frequencyCap: Optional[int] = None


class IterableChannelModel(IterableModelBase):
    id: int
    name: Optional[str] = None
    channelType: IterableChannelTypes
    messageMedium: IterableMessageMedium
    messageTypes: List[MessageType]


class IterablePostResponseModel(IterableModelBase):
    """
    These fields are present for any non-bulk post/delete request.
    """
    msg: Optional[str]
    code: IterableResponseCode
    params: Optional[dict]
    isError: bool = False

    @root_validator()
    def is_error(cls, values):
        values['isError'] = False
        if values.get('code') != IterableResponseCode.Success.value:
            values['isError'] = True
        return values


class IterablePostBulkResponseModel(IterableModelBase):
    """
    These fields are present in all responses to bulk requests, in addition, each bulk request has specific fields.
    """
    successCount: int
    failCount: int
    invalidEmails: List[str] = []
    invalidUserIds: List[str] = []
