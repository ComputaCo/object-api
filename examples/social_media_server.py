from __future__ import annotations

from datetime import datetime, timedelta
from typing import Self

from pydantic import UUID4, Field
from sqlmodel import Session
from object_api import (
    App,
    Entity,
    create_variant,
    read_variant,
    update_variant,
    db_variant,
    router,
    route,
    get,
    post,
    put,
    delete,
    patch,
    head,
    options,
    servicemethod,
)
from object_api.utils.dynamic_default import dynamic_default


@create_variant()
@read_variant()
@update_variant()
@db_variant(include=["passwd_hash"])
class User(Entity):
    name: str
    birthdate: datetime

    class DBModel(Entity.DBModel):
        passwd_hash: str = Field(exclude=True)
        login_ids: list[UUID4]

    @property
    def logins(self) -> list[Login]:
        return Login.get_by_ids(self.get_db_model().login_ids)

    @property
    def most_recent_login(self) -> Login:
        return max(self.logins, key=lambda login: login.timestamp)

    @property
    def time_since_last_login(self) -> timedelta:
        return datetime.now() - self.most_recent_login.timestamp

    @property
    def age(self) -> timedelta:
        return datetime.now() - self.birthdate

    MINIMUM_USER_AGE = Field(timedelta(days=13 * 365.25), exclude=True)

    @router.post("")
    @dynamic_default("db_session", App.current_db_session)
    @classmethod
    def create(cls, args: Entity.CreateModel, *, db_session: Session = None) -> Self:
        if args.birthdate > datetime.now() - cls.MINIMUM_USER_AGE:
            raise ValueError("User is too young to use this service")
        return super().create(args, db_session=db_session)

    USER_RETENTION_PERIOD = Field(timedelta(days=365), exclude=True)

    @servicemethod(interval=timedelta(days=1))
    @classmethod
    def remove_inactive_users(cls) -> None:
        for user in cls.objects:
            if user.time_since_last_login > cls.USER_RETENTION_PERIOD:
                user.delete()


@create_variant()
@read_variant()
@update_variant(exclude=["token"])
@db_variant(exclude=[])
class Login(Entity):
    user_id: UUID4
    timestamp: datetime
    token: str

    @property
    def user(self) -> User:
        return User.get_by_id(self.user_id)


app = App()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
