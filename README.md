# The Object API

ObjectAPI provides a concise negative-boilerplate paradigm for creating full-stack web applications with Python. It is built on top of [FastAPI](https://fastapi.tiangolo.com/), [SQLModel](https://sqlmodel.tiangolo.com/), and [pydantic](https://docs.pydantic.dev/latest/).

## Features

- Active record pattern for database access
- Automatic get_by_id lookup for instance methods with route decorators
- Automatic CRUD routes
- Scheduled service methods
- Managed DB sessions for service methods and for each request
- `__post_init__` for entity classes

## Installation

```bash
pip install object-api
```

## Usage

```python
from object_api.entity import Entity
from object_api.app import App
from object_api.model_variants import (
    create_variant,
    read_variant,
    update_variant,
    db_variant,
)
from object_api import router
from object_api.router import route, get, post, put, delete, patch, head, options
from object_api.servicemethod import servicemethod
```


```python
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
    servicemethod
)


@create_variant()
@read_variant()
@update_variant()
@db_variant(include=["passwd_hash"])
class User(Entity):
    name: str
    passwd_hash: str = Field(exclude=True)
    birthdate: datetime
    
    @property
    def age(self) -> timedelta:
        return datetime.now() - self.birthdate


class User(Entity):

    name: str
    pass: str
    age: int

    @service.servicemethod
    @classmethod
    def remove_inactive(cls):
        for user in User.get_all():
            if user.age > 100:
                user.delete()
    
    @router.route()
    def get_name(self):
        return self.name

    @router.post("/change_name")
    def change_name(self, name: str):
        self.name = name
        self.save()

app = App()

app.run()
```

## Documentation

<https://github.com/ComputaCo/object-api>

## Roadmap

[] Make the Create/Read/UpdateModel's automatically convert foreign lists/dicts to just their ID's

## License

[MIT](https://choosealicense.com/licenses/mit/)
