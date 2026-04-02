from pydantic import BaseModel, Field


class ApiUserModel(BaseModel):
    apiUserToken: str = Field(alias='api_user_token')

    class Config:
        orm_mode = True
