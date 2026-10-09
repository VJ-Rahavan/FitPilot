"""Validate individual UI components produced by the LLM.

Components are validated one at a time so each can be shown as soon as it has been
generated (see `genui.ui.stream`).
"""

from dataclasses import dataclass
from typing import Any

from pydantic import TypeAdapter, ValidationError

from genui.core.schema_utils import format_validation_error, strip_titles
from genui.ui.components import Component, UISpec

MAX_NESTING_DEPTH = 6

_COMPONENT = TypeAdapter[Any](Component)


@dataclass(slots=True, frozen=True)
class ComponentResult:
    component: dict[str, Any] | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.component is not None


def validate_component(raw: Any) -> ComponentResult:
    """Validate one top-level component into a JSON-ready dict (or a readable error)."""
    if not isinstance(raw, dict):
        return ComponentResult(error="each component must be a JSON object")
    try:
        model = _COMPONENT.validate_python(raw)
    except ValidationError as exc:
        return ComponentResult(error=format_validation_error(exc))
    component: dict[str, Any] = model.model_dump(mode="json", exclude_none=True)
    if (depth := _depth(component)) > MAX_NESTING_DEPTH:
        return ComponentResult(
            error=f"nested {depth} levels deep; the maximum is {MAX_NESTING_DEPTH}"
        )
    return ComponentResult(component=component)


def ui_json_schema() -> dict[str, Any]:
    """Schema of the component catalog (with $defs, since components are recursive)."""
    return strip_titles(UISpec.model_json_schema())


def _depth(node: dict[str, Any]) -> int:
    children = node.get("children") or []
    return 1 + max((_depth(c) for c in children if isinstance(c, dict)), default=0)
