"""Minimal {{var}} template rendering per DEC-001."""

import re
from typing import Any


def get_nested(data: dict[str, Any], path: str) -> Any:
    """Get a nested value from a dict using dot notation.

    Examples:
        get_nested({"a": {"b": 1}}, "a.b") -> 1
        get_nested({"a": 1}, "a") -> 1
        get_nested({"a": 1}, "b") -> None
    """
    parts = path.split(".")
    current = data
    for part in parts:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
        if current is None:
            return None
    return current


def render(template: str, variables: dict[str, Any]) -> str:
    """Render a template with {{var}} substitution.

    Supports:
        - {{var}} - direct variable
        - {{var.nested.path}} - nested access
        - {{ var }} - spaces are ignored

    Unknown variables are left as-is.
    """

    def replace(match: re.Match) -> str:
        key = match.group(1).strip()
        if "." in key:
            value = get_nested(variables, key)
        else:
            value = variables.get(key)

        if value is None:
            return match.group(0)  # Leave unknown vars as-is
        return str(value)

    return re.sub(r"\{\{\s*([^}]+?)\s*\}\}", replace, template)
