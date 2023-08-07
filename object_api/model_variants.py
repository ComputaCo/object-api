from typing import Any, Generic, Iterable, TypeVar
from exports import export

from pydantic import BaseModel
from sqlmodel import Field, SQLModel

from object_api.entity import AbstractEntity
from object_api.utils.python import get_in_classes

T = TypeVar("T")


class VariantModelBase(Generic[T], BaseModel):
    pass


class CreateModelBase(Generic[T], VariantModelBase[T]):
    pass


class ReadModelBase(Generic[T], VariantModelBase[T]):
    pass


class UpdateModelBase(Generic[T], VariantModelBase[T]):
    pass


class DBModelBase(Generic[T], VariantModelBase[T], SQLModel, table=False):
    pass


def make_variant(
    base,
    variant_attr_name: str,
    variant_type: type[VariantModelBase],
    include: Iterable[str] = None,
    exclude: Iterable[str] = None,
) -> VariantModelBase:
    parent_variants = [
        getattr(v, variant_attr_name)
        for v in base.__bases__
        if issubclass(v, VariantModelBase)
    ]

    inherited_variant_fields = set(*(v.__fields__ for v in parent_variants))
    new_fields = set(base.__fields__)

    # then apply the BaseModel.__include_fields__ and BaseModel.__exclude_fields__
    if hasattr(base, "__include_fields__") and getattr(base, "__include_fields__"):
        base_include_fields = {k for k, v in base.__include_fields__.items() if v}
        new_fields = new_fields & base_include_fields
    if hasattr(base, "__exclude_fields__") and getattr(base, "__exclude_fields__"):
        base_exclude_fields = {k for k, v in base.__exclude_fields__.items() if v}
        new_fields = new_fields - base_exclude_fields

    fields: set[str]

    match include, exclude:
        case None, None:
            fields = inherited_variant_fields | new_fields
        case None, _:
            fields = inherited_variant_fields | new_fields - set(exclude)
        case _, None:
            fields = inherited_variant_fields | set(include)
        case _, _:
            fields = inherited_variant_fields | set(include) - set(exclude)

    variant_on_base = getattr(base, variant_attr_name)
    bases = (base, *parent_variants, variant_on_base)
    field_values = dict()
    field_types = dict()
    for field_name in fields:
        # if its ben redefined in the base, we'll use the base value
        value = get_in_classes(bases, field_name)
        if value:
            field_values[field_name] = value
            if isinstance(value, Field):
                field_types[field_name] = value.type_
            else:
                field_types[field_name] = type(value)
        else:
            # try to get a type from the annotations
            type = get_in_classes(bases, f"__annotations__.{field_name}")
            if type:
                field_types[field_name] = type
            else:
                # this field isn't defined on any of the bases, so it must be invalid
                raise RuntimeError(
                    f"Field {field_name} is not defined on any of the bases of {base}"
                )

    VariantModel = type(
        variant_attr_name,
        bases,
        {
            "__annotations__": field_types,
            "__include_fields__": None,
            "__exclude_fields__": None,
            **field_values,
        },
    )
    return VariantModel


def make_and_attach_variant(
    base,
    variant_attr_name: str,
    variant_type: type[VariantModelBase],
    include: Iterable[str] = None,
    exclude: Iterable[str] = None,
) -> VariantModelBase:
    VariantModel = make_variant(base, variant_attr_name, variant_type, include, exclude)
    setattr(base, variant_attr_name, VariantModel)
    return base


@export
def create_variant(
    include: Iterable[str] = None, exclude: Iterable[str] = None
) -> VariantModelBase:
    def decorator(base: type[AbstractEntity]) -> type[AbstractEntity]:
        return make_and_attach_variant(base, CreateModelBase, include, exclude)

    return decorator


@export
def read_variant(
    include: Iterable[str] = None, exclude: Iterable[str] = None
) -> VariantModelBase:
    def decorator(base: type[AbstractEntity]) -> type[AbstractEntity]:
        return make_and_attach_variant(base, ReadModelBase, include, exclude)

    return decorator


@export
def update_variant(
    include: Iterable[str] = None, exclude: Iterable[str] = None
) -> VariantModelBase:
    def decorator(base: type[AbstractEntity]) -> type[AbstractEntity]:
        return make_and_attach_variant(base, UpdateModelBase, include, exclude)

    return decorator


@export
def db_variant(
    include: Iterable[str] = None, exclude: Iterable[str] = None
) -> VariantModelBase:
    def decorator(base: type[AbstractEntity]) -> type[AbstractEntity]:
        return make_and_attach_variant(base, DBModelBase, include, exclude)

    return decorator
