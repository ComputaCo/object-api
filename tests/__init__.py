import pytest


def import_entity():
    from object_api.entity import AbstractEntity


def make_entity():
    from object_api.entity import AbstractEntity

    class SubEntity(AbstractEntity):
        pass


def make_entity_with_fields():
    from object_api.entity import AbstractEntity

    class SubEntity(AbstractEntity):
        foo: str
        bar: int


def make_entity_with_meta():
    from object_api.entity import AbstractEntity

    class SubEntity(AbstractEntity):
        class Meta:
            pass

        pass


def make_entity_with_meta_that_subs_base_meta():
    from object_api.entity import AbstractEntity

    class SubEntity(AbstractEntity):
        class Meta(AbstractEntity.Meta):
            pass

        pass


def make_entity_with_private_fields():
    from object_api.entity import AbstractEntity

    class SubEntity(AbstractEntity):
        class Meta:
            new_private_fields = ["foo"]

        foo: str


def import_app():
    from object_api.app import App


def make_app():
    from object_api.app import App

    app = App()


def import_router_builder():
    from object_api.router_builder import RouterBuilder


def make_router_builder():
    from object_api.entity import AbstractEntity
    from object_api.router_builder import RouterBuilder

    class SubEntity(AbstractEntity):
        class Meta:
            router = RouterBuilder()

        pass


def add_route():
    from object_api.entity import AbstractEntity
    from object_api.router_builder import RouterBuilder

    class SubEntity(AbstractEntity):
        class Meta:
            router = RouterBuilder()

        @Meta.router.route()
        def foo(self):
            pass


def build_router():
    from object_api.entity import AbstractEntity
    from object_api.router_builder import RouterBuilder

    class SubEntity(AbstractEntity):
        class Meta:
            router = RouterBuilder()

        @Meta.router.route()
        def foo(self):
            pass

    SubEntity.Meta.router.build_router(SubEntity)


def import_service_builder():
    from object_api.service_builder import ServiceBuilder


def make_service_builder():
    from object_api.entity import AbstractEntity
    from object_api.service_builder import ServiceBuilder

    class SubEntity(AbstractEntity):
        class Meta:
            service = ServiceBuilder()

        pass


def register_service_method():
    from object_api.entity import AbstractEntity
    from object_api.service_builder import ServiceBuilder

    class SubEntity(AbstractEntity):
        class Meta:
            service = ServiceBuilder()

        @Meta.service.servicemethod()
        def foo(self):
            pass


def build_service_builder():
    from object_api.entity import AbstractEntity
    from object_api.service_builder import ServiceBuilder

    class SubEntity(AbstractEntity):
        class Meta:
            service = ServiceBuilder()

        @Meta.service.servicemethod()
        def foo(self):
            pass

    SubEntity.Meta.service.build_services(SubEntity)
