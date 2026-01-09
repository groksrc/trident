"""Project and manifest loading."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import ParseError, ValidationError
from .parser import (
    AgentNode,
    BranchNode,
    MCPServerConfig,
    PromptNode,
    parse_prompt_file,
    parse_yaml_simple,
)


@dataclass
class EdgeMapping:
    """Field mapping for an edge."""

    target_var: str
    source_expr: str


@dataclass
class Edge:
    """Edge connecting two nodes."""

    id: str
    from_node: str
    to_node: str
    mappings: list[EdgeMapping] = field(default_factory=list)
    condition: str | None = None


@dataclass
class InputNode:
    """Input node definition."""

    id: str = "input"
    schema: dict[str, tuple[str, str]] = field(default_factory=dict)  # name -> (type, desc)


@dataclass
class OutputNode:
    """Output node definition."""

    id: str = "output"
    format: str = "json"


@dataclass
class ToolDef:
    """Tool definition."""

    id: str
    type: str  # "python", "shell", "http"
    path: str | None = None
    module: str | None = None
    function: str | None = None
    description: str = ""


@dataclass
class Project:
    """Loaded Trident project."""

    name: str
    root: Path
    version: str = "0.1"
    description: str = ""
    defaults: dict[str, Any] = field(default_factory=dict)
    entrypoints: list[str] = field(default_factory=list)
    edges: dict[str, Edge] = field(default_factory=dict)
    prompts: dict[str, PromptNode] = field(default_factory=dict)
    input_nodes: dict[str, InputNode] = field(default_factory=dict)
    output_nodes: dict[str, OutputNode] = field(default_factory=dict)
    tools: dict[str, ToolDef] = field(default_factory=dict)
    agents: dict[str, AgentNode] = field(default_factory=dict)  # Agent nodes (SPEC-3)
    branches: dict[str, BranchNode] = field(default_factory=dict)  # Branch nodes (sub-workflows)
    env: dict[str, dict[str, Any]] = field(default_factory=dict)


def _load_dotenv(env_path: Path) -> None:
    """Load .env file into os.environ if it exists.

    Does not override existing environment variables.
    Supports standard .env format: KEY=VALUE, with optional quotes.

    Args:
        env_path: Path to .env file
    """
    if not env_path.exists():
        return

    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue
            # Parse KEY=VALUE
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # Strip quotes if present
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                value = value[1:-1]
            # Don't override existing env vars
            if key not in os.environ:
                os.environ[key] = value


def load_project(path: str | Path) -> Project:
    """Load a Trident project from a file or directory.

    Args:
        path: Path to manifest file (.tml/.yaml) or directory containing one.
              If a directory, auto-discovers manifest in order:
              agent.tml, trident.tml, trident.yaml

    Returns:
        Loaded and validated Project

    Raises:
        ParseError: If files cannot be parsed
        ValidationError: If project structure is invalid
    """
    path = Path(path).resolve()

    # If path is a file, load it directly
    if path.is_file():
        manifest_path = path
        root = path.parent
    # If path is a directory, auto-discover manifest
    else:
        root = path
        # Search order: agent.tml (primary), trident.tml, trident.yaml (legacy)
        manifest_path = None
        for candidate in ["agent.tml", "trident.tml", "trident.yaml"]:
            candidate_path = root / candidate
            if candidate_path.exists():
                manifest_path = candidate_path
                break
        if manifest_path is None:
            raise ParseError(f"No agent.tml, trident.tml, or trident.yaml found in {root}")

    # Load .env file if present (before parsing manifest)
    _load_dotenv(root / ".env")

    try:
        manifest_text = manifest_path.read_text(encoding="utf-8")
        manifest = parse_yaml_simple(manifest_text)
    except Exception as e:
        raise ParseError(f"Cannot parse {manifest_path.name}: {e}") from e

    # Validate required fields
    if "trident" not in manifest:
        raise ValidationError("Missing 'trident' version in manifest")
    if "name" not in manifest:
        raise ValidationError("Missing 'name' in manifest")

    project = Project(
        name=manifest["name"],
        root=root,
        version=manifest.get("version", "0.1"),
        description=manifest.get("description", ""),
        defaults=manifest.get("defaults", {}),
        entrypoints=manifest.get("entrypoints", []),
    )

    # Parse env declarations
    if "env" in manifest:
        project.env = manifest["env"]

    # Parse nodes (input/output/tool)
    if "nodes" in manifest:
        for node_id, node_spec in manifest["nodes"].items():
            if not isinstance(node_spec, dict):
                continue
            node_type = node_spec.get("type", "prompt")
            if node_type == "input":
                input_node = InputNode(id=node_id)
                if "schema" in node_spec:
                    for fname, fspec in node_spec["schema"].items():
                        if isinstance(fspec, str) and "," in fspec:
                            ftype, fdesc = fspec.split(",", 1)
                            input_node.schema[fname] = (ftype.strip(), fdesc.strip())
                        else:
                            input_node.schema[fname] = (str(fspec), "")
                project.input_nodes[node_id] = input_node
            elif node_type == "output":
                project.output_nodes[node_id] = OutputNode(
                    id=node_id,
                    format=node_spec.get("format", "json"),
                )
            elif node_type == "tool":
                # Tools must be defined in the tools: section, not nodes:
                raise ValidationError(
                    f"Node '{node_id}' has type 'tool', but tools must be defined "
                    f"in the 'tools:' section at the bottom of the manifest, not in 'nodes:'.\n"
                    f"\n"
                    f"Move this definition to the tools section:\n"
                    f"\n"
                    f"  tools:\n"
                    f"    {node_id}:\n"
                    f"      type: python\n"
                    f"      module: <module_name>\n"
                    f"      function: <function_name>\n"
                    f"\n"
                    f"Then reference it in edges by using '{node_id}' as the from/to node."
                )
            elif node_type == "agent":
                # Parse agent node configuration (SPEC-3)
                mcp_servers: dict[str, MCPServerConfig] = {}
                if "mcp_servers" in node_spec:
                    for server_name, server_spec in node_spec["mcp_servers"].items():
                        if isinstance(server_spec, dict):
                            mcp_servers[server_name] = MCPServerConfig(
                                command=server_spec.get("command", ""),
                                args=server_spec.get("args", []),
                                env=server_spec.get("env", {}),
                            )

                allowed_tools_raw = node_spec.get("allowed_tools", [])
                if isinstance(allowed_tools_raw, list):
                    allowed_tools = [str(t) for t in allowed_tools_raw]
                elif isinstance(allowed_tools_raw, str):
                    allowed_tools = [allowed_tools_raw]
                else:
                    allowed_tools = []

                project.agents[node_id] = AgentNode(
                    id=node_id,
                    prompt_path=node_spec.get("prompt", f"prompts/{node_id}.prompt"),
                    allowed_tools=allowed_tools,
                    mcp_servers=mcp_servers,
                    max_turns=node_spec.get("max_turns", 50),
                    permission_mode=node_spec.get("permission_mode", "acceptEdits"),
                    cwd=node_spec.get("cwd"),
                )
            elif node_type == "branch":
                # Parse branch node configuration (sub-workflow calls)
                workflow_path = node_spec.get("workflow", "")
                if not workflow_path:
                    raise ValidationError(
                        f"Branch node '{node_id}' missing required 'workflow' path"
                    )

                project.branches[node_id] = BranchNode(
                    id=node_id,
                    workflow_path=workflow_path,
                    condition=node_spec.get("condition"),
                    loop_while=node_spec.get("loop_while"),
                    max_iterations=node_spec.get("max_iterations", 10),
                )

    # Parse edges
    if "edges" in manifest:
        for edge_id, edge_spec in manifest["edges"].items():
            if not isinstance(edge_spec, dict):
                continue
            edge = Edge(
                id=edge_id,
                from_node=edge_spec.get("from", ""),
                to_node=edge_spec.get("to", ""),
                condition=edge_spec.get("condition"),
            )
            if "mapping" in edge_spec:
                for target, source in edge_spec["mapping"].items():
                    edge.mappings.append(EdgeMapping(target_var=target, source_expr=str(source)))
            project.edges[edge_id] = edge

    # Parse tools
    if "tools" in manifest:
        for tool_id, tool_spec in manifest["tools"].items():
            if not isinstance(tool_spec, dict):
                continue
            project.tools[tool_id] = ToolDef(
                id=tool_id,
                type=tool_spec.get("type", "python"),
                path=tool_spec.get("path"),
                module=tool_spec.get("module"),
                function=tool_spec.get("function"),
                description=tool_spec.get("description", ""),
            )

    # Discover and parse prompt files
    prompts_dir = root / "prompts"
    if prompts_dir.exists():
        for prompt_file in prompts_dir.glob("*.prompt"):
            try:
                node = parse_prompt_file(prompt_file)
                project.prompts[node.id] = node
            except ParseError:
                raise
            except Exception as e:
                raise ParseError(f"Error parsing {prompt_file}: {e}") from e

    # Create implicit input/output nodes if referenced but not defined
    all_from_nodes = {e.from_node for e in project.edges.values()}
    all_to_nodes = {e.to_node for e in project.edges.values()}

    # All known node types
    known_nodes = (
        set(project.prompts.keys())
        | set(project.input_nodes.keys())
        | set(project.output_nodes.keys())
        | set(project.tools.keys())
        | set(project.agents.keys())
        | set(project.branches.keys())
    )

    for node_id in all_from_nodes:
        if node_id not in known_nodes:
            project.input_nodes[node_id] = InputNode(id=node_id)
            known_nodes.add(node_id)

    for node_id in all_to_nodes:
        if node_id not in known_nodes:
            project.output_nodes[node_id] = OutputNode(id=node_id)

    # Default entrypoint
    if not project.entrypoints and project.input_nodes:
        project.entrypoints = list(project.input_nodes.keys())[:1]

    return project
