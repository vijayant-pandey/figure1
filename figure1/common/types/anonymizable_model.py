from typing import Optional

from pydantic import BaseModel, Field


class AnonymousAuthorFields(BaseModel):
    toExclude: dict = Field(default={"displayName": True,
                                     "avatar": True,
                                     "username": True,
                                     "userUid": True,
                                     "userUuid": True,
                                     "profileLink": True,
                                     "profileLinkText": True,
                                     "userType": True,
                                     "countryUuid": True,
                                     "stateUuid": True,
                                     "isPartner": True,
                                     "legacyAccount": True},
                            alias='to_exclude')
    toInclude: Optional[dict]


class AnonymousFeedCardFields(BaseModel):
    toExclude: dict = Field(default={"authorUid": True,
                                     "authorUsername": True},
                            alias="to_exclude")
    toInclude: Optional[dict]


class AnonymousCommentFields(BaseModel):
    toExclude: dict = Field(default={"authorUuid": True,
                                     "username": True,
                                     "avatar": True,
                                     "email": True},
                            alias="to_exclude")
    toInclude: Optional[dict]


class AnonymizableBaseModel(BaseModel):
    isAnonymous: Optional[bool] = Field(alias="is_anonymous")
    fieldsToExcludeIfAnonymous: dict = Field(exclude=True)

    def dict(self, **kwargs):
        exclude = getattr(self.Config, "exclude", dict())

        if isinstance(exclude, set):
            exclude = dict.fromkeys(exclude, True)
        if self.isAnonymous is True:
            exclude = {**self.fieldsToExcludeIfAnonymous, **exclude}

        kwargs_exclude = kwargs.get("exclude", dict())
        if isinstance(kwargs_exclude, set):
            kwargs_exclude = dict.fromkeys(kwargs_exclude, True)

        exclude = {**exclude, **kwargs_exclude}
        kwargs.pop("exclude", None)
        return super().dict(exclude=exclude, **kwargs)

    def copy(self, **kwargs):
        fields_to_exclude = self.fieldsToExcludeIfAnonymous
        isAnonymous = self.isAnonymous

        copy_obj = super().copy(**kwargs)
        copy_obj.fieldsToExcludeIfAnonymous = fields_to_exclude
        copy_obj.isAnonymous = isAnonymous

        return copy_obj
