"""Parser for .prompt files (frontmatter + body)."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import ParseError


@dataclass
class InputField:
    """Input field definition."""

    name: str
    type: str = "string"
    description: str = ""
    required: bool = True
    default: Any = None


@dataclass
class OutputSchema:
    """Output schema definition."""

    format: str = "text"  # "text" or "json"
    fields: dict[str, tuple[str, str]] = field(default_factory=dict)  # name -> (type, description)


@dataclass
class PromptNode:
    """Parsed .prompt file."""

    id: str
    name: str = ""
    description: str = ""
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    inputs: dict[str, InputField] = field(default_factory=dict)
    output: OutputSchema = field(default_factory=OutputSchema)
    body: str = ""
    file_path: Path | None = None


@dataclass
class MCPServerConfig:
    """MCP server configuration for agent nodes."""

    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class AgentNode:
    """Agent node definition - executes via Claude Agent SDK.

    Agent nodes have access to tools and MCP servers, enabling
    autonomous multi-turn execution with real-world interactions.
    """

    id: str
    prompt_path: str  # Path to .prompt file
    allowed_tools: list[str] = field(default_factory=list)
    mcp_servers: dict[str, MCPServerConfig] = field(default_factory=dict)
    max_turns: int = 50  # Default limit for agent iterations
    permission_mode: str = "acceptEdits"  # Auto-accept file edits
    cwd: str | None = None  # Working directory for agent
    # Parsed prompt content (loaded at runtime)
    prompt_node: PromptNode | None = None


def _parse_value(value: str) -> Any:
    """Parse a YAML value into Python type."""
    value = value.strip()

    if not value:
        return None

    # Strip trailing comments (but not inside quotes)
    if not value.startswith('"') and not value.startswith("'"):
        comment_pos = value.find("  #")
        if comment_pos > 0:
            value = value[:comment_pos].strip()

    # Strip quotes
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]

    # Handle inline JSON arrays like ["item1", "item2"]
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        # Parse comma-separated items
        items = []
        for item in inner.split(","):
            item = item.strip()
            # Strip quotes from each item
            if (item.startswith('"') and item.endswith('"')) or (
                item.startswith("'") and item.endswith("'")
            ):
                item = item[1:-1]
            items.append(item)
        return items

    # Booleans
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if value.lower() == "null" or value == "~":
        return None

    # Numbers
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        pass

    return value


def parse_yaml_simple(text: str) -> dict[str, Any]:
    """Simple YAML parser for frontmatter.

    Supports: strings, numbers, booleans, nested dicts, simple lists.
    Does NOT support: multi-line strings, anchors, complex nesting.
    """
    lines = text.split("\n")
    return _parse_yaml_block(lines, 0, 0)[0]


def _parse_yaml_block(lines: list[str], start: int, min_indent: int) -> tuple[dict[str, Any], int]:
    """Parse a YAML block at the given indentation level."""
    result: dict[str, Any] = {}
    i = start

    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()

        # Skip empty lines and comments
        if not stripped or stripped.startswith("#"):
            i += 1
            continue

        indent = len(line) - len(stripped)

        # If we've dedented past our level, we're done
        if indent < min_indent:
            break

        # Handle list items
        if stripped.startswith("- "):
            # This is a list - find the key and parse as list
            i += 1
            continue

        # Handle key: value
        if ":" in stripped:
            colon_pos = stripped.index(":")
            key = stripped[:colon_pos].strip()
            value_part = stripped[colon_pos + 1 :].strip()

            if value_part:
                # Inline value
                result[key] = _parse_value(value_part)
                i += 1
            else:
                # Nested structure - look ahead to determine type
                i += 1
                if i < len(lines):
                    next_line = lines[i].lstrip()
                    next_indent = len(lines[i]) - len(next_line) if next_line else 0

                    if next_line.startswith("- "):
                        # It's a list
                        result[key], i = _parse_yaml_list(lines, i, next_indent)
                    elif next_indent > indent:
                        # It's a nested dict
                        result[key], i = _parse_yaml_block(lines, i, next_indent)
                    else:
                        # Empty value
                        result[key] = None
                else:
                    result[key] = None
        else:
            i += 1

    return result, i


def _parse_yaml_list(lines: list[str], start: int, min_indent: int) -> tuple[list[Any], int]:
    """Parse a YAML list."""
    result: list[Any] = []
    i = start

    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()

        if not stripped or stripped.startswith("#"):
            i += 1
            continue

        indent = len(line) - len(stripped)

        if indent < min_indent:
            break

        if stripped.startswith("- "):
            value = stripped[2:].strip()
            result.append(_parse_value(value))
            i += 1
        else:
            break

    return result, i


def parse_schema_field(value: str) -> tuple[str, str]:
    """Parse 'type, description' schema syntax."""
    if "," in value:
        type_part, _, desc = value.partition(",")
        return type_part.strip(), desc.strip()
    return value.strip(), ""


def parse_prompt_file(path: Path) -> PromptNode:
    """Parse a .prompt file into a PromptNode.

    Format:
        ---
        <frontmatter: YAML>
        ---
        <body: template text>
    """
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        raise ParseError(f"Cannot read {path}: {e}") from e

    # Split frontmatter and body
    parts = re.split(r"^---\s*$", content, maxsplit=2, flags=re.MULTILINE)

    if len(parts) < 3:
        raise ParseError(f"Invalid .prompt format in {path}: missing frontmatter delimiters")

    frontmatter_text = parts[1].strip()
    body = parts[2].strip()

    # Parse frontmatter
    try:
        fm = parse_yaml_simple(frontmatter_text)
    except Exception as e:
        raise ParseError(f"Invalid YAML in {path}: {e}") from e

    if "id" not in fm:
        raise ParseError(f"Missing required 'id' in {path}")

    # Build PromptNode
    node = PromptNode(
        id=fm["id"],
        name=fm.get("name", ""),
        description=fm.get("description", ""),
        model=fm.get("model"),
        temperature=fm.get("temperature"),
        max_tokens=fm.get("max_tokens"),
        body=body,
        file_path=path,
    )

    # Parse inputs
    if "input" in fm and isinstance(fm["input"], dict):
        for name, spec in fm["input"].items():
            if isinstance(spec, dict):
                node.inputs[name] = InputField(
                    name=name,
                    type=spec.get("type", "string"),
                    description=spec.get("description", ""),
                    required=spec.get("required", True),
                    default=spec.get("default"),
                )
            else:
                node.inputs[name] = InputField(name=name)

    # Parse output
    if "output" in fm and isinstance(fm["output"], dict):
        output_spec = fm["output"]
        node.output = OutputSchema(
            format=output_spec.get("format", "text"),
        )
        if "schema" in output_spec and isinstance(output_spec["schema"], dict):
            for fname, fspec in output_spec["schema"].items():
                if isinstance(fspec, str):
                    node.output.fields[fname] = parse_schema_field(fspec)
                else:
                    node.output.fields[fname] = (str(fspec), "")

    return node
