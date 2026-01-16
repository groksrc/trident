"""Parser for .prompt files (frontmatter + body)."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

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
    allowed_tools: list[str] | None = None  # None means "allow all tools"
    mcp_servers: dict[str, MCPServerConfig] = field(default_factory=dict)
    max_turns: int = 50  # Default limit for agent iterations
    permission_mode: str = "acceptEdits"  # Auto-accept file edits
    cwd: str | None = None  # Working directory for agent
    # Parsed prompt content (loaded at runtime)
    prompt_node: PromptNode | None = None


@dataclass
class BranchNode:
    """Branch node definition - calls sub-workflows with optional looping.

    A branch node can:
    - Call another workflow file (workflow: ./refinement.yaml)
    - Call itself recursively (workflow: self)
    - Run conditionally (condition: "quality_score < 8")
    - Loop while a condition is true (loop_while: "needs_refinement")
    - Have a max iteration limit (max_iterations: 5)

    Condition syntax uses field access (not template syntax):
    - Simple fields: "ready", "value > 10"
    - Nested fields: "output.score < 8"

    Example YAML:
        - id: refine_loop
          type: branch
          workflow: ./single_pass.yaml
          loop_while: "quality_score < 8"
          max_iterations: 5
    """

    id: str
    workflow_path: str  # Path to workflow file, or "self" for recursion
    condition: str | None = None  # Pre-execution condition (skip if false)
    loop_while: str | None = None  # Loop condition (evaluated after each iteration)
    max_iterations: int = 10  # Safety limit to prevent infinite loops


@dataclass
class TriggerNode:
    """Trigger node definition - fires downstream workflows.

    A trigger node can:
    - Fire-and-forget: Start downstream workflow without waiting
    - Wait: Block until downstream workflow completes
    - Pass outputs to downstream workflow as inputs

    Example YAML:
        - id: trigger_analysis
          type: trigger
          workflow: ./analysis/agent.tml
          mode: fire-and-forget  # or "wait"
          pass_outputs: true
          emit_signal: true
    """

    id: str
    workflow_path: str  # Path to downstream workflow file
    mode: str = "fire-and-forget"  # "fire-and-forget" or "wait"
    pass_outputs: bool = True  # Whether to pass upstream outputs as inputs
    emit_signal: bool = True  # Whether to emit signal when triggered
    condition: str | None = None  # Pre-execution condition (skip if false)


def parse_yaml_simple(text: str) -> dict[str, Any]:
    """Parse YAML text into a dictionary.

    Uses PyYAML's safe_load for full YAML 1.1 spec support.
    """
    result = yaml.safe_load(text)
    return result if result is not None else {}


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
                if isinstance(fspec, dict):
                    # Verbose format: {type: string, description: "..."}
                    field_type = fspec.get("type", "string")
                    field_desc = fspec.get("description", "")
                    node.output.fields[fname] = (field_type, field_desc)
                else:
                    raise ParseError(
                        f"Invalid schema field '{fname}' in {path}: "
                        f"expected dict with 'type' and 'description', got {type(fspec).__name__}"
                    )

    return node
