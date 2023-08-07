from __future__ import annotations
from contextlib import contextmanager
from typing import Generator
from fastapi import FastAPI
from pydantic import Field
from sqlalchemy.future.engine import Engine

from scheduler import Scheduler
from sqlmodel import SQLModel, Session, create_engine

from object_api.entity import Entity
from object_api.utils.has_post_init import HasPostInitMixin


class App(FastAPI, HasPostInitMixin):
    CURRENT_APP: App = Field(None, init=False)

    scheduler: Scheduler = Field(default_factory=Scheduler, init=False)
    entity_classes: list[type[Entity]] = Field([], init=False)
    db_engine: Engine = Field(None, init=False)
    debug: bool = True

    def __post_init__(self):
        if not self.db_engine:
            sqlite_file_name = "database.db"
            sqlite_url = f"sqlite:///{sqlite_file_name}"
            connect_args = {"check_same_thread": False}
            self.db_engine = create_engine(
                sqlite_url, echo=self.debug, connect_args=connect_args
            )
        self.CURRENT_APP = self

        self.build()

        return super().__post_init__()

    def build(self):
        self.create_db_and_tables()
        self.build_services()
        self.build_routers()

    def create_db_and_tables(self):
        SQLModel.metadata.create_all(self.db_engine)

    def build_services(self):
        for entity_class in self.entity_classes:
            entity_class.Meta.service.build_services(entity_class)

    def build_routers(self):
        for entity_class in self.entity_classes:
            entity_class.Meta.router.build_router(entity_class)

    _object_api_app_active_session: Session = Field(None, init=False)

    @contextmanager
    async def session(self) -> Generator[None, None, None]:
        if self._object_api_app_active_session:
            if not self._object_api_app_active_session.is_active:
                raise RuntimeError(
                    "Session is already closed. Please use a new session for each request."
                )

            yield self._object_api_app_active_session
            return

        with Session(self.db_engine) as session:
            self._object_api_app_active_session = session
            yield session
            self._object_api_app_active_session = None

    @contextmanager
    async def as_current(self) -> Generator[App, None, None]:
        old_app = self.CURRENT_APP
        self.CURRENT_APP = self
        yield
        self.CURRENT_APP = old_app

    def start(self):
        self.start_services()

    def stop(self):
        self.stop_services()

    def start_services(self):
        for entity_class in self.entity_classes:
            if entity_class.Meta.service:
                entity_class.Meta.service.start_service(entity_class)

    def stop_services(self):
        for entity_class in self.entity_classes:
            if entity_class.Meta.service:
                entity_class.Meta.service.stop_service(entity_class)
