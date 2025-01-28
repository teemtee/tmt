from tmt._compat.pydantic import BaseModel, Extra
from tmt.utils import key_to_option


class BaseConfig(BaseModel):
    class Config:
        # Accept only keys with dashes instead of underscores
        alias_generator = key_to_option
        extra = Extra.forbid
        validate_assignment = True
