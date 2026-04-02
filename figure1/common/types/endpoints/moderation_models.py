from pydantic import BaseModel, HttpUrl, Field, constr
from typing import Optional, List
from figure1.common.types import VerificationStatus


class PartnerCaseUpdate(BaseModel):
    externalLinkUrl: Optional[HttpUrl] = Field(alias='external_link_url')
    externalLinkText: Optional[str] = Field(alias='external_link_text')
    sponsoredText: Optional[str] = Field(alias='sponsored_text')
    disclosureText: Optional[str] = Field(alias='disclosure_text')


class VerificationUpdate(BaseModel):
    userUids: List[str] = Field(alias='user_uids')
    moderatorUid: str = Field(alias='moderator_uid')


class VerificationTagUpdate(VerificationUpdate):
    tagUuids: List[str] = Field(alias='tag_uuids')


class VerificationStatusUpdate(VerificationUpdate):
    verificationStatus: VerificationStatus = Field(alias='state')
    flagForReview: bool = Field(alias='flag_for_review', default=False)


class VerificationNote(VerificationUpdate):
    verificationNote: constr(curtail_length=1000)
