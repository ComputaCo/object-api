from datetime import timedelta
from exports import export

from pydantic import Field
from scheduler.threading.job import Job

from object_api.app import App
from object_api.utils.decorator import decorator


@export
class servicemethod(decorator):
    __dec_name__: str = "__servicemethod__"

    startup: bool = False
    shutdown: bool = False
    interval: timedelta or None = None
    seed: bool = False

    last_executed: timedelta or None = Field(None, init=False)
    app: App = Field(None, init=False)
    scheduler_job: Job = Field(None, init=False)
