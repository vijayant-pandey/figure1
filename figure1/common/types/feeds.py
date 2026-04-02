from pydantic import BaseModel, validator
from typing import Optional, Dict


class FeedMetaDataDocument(BaseModel):
    feed_type_uuid: str
    feedTypeUuid: str
    feed_kind: str
    feedKind: str
    is_followed: Optional[bool]
    isFollowed: Optional[bool]
    search_results_total: int = 0
    searchResultsTotal: int = 0
    endOfFeed: bool = False
    feed_name: str
    feedName: str
    hidden: bool = False

    def firestore_struct(self):
        return {
            self.feed_type_uuid: {
                **self.dict(exclude_none=True)
            }
        }

    @validator('feed_type_uuid', 'feedTypeUuid', pre=True)
    def stringify_uuid(cls, value):
        return str(value)


class UserFeedMetaDataDocument(BaseModel):
    user_uid: str
    userUid: str
    user_uuid: str
    userUuid: str
    username: Optional[str]
    firstName: Optional[str]
    first_name: Optional[str]
    lastName: Optional[str]
    last_name: Optional[str]
    email: Optional[str]
    feeds: Dict[str, FeedMetaDataDocument] = {}

    @validator('user_uuid', 'userUuid', pre=True)
    def stringify_uuid(cls, value):
        return str(value)
