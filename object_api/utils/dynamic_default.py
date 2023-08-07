import functools
import inspect
from typing import Annotated, Any, Callable

from fastapi import Depends


def dynamic_default(
    arg_name: str, default_func: Callable, /, *, make_fastapi_depends=True
):
    def decorator(func):
        # Get the original function's signature
        orig_signature = inspect.signature(func)

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Bind the provided arguments to the original function's signature
            bound_args = orig_signature.bind_partial(*args, **kwargs)
            bound_args.apply_defaults()

            # If the argument isn't provided, get its dynamic default
            if (
                arg_name not in bound_args.arguments
                or bound_args.arguments[arg_name] is None
            ):
                bound_args.arguments[arg_name] = default_func()

            # Call the original function with the potentially updated arguments
            return func(*bound_args.args, **bound_args.kwargs)

        # Update the wrapper's signature to match the original function's
        wrapper.__signature__ = orig_signature

        # get the annotation on the argument
        # if the annotation doesn't exist, then set it to the return type of the default function or Any
        arg_annotation = orig_signature.parameters[arg_name].annotation
        if arg_annotation is inspect._empty:
            arg_annotation = default_func.__annotations__.get("return", Any)
        # now wrap the annotation with a fastapi Depends
        if make_fastapi_depends:
            arg_annotation = Annotated[arg_annotation, Depends(default_func)]
        # set the annotation on the wrapper parameter
        wrapper_signature = inspect.signature(wrapper)
        wrapper_signature.parameters[arg_name] = wrapper_signature.parameters[
            arg_name
        ].replace(annotation=arg_annotation)
        wrapper.__signature__ = wrapper_signature

        return wrapper

    return decorator


# Test
@dynamic_default("arg1", lambda: 1)
def foo(arg0, arg1=None, arg2=None):
    return arg0, arg1, arg2


results = {
    "test1": foo(0, arg2=2),  # fills in the blanks
    "test2": foo(0, 1, 2),  # you can also directly pass
}

results
