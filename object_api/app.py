from __future__ import annotations

from contextlib import asynccontextmanager, contextmanager
from typing import Generator

from sqlalchemy.future.engine import Engine
from sqlmodel import SQLModel, Session, create_engine
from pydantic import Field
from fastapi import FastAPI
from scheduler import Scheduler

from object_api.entity import Entity
from object_api.request_context import RequestContextMiddleware, get_request_id
from object_api.utils.has_post_init import HasPostInitMixin


class App(FastAPI, HasPostInitMixin):
    CURRENT_APP: App = Field(None, init=False)

    scheduler: Scheduler = Field(
        default_factory=lambda: Scheduler(n_threads=0), init=False
    )
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

        self.add_middleware(RequestContextMiddleware)
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

    # The servicemethods will just have to manually pass the session to their invoked service methods
    _per_thread_active_session: dict[str, Session] = Field(None, init=False)

    @asynccontextmanager
    async def session(self) -> Generator[None, None, None]:
        """Returns (and possibly creates) a session for the current req-response cycle
        or returns a globally shared session if no request context is available."""
        req_id = get_request_id() or "global"

        # maybe create or re-initialize the session if its non-existent or inactive
        if (
            req_id not in self._per_thread_active_session
            or not self._per_thread_active_session[req_id]
            or not self._per_thread_active_session[req_id].is_active
        ):
            self._per_thread_active_session[req_id] = Session(self.db_engine)

        # now enter the session context or just yield the session if it's already active
        if self._per_thread_active_session[req_id].is_active:
            yield self._per_thread_active_session[req_id]
            return
        else:
            with self._per_thread_active_session[req_id] as session:
                yield session
            # make sure to clean up the session after the request is done
            del self._per_thread_active_session[req_id]
            return

    @asynccontextmanager
    @staticmethod
    async def current_session() -> Generator[Session, None, None]:
        if not App.CURRENT_APP:
            raise RuntimeError(
                "No current app. Please use App.as_current() to set the current app."
            )

        yield App.CURRENT_APP.session()

    @asynccontextmanager
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
