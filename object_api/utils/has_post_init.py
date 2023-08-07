import asyncio
from pydantic import BaseModel


class HasPostInitMixin(BaseModel):
    def __init__(self):
        super().__init__()

    def __post_init__(self):
        pass
