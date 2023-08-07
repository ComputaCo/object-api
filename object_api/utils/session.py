from functools import wraps
import inspect
from object_api.app import App


def managed_session(func):
    # assert 'session' is in the signature
    assert "session" in inspect.signature(func).parameters

    @wraps(func)
    async def wrapper(*args, **kwargs):
        async with App.CURRENT_APP.session() as session:
            return await func(*args, **kwargs, session=session)

    # remove session from the signature
    sig = inspect.signature(wrapper)
    params = list(sig.parameters.values())
    params = [p for p in params if p.name != "session"]
    sig = sig.replace(parameters=params)
    wrapper.__signature__ = sig

    return wrapper
