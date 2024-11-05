from tmt._compat.pydantic import BaseModel, Extra


def create_alias(name: str) -> str:
    return name.replace('_', '-')


class BaseConfig(BaseModel):
    class Config:
        # Accept only keys with dashes instead of underscores
        alias_generator = create_alias
        extra = Extra.forbid
        validate_assignment = True
