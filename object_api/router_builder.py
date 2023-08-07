from __future__ import annotations

import inspect
from functools import wraps
from typing import Annotated, Any, Generic, TypeVar

import inspect_mate_pp
from stringcase import snakecase
from pydantic import UUID4, BaseModel, Field
from fastapi import APIRouter

from object_api.entity import Entity
from object_api.utils.python import (
    MultiSet,
    attr_is_dict,
    attr_is_list,
    get_class_attr_type,
    get_class_dict_attr_generic_types,
    get_class_list_attr_generic_type,
)

T = TypeVar("T", bound=Entity)


class RouterBuilder(Generic[T], BaseModel):
    """
    Used for extracting API methods from a class, inline with the class definition.
    Shared by all instances of the class, so doesn't store any instance-specific data.
    """

    ## Parent routers

    parent_routers: set[RouterBuilder] = Field(default_factory=set, init=False)

    @classmethod
    def child(self):
        child = self.copy(deep=True)
        child.parent_routers.add(self)
        return child

    ## Proto API routes

    class ProtoAPIRoute(BaseModel):
        subpath: str
        methods: list[str]
        handler_name: str

    _proto_api_routes: set[ProtoAPIRoute] = Field(default_factory=set)

    @property
    def proto_api_routes(self) -> set[ProtoAPIRoute]:
        return MultiSet(
            self._proto_api_routes, *[r.proto_api_routes for r in self.parent_routers]
        )

    def route(self, subpath=None, http_methods=["post"]):
        def wrapper(func):
            self.proto_api_routes.add(
                RouterBuilder.ProtoAPIRoute(
                    subpath=subpath or func.__name__,
                    methods=http_methods,
                    handler_name=func.__name__,
                )
            )
            return func

        return wrapper

    def get(self, subpath=None):
        return self.api_route(subpath=subpath, http_methods=["get"])

    def post(self, subpath=None):
        return self.api_route(subpath=subpath, http_methods=["post"])

    def put(self, subpath=None):
        return self.api_route(subpath=subpath, http_methods=["put"])

    def delete(self, subpath=None):
        return self.api_route(subpath=subpath, http_methods=["delete"])

    def patch(self, subpath=None):
        return self.api_route(subpath=subpath, http_methods=["patch"])

    def options(self, subpath=None):
        return self.api_route(subpath=subpath, http_methods=["options"])

    def head(self, subpath=None):
        return self.api_route(subpath=subpath, http_methods=["head"])

    ## Query vars

    _class_can_query_vars: set[str] = Field(default_factory=set)

    def class_can_query_vars(self) -> set[str]:
        return MultiSet(
            self._class_can_query_vars,
            *[r.can_query_vars for r in self.parent_routers],
        )

    _instance_can_query_vars: set[str] = Field(default_factory=set)

    def instance_can_query_vars(self) -> set[str]:
        return MultiSet(
            self._instance_can_query_vars,
            *[r.can_query_vars for r in self.parent_routers],
        )

    def can_query(self, *attr_names: list[str], instance=True, cls=False):
        if instance:
            self.instance_can_query_vars.update(attr_names)
        if cls:
            self.class_can_query_vars.update(attr_names)

    ## Mutate vars

    _class_can_mutate_vars: set[str] = Field(default_factory=set)

    def class_can_mutate_vars(self) -> set[str]:
        return MultiSet(
            self._class_can_mutate_vars,
            *[r.can_query_vars for r in self.parent_routers],
        )

    _instance_can_mutate_vars: set[str] = Field(default_factory=set)

    def instance_can_mutate_vars(self) -> set[str]:
        return MultiSet(
            self._instance_can_mutate_vars,
            *[r.can_query_vars for r in self.parent_routers],
        )

    def can_mutate(self, *attr_names: list[str], instance=True, cls=False):
        if instance:
            self.instance_can_mutate_vars.update(attr_names)
        if cls:
            self.class_can_mutate_vars.update(attr_names)

    router: APIRouter = Field(None, init=False)

    def build_router(self, entity_class: type[T], prefix: str = None) -> APIRouter:
        """Should be called by Entity.__init_subclass__ to build a router for the subclass."""

        # Get all parent routers from the entity_class.Meta.parent and assign them to self.parent_routers
        # This way the router will inherit all the routes from the parent routers
        # 1. Get all parents of entity_class up to Entity
        parents = inspect.getmro(entity_class)
        parents = filter(lambda p: issubclass(p, Entity), parents)
        parents = parents[: parents.index(Entity) + 1]
        # 2. Get the router from each parent
        parent_routers = map(lambda p: p.Meta.router, parents)
        # 3. Assign them to self.parent_routers
        self.parent_routers.update(parent_routers)

        entity_name = snakecase(entity_class.__name__).lstrip("_")
        prefix = f"/{prefix}/{entity_name}" if prefix is not None else f"/{entity_name}"
        self.router = APIRouter(prefix=prefix)

        self._build_method_api_routes(entity_class)
        self._build_query_routes(entity_class)
        self._build_list_query_routes(entity_class)
        self._build_dict_query_routes(entity_class)
        self._build_mutate_routes(entity_class)
        self._build_list_mutate_routes(entity_class)
        self._build_dict_mutate_routes(entity_class)

    def _build_method_api_routes(self, entity_class: type[T]):
        for route in self.proto_api_routes:
            bound_method = getattr(entity_class, route.handler_name)

            # if its a class/static method, the client doesn't care about the first arg
            if inspect_mate_pp.is_static_method(entity_class, route.handler_name):
                handler = bound_method
            elif inspect_mate_pp.is_class_method(entity_class, route.handler_name):
                handler = bound_method
            # see if func is an instance method
            elif inspect_mate_pp.is_regular_method(entity_class, route.handler_name):
                # if so, we'll annotate the bound arg with a `get_by_id` fastapi dependency
                unbound_method = bound_method.__func__

                @wraps(unbound_method)
                def wrapper(*args, **kwargs):
                    return unbound_method(*args, **kwargs)

                params = list(inspect.signature(unbound_method).parameters.values())
                params[1] = inspect.Parameter(
                    params[1].name,
                    params[1].kind,
                    default=params[1].default,
                    annotation=Annotated[Entity, Entity.get_by_id],
                )
                wrapper.__signature__ = inspect.signature(unbound_method).replace(
                    parameters=params
                )

                # now we have a bound method-like function that we can add to the router
                handler = wrapper

            self.router.add_api_route(
                path=f"{route.subpath}",
                methods=route.methods,
                endpoint=handler,
            )

    def _build_query_routes(self, entity_class: type[T]):
        # query class attr
        for attr in self.class_can_query_vars:
            T = get_class_attr_type(entity_class, attr)

            @self.router.get(f"{attr}")
            def query_class_attr() -> T:
                return getattr(entity_class, attr)

        # query instance attr
        for attr in self.instance_can_query_vars:
            T = get_class_attr_type(entity_class, attr)

            @self.router.get(f"{{id}}/{attr}")
            def query_instance_attr(id: UUID4) -> T:
                return getattr(entity_class.get_by_id(id), attr)

    def _build_list_query_routes(self, entity_class: type[T]):
        # query class list attr
        for attr in self.class_can_query_vars:
            if attr_is_list(entity_class, attr):
                # get by index
                T = get_class_list_attr_generic_type(entity_class, attr)

                @self.router.get(f"{attr}/{{index}}")
                def get_class_attr_list_by_index(index: int) -> T:
                    return getattr(entity_class, attr)[index]

                # get by slice
                @self.router.get(f"{attr}/{{start}}:{{stop}}:{{step}}")
                def get_class__attrlist_by_slice(
                    start: int, stop: int, step: int
                ) -> list[T]:
                    return getattr(entity_class, attr)[start:stop:step]

        # query instance list attr
        for attr in self.instance_can_query_vars:
            if attr_is_list(entity_class, attr):
                # get by index
                T = get_class_list_attr_generic_type(entity_class, attr)

                @self.router.get(f"{{id}}/{attr}/{{index}}")
                def get_instance_attr_list_by_index(id: UUID4, index: int) -> T:
                    return getattr(entity_class.get_by_id(id), attr)[index]

                # get by slice
                @self.router.get(f"{{id}}/{attr}/{{start}}:{{stop}}:{{step}}")
                def get_instance_attr_list_by_slice(
                    id: UUID4, start: int, stop: int, step: int
                ) -> list[T]:
                    return getattr(entity_class.get_by_id(id), attr)[start:stop:step]

    def _build_dict_query_routes(self, entity_class: type[T]):
        # query class dict attr
        for attr in self.class_can_query_vars:
            if attr_is_dict(entity_class, attr):
                # get by key
                Tkey, Tvalue = get_class_dict_attr_generic_types(entity_class, attr)

                @self.router.get(f"{attr}/{{key}}")
                def get_class_attr_dict_by_key(key: Tkey) -> Tvalue:
                    return getattr(entity_class, attr)[key]

        # query instance dict attr
        for attr in self.instance_can_query_vars:
            if attr_is_dict(entity_class, attr):
                # get by key
                Tkey, Tvalue = get_class_dict_attr_generic_types(entity_class, attr)

                @self.router.get(f"{{id}}/{attr}/{{key}}")
                def get_instance_attr_dict_by_key(id: UUID4, key: Tkey) -> Tvalue:
                    return getattr(entity_class.get_by_id(id), attr)[key]

    def _build_mutate_routes(self, entity_class: type[T]):
        # mutate class attr
        for attr in self.class_can_mutate_vars:
            # set
            @self.router.api_route(f"{attr}", methods=["put", "post"])
            def mutate_class_attr(value: T):
                setattr(entity_class, attr, value)

        # mutate instance attr
        for attr in self.instance_can_mutate_vars:
            # set
            @self.router.api_route(f"{{id}}/{attr}", methods=["put", "post"])
            def mutate_instance_attr(id: UUID4, value: T):
                setattr(entity_class.get_by_id(id), attr, value)

    def _build_list_mutate_routes(self, entity_class: type[T]):
        # mutate class list attr
        for attr in self.class_can_mutate_vars:
            if attr_is_list(entity_class, attr):
                T = get_class_list_attr_generic_type(entity_class, attr)

                # set by index
                @self.router.post(f"{attr}/{{index}}")
                def set_class_attr_list_by_index(index: int, value: T):
                    getattr(entity_class, attr)[index] = value

                # set by slice
                @self.router.post(f"{attr}/{{start}}:{{stop}}:{{step}}")
                def set_class_attr_list_by_slice(
                    start: int, stop: int, step: int, value: T
                ):
                    getattr(entity_class, attr)[start:stop:step] = value

                # append
                @self.router.put(f"{attr}/")
                @self.router.post(f"{attr}/append")
                def append_to_class_attr_list(value: T):
                    getattr(entity_class, attr).append(value)

                # extend
                @self.router.post(f"{attr}/extend")
                def extend_class_attr_list(values: list[T]):
                    getattr(entity_class, attr).extend(values)

                # insert
                @self.router.post(f"{attr}/insert")
                def insert_into_class_attr_list(index: int, value: T):
                    getattr(entity_class, attr).insert(index, value)

                # pop
                @self.router.post(f"{attr}/pop")
                def pop_from_class_attr_list(index: int) -> T:
                    return getattr(entity_class, attr).pop(index)

                # remove
                @self.router.post(f"{attr}/remove")
                def remove_from_class_attr_list(value: T):
                    getattr(entity_class, attr).remove(value)

        # mutate instance list attr
        for attr in self.instance_can_mutate_vars:
            if attr_is_list(entity_class, attr):
                T = get_class_list_attr_generic_type(entity_class, attr)

                # set by index
                @self.router.post(f"{{id}}/{attr}/{{index}}")
                def set_instance_attr_list_by_index(id: UUID4, index: int, value: T):
                    getattr(entity_class.get_by_id(id), attr)[index] = value

                # set by slice
                @self.router.post(f"{{id}}/{attr}/{{start}}:{{stop}}:{{step}}")
                def set_instance_attr_list_by_slice(
                    id: UUID4, start: int, stop: int, step: int, values: list[T]
                ):
                    getattr(entity_class.get_by_id(id), attr)[start:stop:step] = values

                # append
                @self.router.put(f"{{id}}/{attr}/")
                @self.router.post(f"{{id}}/{attr}/append")
                def append_to_instance_attr_list(id: UUID4, value: T):
                    getattr(entity_class.get_by_id(id), attr).append(value)

                # extend
                @self.router.post(f"{{id}}/{attr}/extend")
                def extend_instance_attr_list(id: UUID4, values: list[T]):
                    getattr(entity_class.get_by_id(id), attr).extend(values)

                # insert
                @self.router.post(f"{{id}}/{attr}/insert")
                def insert_into_instance_attr_list(id: UUID4, index: int, value: T):
                    getattr(entity_class.get_by_id(id), attr).insert(index, value)

                # pop
                @self.router.post(f"{{id}}/{attr}/pop")
                def pop_from_instance_attr_list(id: UUID4, index: int) -> T:
                    return getattr(entity_class.get_by_id(id), attr).pop(index)

                # remove
                @self.router.post(f"{{id}}/{attr}/remove")
                def remove_from_instance_attr_list(id: UUID4, value: T):
                    getattr(entity_class.get_by_id(id), attr).remove(value)

    def _build_dict_mutate_routes(self, entity_class: type[T]):
        # mutate class dict attr
        for attr in self.class_can_mutate_vars:
            if attr_is_dict(entity_class, attr):
                Tkey, Tvalue = get_class_dict_attr_generic_types(entity_class, attr)

                # set by key
                @self.router.api_route(f"{attr}/{{key}}", methods=["put", "post"])
                def set_instance_attr_dict_by_key(key: Tkey, value: Tvalue):
                    getattr(entity_class, attr)[key] = value

                # pop
                @self.router.post(f"{attr}/pop/{{key}}")
                def pop_from_class_attr_dict(key: Tkey) -> Tvalue:
                    return getattr(entity_class, attr).pop(key)

                # clear
                @self.router.post(f"{attr}/clear")
                def clear_class_attr_dict():
                    getattr(entity_class, attr).clear()

        # mutate instance dict attr
        for attr in self.instance_can_mutate_vars:
            if attr_is_dict(entity_class, attr):
                Tkey, Tvalue = get_class_dict_attr_generic_types(entity_class, attr)

                # set by key
                @self.router.api_route(
                    f"{{id}}/{attr}/{{key}}", methods=["put", "post"]
                )
                def set_instance_attr_dict_by_key(id: UUID4, key: Tkey, value: Tvalue):
                    getattr(entity_class.get_by_id(id), attr)[key] = value

                # pop
                @self.router.post(f"{{id}}/{attr}/pop/{{key}}")
                def pop_from_class_attr_dict(id: UUID4, key: Tkey) -> Tvalue:
                    return getattr(entity_class.get_by_id(id), attr).pop(key)

                # clear
                @self.router.post(f"{{id}}/{attr}/clear")
                def clear_class_attr_dict(id: UUID4):
                    getattr(entity_class.get_by_id(id), attr).clear()


class FrontendProxyEntityWrapper(Generic[T], BaseModel):
    @classmethod
    def build_from_entity(cls, entity: Entity[T]) -> FrontendProxyEntityWrapper[T]:
        pass  # TODO
