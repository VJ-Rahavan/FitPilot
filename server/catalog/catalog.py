"""Compact, TypeScript-like description of the component catalog for the system prompt.

Generated from the Pydantic models (single source of truth) but ~3x smaller than the raw
JSON Schema, which matters on token-per-minute limited LLM tiers.
"""

import json
import types
from functools import lru_cache
from typing import Annotated, Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel

from genui.ui.components import Component

_PRIMITIVES: dict[Any, str] = {str: "string", int: "int", float: "number", bool: "bool", Any: "any"}


def _is_component_union(args: tuple[Any, ...]) -> bool:
    models = [a for a in args if isinstance(a, type) and issubclass(a, BaseModel)]
    return len(models) > 3 and all("type" in m.model_fields for m in models)


def _type_str(tp: Any) -> str:
    origin, args = get_origin(tp), get_args(tp)
    if tp is type(None):
        return "null"
    if origin is Annotated:
        return _type_str(args[0])
    if origin is Literal:
        return "|".join(json.dumps(a) for a in args)
    if origin in (Union, types.UnionType):
        if _is_component_union(args):
            return "Component"
        return "|".join(_type_str(a) for a in args if a is not type(None))
    if origin is list:
        inner = _type_str(args[0])
        is_union = get_origin(args[0]) in (Union, types.UnionType) and inner != "Component"
        return f"({inner})[]" if is_union else f"{inner}[]"
    if origin is dict:
        return f"{{[key: string]: {_type_str(args[1])}}}"
    if isinstance(tp, type) and issubclass(tp, BaseModel):
        return _object_str(tp)
    return _PRIMITIVES.get(tp, getattr(tp, "__name__", str(tp)))


def _object_str(model: type[BaseModel], *, skip: tuple[str, ...] = ()) -> str:
    parts = []
    for name, field in model.model_fields.items():
        if name in skip:
            continue
        optional = "" if field.is_required() else "?"
        part = f"{name}{optional}: {_type_str(field.annotation)}"
        if field.description:
            part += f" /* {field.description} */"
        parts.append(part)
    return "{" + ", ".join(parts) + "}"


@lru_cache(maxsize=1)
def component_catalog() -> str:
    union_members = get_args(get_args(Component)[0])
    lines = []
    for model in union_members:
        type_name = get_args(model.model_fields["type"].annotation)[0]
        doc = (model.__doc__ or "").strip().splitlines()[0] if model.__doc__ else ""
        header = f'- "{type_name}"' + (f" — {doc}" if doc else "")
        lines.append(f"{header}\n  {_object_str(model, skip=('type',))}")
    return "\n".join(lines)
