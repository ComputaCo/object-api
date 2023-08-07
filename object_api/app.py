from __future__ import annotations
import asyncio

from contextlib import asynccontextmanager, contextmanager
from typing import Generator
from exports import export

from sqlalchemy.future.engine import Engine
from sqlmodel import SQLModel, Session, create_engine
from pydantic import Field
from fastapi import FastAPI
from scheduler import Scheduler

from object_api.entity import AbstractEntity, Entity
from object_api.utils.python import subclasses_recursive
from object_api.utils.request_context import RequestContextMiddleware, get_request_id
from object_api.utils.has_post_init import HasPostInitMixin


@export
class App(FastAPI, HasPostInitMixin):
    # Class-level semaphore to ensure only one instance is current at a time
    _semaphore = Field(asyncio.Semaphore(1), init=False, exclude=True)
    CURRENT_APP: App = Field(None, init=False, exclude=True)

    scheduler: Scheduler = Field(
        default_factory=lambda: Scheduler(n_threads=0), init=False
    )
    get_entity_classes: list[type[AbstractEntity]] = Field([], init=False)
    db_engine: Engine = Field(None, init=False)
    debug: bool = True

    async def __post_init__(self):
        if not self.db_engine:
            sqlite_file_name = "database.db"
            sqlite_url = f"sqlite:///{sqlite_file_name}"
            connect_args = {"check_same_thread": False}
            self.db_engine = create_engine(
                sqlite_url, echo=self.debug, connect_args=connect_args
            )

        # Wait until the semaphore is available
        # Create an event loop
        loop = asyncio.get_event_loop()
        # Use the loop to run the async function
        loop.run_until_complete(self._semaphore.acquire())
        # Close the loop
        loop.close()
        # Now set the CURRENT_APP, but do not acquire the semaphore
        # since this is just something that happens by default
        self.CURRENT_APP = self

        self.add_middleware(RequestContextMiddleware)
        self.build()

        self.on_event("startup")(self.start)
        self.on_event("shutdown")(self.stop)

        return super().__post_init__()

    @classmethod
    def get_entity_classes(cls) -> list[type[Entity]]:
        return subclasses_recursive(Entity)

    # The servicemethods will just have to manually pass the session to their invoked service methods
    _per_thread_active_db_session: dict[str, Session] = Field(None, init=False)

    @asynccontextmanager
    async def db_session(self) -> Generator[None, None, None]:
        """Returns (and possibly creates) a session for the current req-response cycle
        or returns a globally shared session if no request context is available."""
        req_id = get_request_id() or "global"

        # maybe create or re-initialize the session if its non-existent or inactive
        if (
            req_id not in self._per_thread_active_db_session
            or not self._per_thread_active_db_session[req_id]
            or not self._per_thread_active_db_session[req_id].is_active
        ):
            self._per_thread_active_db_session[req_id] = Session(self.db_engine)

        # now enter the session context or just yield the session if it's already active
        if self._per_thread_active_db_session[req_id].is_active:
            yield self._per_thread_active_db_session[req_id]
            return
        else:
            with self._per_thread_active_db_session[req_id] as session:
                yield session
            # make sure to clean up the session after the request is done
            del self._per_thread_active_db_session[req_id]
            return

    @asynccontextmanager
    @staticmethod
    async def current_db_session() -> Generator[Session, None, None]:
        if not App.CURRENT_APP:
            raise RuntimeError(
                "No current app. Please use App.as_current() to set the current app."
            )

        yield App.CURRENT_APP.db_session()

    @asynccontextmanager
    async def as_current(self) -> Generator["App", None, None]:
        # Wait until the semaphore is available
        await self._semaphore.acquire()

        # Set this instance as the current app
        old_app = self.CURRENT_APP
        self.CURRENT_APP = self

        try:
            yield self
        finally:
            # Restore the previous value and release the semaphore
            self.CURRENT_APP = old_app
            self._semaphore.release()

    _built = Field(False, init=False)

    def build(self):
        self.create_db_and_tables()
        self.build_services()
        self.build_routers()

    def create_db_and_tables(self):
        SQLModel.metadata.create_all(self.db_engine)

    def build_services(self):
        for entity_class in self.get_entity_classes():
            entity_class.build_servicemethods()

    def build_routers(self):
        for entity_class in self.get_entity_classes():
            entity_class.build_router()
            self.mount(entity_class.url_name, entity_class.router)

    def start(self):
        if self._built:
            self.build()
        self.start_services()

    def stop(self):
        self.stop_services()

    def start_services(self):
        for entity_class in self.get_entity_classes():
            entity_class.start_services(entity_class)

    def stop_services(self):
        for entity_class in self.get_entity_classes():
            entity_class.stop_services(entity_class)
