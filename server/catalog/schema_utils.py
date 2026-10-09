"""Helpers for compact, LLM-friendly JSON schemas and validation errors."""

from typing import Any

from pydantic import ValidationError


def strip_titles(node: Any, *, in_properties: bool = False) -> Any:
    """Remove auto-generated `title` keys (but keep properties that are *named* title)."""
    if isinstance(node, dict):
        out: dict[str, Any] = {}
        for key, value in node.items():
            if not in_properties and key == "title" and isinstance(value, str):
                continue
            out[key] = strip_titles(value, in_properties=key in ("properties", "$defs"))
        return out
    if isinstance(node, list):
        return [strip_titles(item) for item in node]
    return node


def format_validation_error(exc: ValidationError, *, max_errors: int = 15) -> str:
    """Render a ValidationError as short `path: message` lines the LLM can act on."""
    lines = []
    for err in exc.errors()[:max_errors]:
        path = ".".join(str(p) for p in err["loc"]) or "<root>"
        lines.append(f"- {path}: {err['msg']}")
    remaining = len(exc.errors()) - max_errors
    if remaining > 0:
        lines.append(f"- ... and {remaining} more errors")
    return "\n".join(lines)
