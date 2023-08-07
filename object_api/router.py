from datetime import timedelta

from exports import export

from object_api.utils.decorator import decorator


@export
class route(decorator):
    __dec_name__: str = "__get_route__"

    path: str or None = None


@export
class get(route):
    __dec_name__: str = "__get_get__"

    path: str or None = None


@export
class post(route):
    __dec_name__: str = "__get_post__"

    path: str or None = None


@export
class put(route):
    __dec_name__: str = "__get_put__"

    path: str or None = None


@export
class delete(route):
    __dec_name__: str = "__get_delete__"

    path: str or None = None


class patch(route):
    __dec_name__: str = "__get_patch__"

    path: str or None = None


@export
class head(route):
    __dec_name__: str = "__get_head__"

    path: str or None = None


@export
class options(route):
    __dec_name__: str = "__get_options__"

    path: str or None = None
