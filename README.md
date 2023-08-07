# The Object API

ObjectAPI provides a concise negative-boilerplate paradigm for creating full-stack web applications with Python. It is built on top of [FastAPI](https://fastapi.tiangolo.com/), [SQLModel](https://sqlmodel.tiangolo.com/), and [pydantic](https://docs.pydantic.dev/latest/).

## Features

- Active record pattern for database access
- Automatic get_by_id lookup for instance methods with route decorators
- Automatic CRUD routes
- Scheduled service methods
- Managed DB sessions for service methods and for each request

## Installation

```bash
pip install object-api
```

## Usage

```python
from object_api import App, Entity, RouterBuilder, ServiceBuilder

app = App()

class User(Entity):
    class Meta:
        service = ServiceBuilder()
        router = RouterBuilder()

        new_private = ["pass"]

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

## License

[MIT](https://choosealicense.com/licenses/mit/)
