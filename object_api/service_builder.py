from __future__ import annotations

from datetime import datetime, timedelta
from functools import wraps
import inspect
from typing import Generator

from scheduler import Scheduler
from scheduler.threading.job import Job
from pydantic import BaseModel
import inspect_mate_pp
from sqlmodel import Field, SQLModel
from object_api.app import App

from object_api.entity import Entity
from object_api.utils.python import Decorator, MultiList


class ServiceBuilder:
    class ProtoServiceMethod(SQLModel):
        method_name: str
        startup: bool = False
        shutdown: bool = False
        interval: timedelta or None = None
        last_executed: timedelta or None = Field(None, init=False)
        app: App = Field(None, init=False)
        scheduler_job: Job = Field(None, init=False)

    parent_service_builders: list[ServiceBuilder] = []

    _servicemethod_protos: list[ProtoServiceMethod] = []

    @property
    def servicemethod_protos(self) -> list[ProtoServiceMethod]:
        return MultiList(
            self._servicemethod_protos,
            *(p.servicemethod_protos for p in self.parent_service_builders),
        )

    def servicemethod(
        self,
        *,
        startup: bool = False,
        shutdown: bool = False,
        interval: timedelta or None = None,
    ) -> Decorator:
        def wrapper(method):
            servicemethod_meta = self.ProtoServiceMethod(
                method_name=method.__name__,
                startup=startup,
                shutdown=shutdown,
                interval=interval,
            )
            self.servicemethod_protos.append(servicemethod_meta)

            @wraps(method)
            def wrapper(*args, **kwargs):
                with App.CURRENT_APP.session() as session:
                    return method(*args, **kwargs)

            # assign meta
            setattr(wrapper, "__servicemethod_meta__,", servicemethod_meta)

            return method

        return wrapper

    @property
    def servicemethods(self, entity_class: type[Entity]) -> list[callable]:
        return [
            getattr(entity_class, servicemethod_proto.method_name)
            for servicemethod_proto in self.servicemethod_protos
        ]

    def build_services(self, entity_class: type[Entity]):
        """Prepares services for the subclass."""

        # Get all parent service builders from the entity_class.Meta.parent and
        # assign them to self.parent_service_builders
        # This way the router will inherit all the routes from the parent routers
        # 1. Get all parents of entity_class up to Entity
        parents = inspect.getmro(entity_class)
        parents = filter(lambda p: issubclass(p, Entity), parents)
        parents = parents[: parents.index(Entity) + 1]
        # 2. Get the service_builder from each parent
        parents = filter(lambda p: hasattr(p, "Meta"), parents)
        parents = filter(lambda p: hasattr(p.Meta, "service"), parents)
        parent_service_builders = map(lambda p: p.Meta.router, parents)
        # 3. Assign them to self.parent_service_builders
        self.parent_service_builders.update(parent_service_builders)

        for servicemethod in self.servicemethods(entity_class):
            # make sure the methods are static or class methods
            if not inspect_mate_pp.is_class_method(
                entity_class, servicemethod.__name__
            ) or not inspect_mate_pp.is_static_method(
                entity_class, servicemethod.__name__
            ):
                raise RuntimeError(
                    f"Service methods must be static methods or class methods but {servicemethod} is not."
                )
            # make sure the bound methods have 0 arguments
            if inspect.signature(servicemethod).parameters != 0:
                raise RuntimeError(
                    f"Service methods must have 0 arguments but {servicemethod} does not."
                )
            # yay! this is a valid service method
            servicemethod.__servicemethod_meta__.app = App.CURRENT_APP
            continue

    def all_startup_servicemethods(
        self, entity_class: type[Entity]
    ) -> Generator[callable, None, None]:
        return filter(
            lambda m: m.__servicemethod_meta__.startup,
            self.servicemethods(entity_class),
        )

    def all_shutdown_servicemethods(
        self, entity_class: type[Entity]
    ) -> Generator[callable, None, None]:
        return filter(
            lambda m: m.__servicemethod_meta__.shutdown,
            self.servicemethods(entity_class),
        )

    def all_interval_servicemethods(
        self, entity_class: type[Entity]
    ) -> Generator[callable, None, None]:
        return filter(
            lambda m: m.__servicemethod_meta__.interval,
            self.servicemethods(entity_class),
        )

    def start_service(self, entity_class: type[Entity]):
        self.start_servicemethods(entity_class)
        self.start_interval_servicemethod_scheduler(entity_class)

    def stop_service(self, entity_class: type[Entity]):
        self.stop_servicemethods(entity_class)
        self.stop_interval_servicemethod_scheduler(entity_class)

    def start_servicemethods(self, entity_class: type[Entity]):
        for servicemethod in self.all_startup_servicemethods(entity_class):
            servicemethod()

    def stop_servicemethods(self, entity_class: type[Entity]):
        for servicemethod in self.all_shutdown_servicemethods(entity_class):
            servicemethod()

    def start_interval_servicemethod_scheduler(self, entity_class: type[Entity]):
        for servicemethod in self.all_interval_servicemethods(entity_class):
            servicemethod.__servicemethod_meta__.last_executed = datetime.now()
            job = App.CURRENT_APP.scheduler.cyclic(
                servicemethod.__servicemethod_meta__.interval, servicemethod
            )
            servicemethod.__servicemethod_meta__.scheduler_job = job

    def stop_interval_servicemethod_scheduler(self, entity_class: type[Entity]):
        for servicemethod in self.all_interval_servicemethods(entity_class):
            App.CURRENT_APP.scheduler.delete_job(
                servicemethod.__servicemethod_meta__.scheduler_job
            )
