from functools import wraps
from typing import Any
from pydantic import BaseModel


class decorator(BaseModel):
    __dec_name__: str = "__decorator__"

    def __call__(self, func: callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        setattr(wrapper, self.__dec_name__, self)

        return wrapper

    @classmethod
    def all(this_cls, class_: type) -> list:
        return [
            getattr(class_, attr)
            for attr in dir(class_)
            if hasattr(getattr(class_, attr), this_cls.__dec_name__)
            and isinstance(getattr(class_, attr), this_cls)
        ]
