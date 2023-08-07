from __future__ import annotations

from abc import ABC, ABCMeta, abstractmethod
from typing import Annotated, Any, Generic, Self, TypeVar
from uuid import UUID
import uuid
import fastapi
import httpx

from pydantic import UUID4, BaseModel, Field
from fastapi import APIRouter, Depends
from sqlmodel import SQLModel, Session, select
from object_api.app import App

from object_api.router_builder import RouterBuilder
from object_api.service_builder import ServiceBuilder
from object_api.utils.has_post_init import HasPostInitMixin
from object_api.utils.python import MultiList, attr_is_list
from object_api.utils.session import managed_session


T = TypeVar("T", bound=BaseModel)


class Entity(Generic[T], HasPostInitMixin, SQLModel, ABC, table=False):
    class Meta:
        router = RouterBuilder()
        service = ServiceBuilder()

        # new_public: list[str] or None = None # TODO: add this parameter
        new_private: list[str] or None = None

        new_createable: list[str] or None
        new_readable: list[str] or None
        new_updateable: list[str] or None

        @classmethod
        def all_createable(cls, entity_class: type[T]) -> set[str]:
            # all readable from here to the top of the inheritance tree
            parents_createable = set(
                *(p.all_readable for p in cls.__bases__),
            )
            fields = set(entity_class.__fields__.keys())

            match cls.new_private, cls.new_createable:
                case None, None:
                    # assume all readable
                    return parents_createable.intersection(fields)
                case None, _:
                    # only add the readable fields
                    return parents_createable.intersection(cls.new_createable)
                case _, None:
                    # assume all readable except private
                    return parents_createable.intersection(fields).difference(
                        cls.new_private
                    )
                case _, _:
                    # only add the readable fields, and remove private
                    # (and raise an error if the new readable and private overlap)
                    if set(cls.new_createable).intersection(cls.new_private):
                        raise ValueError(
                            "new_readable and new_private cannot share any fields"
                        )
                    return parents_createable.intersection(
                        cls.new_createable
                    ).difference(cls.new_private)

        @classmethod
        def all_readable(cls, entity_class: type[T]) -> set[str]:
            # all readable from here to the top of the inheritance tree
            parents_readable = set(
                *(p.all_readable for p in cls.__bases__),
            )
            fields = set(entity_class.__fields__.keys())

            match cls.new_private, cls.new_readable:
                case None, None:
                    # assume all readable
                    return parents_readable.intersection(fields)
                case None, _:
                    # only add the readable fields
                    return parents_readable.intersection(cls.new_readable)
                case _, None:
                    # assume all readable except private
                    return parents_readable.intersection(fields).difference(
                        cls.new_private
                    )
                case _, _:
                    # only add the readable fields, and remove private
                    # (and raise an error if the new readable and private overlap)
                    if set(cls.new_readable).intersection(cls.new_private):
                        raise ValueError(
                            "new_readable and new_private cannot share any fields"
                        )
                    return parents_readable.intersection(cls.new_readable).difference(
                        cls.new_private
                    )

        @classmethod
        def all_updateable(cls, entity_class: type[T]) -> set[str]:
            # all updateable from here to the top of the inheritance tree
            parents_updateable = set(
                *(p.all_updateable for p in cls.__bases__),
            )
            fields = set(entity_class.__fields__.keys())

            match cls.new_private, cls.new_updateable:
                case None, None:
                    # assume all updateable
                    return parents_updateable.intersection(fields)
                case None, _:
                    # only add the updateable fields
                    return parents_updateable.intersection(cls.new_updateable)
                case _, None:
                    # assume all updateable except private
                    return parents_updateable.intersection(fields).difference(
                        cls.new_private
                    )
                case _, _:
                    # only add the updateable fields, and remove private
                    # (and raise an error if the new updateable and private overlap)
                    if set(cls.new_updateable).intersection(cls.new_private):
                        raise ValueError(
                            "new_updateable and new_private cannot share any fields"
                        )
                    return parents_updateable.intersection(
                        cls.new_updateable
                    ).difference(cls.new_private)

    id: UUID4 = Field(default_factory=uuid.uuid4)

    class CreateModel(Generic[T], BaseModel):
        """Automatically subclassed by Entity.__init_subclass__ based on the object's signature"""

        pass

    class ReadModel(Generic[T], BaseModel):
        """Automatically subclassed by Entity.__init_subclass__ based on the __exclude_fields__,
        __include_fields__, and readable attributes"""

        id: UUID4

    class UpdateModel(Generic[T], BaseModel):
        """Automatically subclassed by Entity.__init_subclass__ based on the __exclude_fields__,
        __include_fields__, readable, and updatable attributes"""

        pass

    def __init_subclass__(cls) -> None:
        # connect self.Meta to parent's Meta so that the Meta class can be inherited
        bases = cls.__bases__
        # But stop at Entity, because Entity.Meta is the only one that should be
        entity_idx = bases.index(Entity)
        bases = bases[:entity_idx]
        # filter ones that don't have a Meta
        bases = filter(lambda b: hasattr(b, "Meta"), bases)
        # now bases is all the classes that are between Entity and the subclass
        # (not including Entity or the subclass)
        cls.Meta = type(
            "Meta",
            tuple(b.Meta for b in bases),
            {},
        )

        # Now make the CreateModel, ReadModel, and UpdateModel
        cls._init_create_model()
        cls._init_read_model()
        cls._init_update_model()

        return super().__init_subclass__()

    def _init_create_model(cls) -> None:
        create_fields = set(cls.Meta.all_createable(cls))

        cls.CreateModel = type(
            f"{cls.__name__}CreateModel",
            (cls.CreateModel,),
            {"__annotations__": {k: v for k, v in create_fields}},
        )

    def _init_read_model(cls) -> None:
        read_fields = set(cls.Meta.all_readable(cls))
        if hasattr(cls, "__include_fields__"):
            read_fields.extend(cls.__include_fields__)
        if hasattr(cls, "__exclude_fields__"):
            read_fields = [
                field for field in read_fields if field not in cls.__exclude_fields__
            ]

        cls.ReadModel = type(
            f"{cls.__name__}ReadModel",
            (cls.ReadModel,),
            {"__annotations__": {k: v for k, v in read_fields}},
        )

    def _init_update_model(cls) -> None:
        update_fields = set(cls.Meta.all_updateable(cls))
        if hasattr(cls, "__include_fields__"):
            update_fields.extend(cls.__include_fields__)
        if hasattr(cls, "__exclude_fields__"):
            update_fields = [
                field for field in update_fields if field not in cls.__exclude_fields__
            ]

        cls.UpdateModel = type(
            f"{cls.__name__}UpdateModel",
            (cls.UpdateModel,),
            {"__annotations__": {k: v for k, v in update_fields}},
        )

    def get_create_model(self) -> CreateModel:
        return self.CreateModel()

    def get_read_model(self) -> ReadModel:
        return self.ReadModel(self.id)

    def get_update_model(self) -> UpdateModel:
        return self.UpdateModel()

    def __post_init__(self):
        # not all python instances should be persisted
        self.__exclude_fields__

    @Meta.router.post("")
    @managed_session
    @classmethod
    def create(cls, args: CreateModel, *, session: Session = None) -> Self:
        instance = cls(**args.dict())
        db_instance = cls.from_orm(instance)
        session.add(db_instance)
        session.commit()
        session.refresh(db_instance)
        return db_instance

    @Meta.router.get(f"{{id}}")
    @managed_session
    @classmethod
    async def get_by_id(cls, id: UUID4, session: Session = None) -> ReadModel[T]:
        obj = session.get(cls, id)
        if not obj:
            raise fastapi.HTTPException(404, f"{cls.__name__} with id {id} not found")
        return obj

    @Meta.router.get("")
    @managed_session
    @classmethod
    async def get_all(
        cls, offset: int = None, limit: int = None, session: Session = None
    ) -> list[ReadModel[T]]:
        query = select(cls)
        if offset:
            query = query.offset(offset)
        if limit:
            query = query.limit(limit)
        return list(session.exec(query).all())

    @Meta.router.patch()
    @managed_session
    def update(self, updates: UpdateModel, session: Session = None) -> None:
        for key, value in updates.dict(exclude_unset=True).items():
            setattr(self, key, value)
        session.add(self)
        session.commit()
        session.refresh(self)
        return self.get_read_model()

    @Meta.router.post("delete")
    @Meta.router.delete("")
    @managed_session
    def delete(self, session: Session = None) -> None:
        session.delete(self)
        session.commit()
        return {"ok": True}

    def __del__(self):
        self.delete()

    @property
    def router(self) -> APIRouter:
        if not self.Meta.router.router:
            self.Meta.router.build_router(self)
        return self.Meta.router.router

    @property
    def servicemethods(self) -> list[callable]:
        return self.Meta.service.servicemethods(self)
