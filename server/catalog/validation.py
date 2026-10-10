"""Validate outgoing UI components against the catalog.

The server builds every component itself, so a validation failure is a server bug:
it is logged and raised, never retried or sent to the client.
"""

import logging
from typing import Any, Literal

from pydantic import ValidationError

from server.catalog.components import UISpec
from server.catalog.schema_utils import format_validation_error, strip_titles

logger = logging.getLogger("fitgen.catalog")

MAX_NESTING_DEPTH = 6

Display = Literal["fragment", "full"]


class ComponentValidationError(RuntimeError):
    """A tool built components that don't match the catalog (a server bug)."""


def validate_components(
    components: list[dict[str, Any]], display: Display = "fragment"
) -> dict[str, Any]:
    """Validate a component list; return the JSON-ready `structuredContent` dict."""
    try:
        spec = UISpec.model_validate({"components": components, "display": display})
    except ValidationError as exc:
        message = format_validation_error(exc)
        logger.error("Invalid UI components (server bug):\n%s", message)
        raise ComponentValidationError(message) from exc
    out = spec.model_dump(mode="json", exclude_none=True)
    for component in out["components"]:
        if (depth := _depth(component)) > MAX_NESTING_DEPTH:
            message = f"nested {depth} levels deep; the maximum is {MAX_NESTING_DEPTH}"
            logger.error("Invalid UI components (server bug): %s", message)
            raise ComponentValidationError(message)
    return out


def ui_json_schema() -> dict[str, Any]:
    """Schema of the component catalog (with $defs, since components are recursive)."""
    return strip_titles(UISpec.model_json_schema())


def _depth(node: dict[str, Any]) -> int:
    children = node.get("children") or []
    return 1 + max((_depth(c) for c in children if isinstance(c, dict)), default=0)
