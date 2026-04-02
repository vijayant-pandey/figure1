from pydantic import BaseModel, root_validator


class Version(BaseModel):
    current: int
    minimum: int

    @root_validator
    def current_is_greater_or_equal_to_minimum(cls, values):
        if values['current'] < values['minimum']:
            raise ValueError("The current version is less than the minimum version")

        return values
