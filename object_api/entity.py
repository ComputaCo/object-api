from __future__ import annotations

from abc import ABC, ABCMeta, abstractmethod
from datetime import datetime
from functools import cache, wraps
import inspect
from typing import Annotated, Any, Generic, Self, TypeVar, get_origin
from uuid import UUID
import uuid
from exports import export
import fastapi
import httpx
from stringcase import snakecase

from pydantic import UUID4, BaseModel, Field
from fastapi import APIRouter, Depends
from sqlmodel import Session, select
from object_api import router, servicemethod
from object_api.app import App
import inspect_mate_pp
from object_api.utils.errors import InvalidIndexError

from object_api.utils.dynamic_default import dynamic_default
from object_api.utils.has_post_init import HasPostInitMixin
from object_api.model_variants import (
    CreateModelBase,
    ReadModelBase,
    UpdateModelBase,
    DBModelBase,
    create_variant,
    db_variant,
    read_variant,
    update_variant,
)
from object_api.utils.python import (
    get_class_dict_attr_generic_types,
    get_class_list_attr_generic_type,
)


@export
@create_variant(include=[])
@read_variant(include=["id"])
@update_variant(include=[])
@db_variant(include=["id"])
class Entity(HasPostInitMixin, BaseModel, ABC):
    CreateModel: type[CreateModelBase]
    ReadModel: type[ReadModelBase]
    UpdateModel: type[UpdateModelBase]
    DBModel: type[DBModelBase]

    def get_create_model(self) -> CreateModel:
        return self.CreateModel(**self.get_db_model().dict())

    def get_read_model(self) -> ReadModel:
        return self.ReadModel(**self.get_db_model().dict())

    def get_update_model(self) -> UpdateModel:
        return self.UpdateModel(**self.get_db_model().dict())

    def get_db_model(self) -> DBModel:
        return self.get_by_id(self.id)

    id: UUID4 = Field(default_factory=uuid.uuid4)

    @router.post("")
    @dynamic_default("db_session", App.current_db_session)
    @classmethod
    def create(cls, args: CreateModel, *, db_session: Session = None) -> Self:
        instance = cls(**args.dict())
        db_instance = cls.DBModel.from_orm(instance)
        db_session.add(db_instance)
        db_session.commit()
        db_session.refresh(db_instance)
        return db_instance

    @dynamic_default("db_session", App.current_db_session)
    @classmethod
    def get_by_id(cls, id: UUID4, *, db_session: Session = None) -> DBModel:
        db_instance = db_session.get(cls.DBModel, id)
        if not db_instance:
            raise InvalidIndexError(f"{cls.__name__} with id {id} not found")
        return db_instance

    @dynamic_default("db_session", App.current_db_session)
    @classmethod
    def get_by_id_or_none(
        cls, id: UUID4, *, db_session: Session = None
    ) -> DBModel or None:
        try:
            return cls.get_by_id(id, db_session=db_session)
        except InvalidIndexError as e:
            return None

    @router.get(f"{{id}}")
    @dynamic_default("db_session", App.current_db_session)
    @classmethod
    def read_by_id(cls, id: UUID4, *, db_session: Session = None) -> ReadModel:
        try:
            return cls.get_by_id(id, db_session=db_session)
        except InvalidIndexError:
            raise fastapi.HTTPException(404, f"{cls.__name__} with id {id} not found")

    @dynamic_default("db_session", App.current_db_session)
    @classmethod
    def get_by_ids(cls, ids: list[UUID4], *, db_session: Session = None) -> DBModel:
        statement = select(cls.DBModel).where(cls.DBModel.id.in_(ids))
        db_instances = db_session.exec(statement).all()
        if not db_instances:
            raise InvalidIndexError(f"{cls.__name__} with id {id} not found")
        return db_instances

    @router.get()
    @dynamic_default("db_session", App.current_db_session)
    @classmethod
    def read_by_ids(cls, ids: list[UUID4], *, db_session: Session = None) -> ReadModel:
        try:
            return cls.get_by_ids(ids, db_session=db_session)
        except InvalidIndexError:
            raise fastapi.HTTPException(404, f"{cls.__name__} with id {id} not found")

    @dynamic_default("db_session", App.current_db_session)
    @classmethod
    def get_all(
        cls, offset: int = None, limit: int = None, *, db_session: Session = None
    ) -> list[DBModel]:
        query = select(cls.DBModel)
        if offset:
            query = query.offset(offset)
        if limit:
            query = query.limit(limit)
        return list(db_session.exec(query).all())

    @router.get("")
    @dynamic_default("db_session", App.current_db_session)
    @classmethod
    def read_all(
        cls, offset: int = None, limit: int = None, *, db_session: Session = None
    ) -> list[ReadModel]:
        return cls.get_all(offset=offset, limit=limit, db_session=db_session)

    @router.patch()
    @dynamic_default("db_session", App.current_db_session)
    def update(self, updates: UpdateModel, *, db_session: Session = None) -> ReadModel:
        for key, value in updates.dict(exclude_unset=True).items():
            setattr(self, key, value)
        db_session.add(self.get_db_model())
        db_session.commit()
        db_session.refresh(self)
        return self.get_read_model()

    @router.post("delete")
    @router.delete("")
    @dynamic_default("db_session", App.current_db_session)
    def delete(self, *, db_session: Session = None) -> None:
        db_session.delete(self)
        db_session.commit()
        return {"ok": True}

    @classmethod
    def build_servicemethods(cls):
        for servicemethod in cls.get_servicemethods():
            # make sure the methods are static or class methods
            if not (
                inspect_mate_pp.is_class_method(cls, servicemethod.__name__)
                or inspect_mate_pp.is_static_method(cls, servicemethod.__name__)
            ):
                raise RuntimeError(
                    f"Service methods must be static methods or class methods but {servicemethod} is not."
                )

    @classmethod
    def start_service(cls):
        cls.start_servicemethods(cls)
        cls.start_interval_servicemethod_scheduler(cls)

    @classmethod
    def stop_service(cls):
        cls.stop_servicemethods(cls)
        cls.stop_interval_servicemethod_scheduler(cls)

    @classmethod
    def start_servicemethods(cls):
        for servicemethod in cls.get_startup_servicemethods(cls):
            servicemethod()

    @classmethod
    def stop_servicemethods(cls):
        for servicemethod in cls.get_shutdown_servicemethods(cls):
            servicemethod()

    @classmethod
    def start_interval_servicemethod_scheduler(cls):
        for servicemethod in cls.get_interval_servicemethods(cls):
            servicemethod_meta: servicemethod = getattr(
                servicemethod, servicemethod.__dec_name__
            )
            servicemethod_meta.app = App.CURRENT_APP
            servicemethod_meta.last_executed = datetime.now()
            servicemethod_meta.scheduler_job = App.CURRENT_APP.scheduler.cyclic(
                servicemethod.__servicemethod_meta__.interval, servicemethod
            )

    @classmethod
    def stop_interval_servicemethod_scheduler(cls):
        for servicemethod in cls.get_interval_servicemethods(cls):
            servicemethod_meta: servicemethod = getattr(
                servicemethod, servicemethod.__dec_name__
            )
            App.CURRENT_APP.scheduler.delete_job(servicemethod_meta.scheduler_job)

    @classmethod
    @cache
    def get_servicemethods(cls) -> list[callable]:
        return servicemethod.all(cls)

    @classmethod
    @cache
    def get_startup_servicemethods(cls) -> list[callable]:
        return filter(
            lambda servicemethod: servicemethod.__servicemethod__.startup,
            cls.get_servicemethods(),
        )

    @classmethod
    @cache
    def get_shutdown_servicemethods(cls) -> list[callable]:
        return filter(
            lambda servicemethod: servicemethod.__servicemethod__.shutdown,
            cls.get_servicemethods(),
        )

    @classmethod
    @cache
    def get_interval_servicemethods(cls) -> list[callable]:
        return filter(
            lambda servicemethod: servicemethod.__servicemethod__.interval is not None,
            cls.get_servicemethods(),
        )

    @classmethod
    @cache
    def get_seed_servicemethods(cls) -> list[callable]:
        return filter(
            lambda servicemethod: servicemethod.__servicemethod__.seed,
            cls.get_servicemethods(),
        )

    router: APIRouter = Field(None, init=False)

    @classmethod
    def url_name(cls) -> str:
        return snakecase(cls.__name__).lstrip("_")

    @classmethod
    def build_router(cls, prefix=None):
        entity_name = cls.url_name()
        prefix = f"/{prefix}/{entity_name}" if prefix is not None else f"/{entity_name}"
        cls.router = APIRouter(prefix=prefix)

        cls._build_static_and_class_method_routes()
        cls._build_regular_method_routes()
        cls._build_list_query_routes()
        cls._build_dict_query_routes()
        cls._build_list_mutate_routes()
        cls._build_dict_mutate_routes()

    @classmethod
    def _build_static_and_class_method_routes(cls):
        static_methods = inspect_mate_pp.get_static_methods(cls)
        class_methods = inspect_mate_pp.get_class_methods(cls)
        for bound_method in static_methods + class_methods:
            route_meta: router.route
            if hasattr(bound_method, "__get_route__") and isinstance(
                route_meta := getattr(bound_method, router.route.__dec_name__),
                router.route,
            ):
                cls.router.api_route(path=route_meta.path)(bound_method)

    @classmethod
    def _build_regular_method_routes(cls):
        regular_methods = inspect_mate_pp.get_regular_methods(cls)
        for bound_method in regular_methods:
            # see if the method has a route_meta: router.route
            route_meta: router.route
            if hasattr(bound_method, "__get_route__") and isinstance(
                route_meta := getattr(bound_method, router.route.__dec_name__),
                router.route,
            ):
                # annotate self with a Annotated[self.__class__, self.__class__.get_by_id]
                # so that fastapi automatically gets the instance from the db
                signature = inspect.signature(bound_method)
                self_arg_name = list(signature.parameters.keys())[0]
                self_arg_annotation = signature.parameters[self_arg_name].annotation
                # see if the annotation is empty annotation
                if self_arg_annotation == inspect._empty:
                    # if it is, set it to the class itself
                    self_arg_annotation = cls
                # now wrap it with a fastapi Depends so that it gets the instance from the db
                new_self_arg_annotation = Annotated[
                    self_arg_annotation, Depends(cls.get_by_id)
                ]

                # now update the exposed signature
                @wraps(bound_method)
                def wrapper(*args, **kwargs):
                    return bound_method(*args, **kwargs)

                wrapper.__signature__ = signature
                wrapper.__annotations__[self_arg_name] = new_self_arg_annotation
                # add new_self_arg_annotation to the signature
                signature.parameters[self_arg_name] = signature.parameters[
                    self_arg_name
                ].replace(annotation=new_self_arg_annotation)

                cls.router.api_route(path=route_meta.path)(wrapper)

    @classmethod
    def _build_list_query_routes(cls):
        for attr, pydantic_field in cls.ReadModel.__fields__.items():
            if issubclass(get_origin(pydantic_field.type_), list):
                # get by index
                T = get_class_list_attr_generic_type(cls, attr)

                @cls.router.get(f"{attr}/{{index}}")
                def get_class_attr_list_by_index(index: int) -> T:
                    return getattr(cls, attr)[index]

                @cls.router.get(f"{{id}}/{attr}/{{index}}")
                def get_instance_attr_list_by_index(id: UUID4, index: int) -> T:
                    return getattr(cls.get_by_id(id), attr)[index]

                # get by slice
                @cls.router.get(f"{attr}/{{start}}:{{stop}}:{{step}}")
                def get_class__attrlist_by_slice(
                    start: int, stop: int, step: int
                ) -> list[T]:
                    return getattr(cls, attr)[start:stop:step]

                @cls.router.get(f"{{id}}/{attr}/{{start}}:{{stop}}:{{step}}")
                def get_instance_attr_list_by_slice(
                    id: UUID4, start: int, stop: int, step: int
                ) -> list[T]:
                    return getattr(cls.get_by_id(id), attr)[start:stop:step]

    @classmethod
    def _build_dict_query_routes(cls):
        for attr, pydantic_field in cls.ReadModel.__fields__.items():
            if issubclass(get_origin(pydantic_field.type_), dict):
                Tkey, Tvalue = get_class_dict_attr_generic_types(cls, attr)
                # get by key

                @cls.router.get(f"{attr}/{{key}}")
                def get_class_attr_dict_by_key(key: Tkey) -> Tvalue:
                    return getattr(cls, attr)[key]

                @cls.router.get(f"{{id}}/{attr}/{{key}}")
                def get_instance_attr_dict_by_key(id: UUID4, key: Tkey) -> Tvalue:
                    return getattr(cls.get_by_id(id), attr)[key]

    @classmethod
    def _build_list_mutate_routes(cls):
        for attr, pydantic_field in cls.UpdateModel.__fields__.items():
            if issubclass(get_origin(pydantic_field.type_), list):
                T = get_class_list_attr_generic_type(cls, attr)

                # set by index
                @cls.router.post(f"{attr}/{{index}}")
                def set_class_attr_list_by_index(index: int, value: T):
                    getattr(cls, attr)[index] = value

                @cls.router.post(f"{{id}}/{attr}/{{index}}")
                def set_instance_attr_list_by_index(id: UUID4, index: int, value: T):
                    getattr(cls.get_by_id(id), attr)[index] = value

                # set by slice
                @cls.router.post(f"{attr}/{{start}}:{{stop}}:{{step}}")
                def set_class_attr_list_by_slice(
                    start: int, stop: int, step: int, value: T
                ):
                    getattr(cls, attr)[start:stop:step] = value

                @cls.router.post(f"{{id}}/{attr}/{{start}}:{{stop}}:{{step}}")
                def set_instance_attr_list_by_slice(
                    id: UUID4, start: int, stop: int, step: int, values: list[T]
                ):
                    getattr(cls.get_by_id(id), attr)[start:stop:step] = values

                # append
                @cls.router.put(f"{attr}/")
                @cls.router.post(f"{attr}/append")
                def append_to_class_attr_list(value: T):
                    getattr(cls, attr).append(value)

                @cls.router.put(f"{{id}}/{attr}/")
                @cls.router.post(f"{{id}}/{attr}/append")
                def append_to_instance_attr_list(id: UUID4, value: T):
                    getattr(cls.get_by_id(id), attr).append(value)

                # extend
                @cls.router.post(f"{attr}/extend")
                def extend_class_attr_list(values: list[T]):
                    getattr(cls, attr).extend(values)

                @cls.router.post(f"{{id}}/{attr}/extend")
                def extend_instance_attr_list(id: UUID4, values: list[T]):
                    getattr(cls.get_by_id(id), attr).extend(values)

                # insert
                @cls.router.post(f"{attr}/insert")
                def insert_into_class_attr_list(index: int, value: T):
                    getattr(cls, attr).insert(index, value)

                @cls.router.post(f"{{id}}/{attr}/insert")
                def insert_into_instance_attr_list(id: UUID4, index: int, value: T):
                    getattr(cls.get_by_id(id), attr).insert(index, value)

                # pop
                @cls.router.post(f"{attr}/pop")
                def pop_from_class_attr_list(index: int) -> T:
                    return getattr(cls, attr).pop(index)

                @cls.router.post(f"{{id}}/{attr}/pop")
                def pop_from_instance_attr_list(id: UUID4, index: int) -> T:
                    return getattr(cls.get_by_id(id), attr).pop(index)

                # remove
                @cls.router.post(f"{attr}/remove")
                def remove_from_class_attr_list(value: T):
                    getattr(cls, attr).remove(value)

                @cls.router.post(f"{{id}}/{attr}/remove")
                def remove_from_instance_attr_list(id: UUID4, value: T):
                    getattr(cls.get_by_id(id), attr).remove(value)

    @classmethod
    def _build_dict_mutate_routes(cls):
        for attr, pydantic_field in cls.ReadModel.__fields__.items():
            if issubclass(get_origin(pydantic_field.type_), dict):
                Tkey, Tvalue = get_class_dict_attr_generic_types(cls, attr)

                # set by key
                @cls.router.api_route(f"{attr}/{{key}}", methods=["put", "post"])
                def set_instance_attr_dict_by_key(key: Tkey, value: Tvalue):
                    getattr(cls, attr)[key] = value

                @cls.router.api_route(f"{{id}}/{attr}/{{key}}", methods=["put", "post"])
                def set_instance_attr_dict_by_key(id: UUID4, key: Tkey, value: Tvalue):
                    getattr(cls.get_by_id(id), attr)[key] = value

                # pop
                @cls.router.post(f"{attr}/pop/{{key}}")
                def pop_from_class_attr_dict(key: Tkey) -> Tvalue:
                    return getattr(cls, attr).pop(key)

                @cls.router.post(f"{{id}}/{attr}/pop/{{key}}")
                def pop_from_class_attr_dict(id: UUID4, key: Tkey) -> Tvalue:
                    return getattr(cls.get_by_id(id), attr).pop(key)

                # clear
                @cls.router.post(f"{attr}/clear")
                def clear_class_attr_dict():
                    getattr(cls, attr).clear()

                @cls.router.post(f"{{id}}/{attr}/clear")
                def clear_class_attr_dict(id: UUID4):
                    getattr(cls.get_by_id(id), attr).clear()


# TODO: split the base entity in a Entity aspect, a API aspect, and a Service aspect
