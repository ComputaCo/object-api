from __future__ import annotations

from abc import ABC, ABCMeta, abstractmethod
from typing import Annotated, Any, Generic, Self, TypeVar
from uuid import UUID
import uuid
import fastapi
import httpx

from pydantic import UUID4, BaseModel, Field
from fastapi import APIRouter
from sqlmodel import SQLModel
from object_api.app import App

from object_api.router_builder import RouterBuilder
from object_api.service_builder import ServiceBuilder
from object_api.utils.has_post_init import HasPostInitMixin
from object_api.utils.python import attr_is_list


T = TypeVar("T", bound=BaseModel)


class Entity(Generic[T], HasPostInitMixin, SQLModel, ABC, table=False):
    class Meta:
        router = RouterBuilder()
        service = ServiceBuilder()

    id: UUID4 = Field(default_factory=uuid.uuid4)

    class CreateArgs(BaseModel):
        pass

    class UpdateArgs(BaseModel):
        pass

    def __post_init__(self):
        self._ALL_ENTITIES[self.id] = self

    def __del__(self):
        del self._ALL_ENTITIES[self.id]

    @Meta.router.post("")
    @classmethod
    def create(cls, args: CreateArgs) -> Self:
        return cls(**args.dict())

    @Meta.router.get(f"{{id}}")
    @classmethod
    async def get_by_id(cls, id: UUID4) -> T:
        return cls._ALL_ENTITIES[id]

    @Meta.router.get("")
    @classmethod
    async def get_all(cls, page: int = 0, page_size: int = 100) -> list[T]:
        return list(cls._ALL_ENTITIES.values())[
            page * page_size : (page + 1) * page_size
        ]

    @Meta.router.patch()
    def update(self, updates: UpdateArgs) -> None:
        for key, value in updates.dict().items():
            setattr(self, key, value)

    @Meta.router.post("delete")
    @Meta.router.delete("")
    def delete(self) -> None:
        del self._ALL_ENTITIES[self.id]
        del self

    @property
    def router(self) -> APIRouter:
        if not self.Meta.router.router:
            self.Meta.router.build_router(self)
        return self.Meta.router.router

    @property
    def servicemethods(self) -> list[callable]:
        return self.Meta.service.servicemethods(self)
