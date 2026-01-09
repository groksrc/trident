"""DAG construction and validation."""

from dataclasses import dataclass, field
from typing import Any

from .errors import DAGError
from .project import Edge, Project
from .tools.python import get_tool_parameters


@dataclass
class ValidationWarning:
    """A validation warning (non-fatal issue)."""

    message: str
    edge_id: str | None = None
    node_id: str | None = None


@dataclass
class ValidationResult:
    """Result of DAG validation."""

    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[ValidationWarning] = field(default_factory=list)


@dataclass
class DAGNode:
    """Node in the execution DAG."""

    id: str
    type: str  # "prompt", "input", "output", "tool", "agent", "branch"
    incoming_edges: list[Edge] = field(default_factory=list)
    outgoing_edges: list[Edge] = field(default_factory=list)


@dataclass
class DAG:
    """Directed Acyclic Graph for execution."""

    nodes: dict[str, DAGNode]
    execution_order: list[str]  # Topologically sorted node IDs (flat, for backward compat)
    execution_levels: list[list[str]]  # Nodes grouped by level (parallel within level)


def get_node_output_fields(project: Project, node_id: str, node_type: str) -> set[str]:
    """Get the fields a node outputs.

    This defines the 'output contract' for each node type, enabling
    validation of edge mappings before execution.

    Args:
        project: The loaded project
        node_id: ID of the node
        node_type: Type of the node (input, prompt, tool, agent, branch, output)

    Returns:
        Set of field names that can be used in edge mapping source expressions
    """
    if node_type == "input":
        if node_id in project.input_nodes:
            return set(project.input_nodes[node_id].schema.keys())
        return set()

    elif node_type == "prompt":
        if node_id in project.prompts:
            prompt = project.prompts[node_id]
            # All prompts output 'text' - for JSON format, text contains the parsed object
            # For JSON prompts, the schema fields are also available at top level
            if prompt.output.format == "json" and prompt.output.fields:
                return {"text"} | set(prompt.output.fields.keys())
            return {"text"}
        return {"text"}

    elif node_type == "tool":
        # Tools return either:
        # - A dict: fields available directly
        # - Non-dict: wrapped as {"output": value}
        # We can't know at validation time, so accept both patterns
        return {"output"}  # Conservative default

    elif node_type == "agent":
        # Agents output 'text' with the final response
        # May also have structured output depending on prompt
        if node_id in project.agents:
            agent = project.agents[node_id]
            # Check if agent's prompt has structured output
            prompt_path = agent.prompt_path
            # Extract prompt ID from path (e.g., "prompts/foo.prompt" -> "foo")
            prompt_id = prompt_path.replace("prompts/", "").replace(".prompt", "")
            if prompt_id in project.prompts:
                prompt = project.prompts[prompt_id]
                if prompt.output.format == "json" and prompt.output.fields:
                    return {"text"} | set(prompt.output.fields.keys())
        return {"text"}

    elif node_type == "branch":
        # Branch nodes pass through their sub-workflow output
        return {"output", "text"}

    elif node_type == "output":
        # Output nodes don't have downstream edges
        return set()

    return set()


def get_node_input_fields(project: Project, node_id: str, node_type: str) -> set[str]:
    """Get the fields a node expects as input.

    Args:
        project: The loaded project
        node_id: ID of the node
        node_type: Type of the node

    Returns:
        Set of field names expected by the node, or empty set if any field is accepted
    """
    if node_type == "prompt":
        if node_id in project.prompts:
            prompt = project.prompts[node_id]
            return set(prompt.inputs.keys())
        return set()

    elif node_type == "agent":
        if node_id in project.agents:
            agent = project.agents[node_id]
            # Check agent's prompt for input schema
            prompt_path = agent.prompt_path
            prompt_id = prompt_path.replace("prompts/", "").replace(".prompt", "")
            if prompt_id in project.prompts:
                prompt = project.prompts[prompt_id]
                return set(prompt.inputs.keys())
        return set()

    elif node_type == "tool":
        # Introspect tool function signature for parameter names
        if node_id in project.tools:
            tool_def = project.tools[node_id]
            params = get_tool_parameters(project.root, tool_def)
            if params is not None:
                return params
        # Fallback: can't determine, accept anything
        return set()

    elif node_type == "output":
        # Output nodes accept anything
        return set()

    elif node_type == "branch":
        # Branch inputs depend on sub-workflow
        return set()

    return set()


def validate_edge_mappings(
    project: Project, dag: "DAG", strict: bool = False
) -> ValidationResult:
    """Validate edge mappings against node input/output contracts.

    Args:
        project: The loaded project
        dag: The constructed DAG
        strict: If True, treat warnings as errors

    Returns:
        ValidationResult with any errors and warnings
    """
    result = ValidationResult(valid=True)

    for edge in project.edges.values():
        source_node = dag.nodes.get(edge.from_node)
        target_node = dag.nodes.get(edge.to_node)

        if not source_node or not target_node:
            # build_dag already validates node existence
            continue

        source_fields = get_node_output_fields(project, edge.from_node, source_node.type)
        target_fields = get_node_input_fields(project, edge.to_node, target_node.type)

        for mapping in edge.mappings:
            # Validate source field
            base_field = mapping.source_expr.split(".")[0]
            if source_fields and base_field not in source_fields:
                warning = ValidationWarning(
                    message=(
                        f"Source field '{mapping.source_expr}' may not exist in "
                        f"'{edge.from_node}' ({source_node.type}) output. "
                        f"Available fields: {sorted(source_fields)}"
                    ),
                    edge_id=edge.id,
                    node_id=edge.from_node,
                )
                result.warnings.append(warning)

            # Validate target field (only if target has defined inputs)
            if target_fields and mapping.target_var not in target_fields:
                warning = ValidationWarning(
                    message=(
                        f"Target field '{mapping.target_var}' not expected by "
                        f"'{edge.to_node}' ({target_node.type}). "
                        f"Expected inputs: {sorted(target_fields)}"
                    ),
                    edge_id=edge.id,
                    node_id=edge.to_node,
                )
                result.warnings.append(warning)

    # In strict mode, warnings become errors
    if strict and result.warnings:
        result.valid = False
        result.errors = [w.message for w in result.warnings]

    return result


def build_dag(project: Project, validate_mappings_flag: bool = False) -> DAG:
    """Build and validate DAG from project.

    Args:
        project: Loaded project
        validate_mappings_flag: If True, validate edge mappings and print warnings

    Returns:
        Validated DAG with topological execution order

    Raises:
        DAGError: If DAG is invalid (cycles, missing nodes, etc.)
    """
    nodes: dict[str, DAGNode] = {}

    # Create nodes for all known entities
    for node_id in project.input_nodes:
        nodes[node_id] = DAGNode(id=node_id, type="input")

    for node_id in project.prompts:
        nodes[node_id] = DAGNode(id=node_id, type="prompt")

    for node_id in project.output_nodes:
        nodes[node_id] = DAGNode(id=node_id, type="output")

    for node_id in project.tools:
        nodes[node_id] = DAGNode(id=node_id, type="tool")

    for node_id in project.agents:
        nodes[node_id] = DAGNode(id=node_id, type="agent")

    for node_id in project.branches:
        nodes[node_id] = DAGNode(id=node_id, type="branch")

    # Wire up edges
    for edge in project.edges.values():
        if edge.from_node not in nodes:
            raise DAGError(f"Edge {edge.id} references unknown source node: {edge.from_node}")
        if edge.to_node not in nodes:
            raise DAGError(f"Edge {edge.id} references unknown target node: {edge.to_node}")

        nodes[edge.from_node].outgoing_edges.append(edge)
        nodes[edge.to_node].incoming_edges.append(edge)

    # Validate: no orphan prompt nodes
    for node_id, node in nodes.items():
        if node.type == "prompt" and not node.incoming_edges and node_id not in project.entrypoints:
            # Prompt with no incoming edges and not an entrypoint - might be okay if unused
            pass

    # Topological sort with level grouping (modified Kahn's algorithm)
    # Nodes at the same level can execute in parallel
    in_degree = {node_id: len(node.incoming_edges) for node_id, node in nodes.items()}
    current_level = [node_id for node_id, degree in in_degree.items() if degree == 0]
    execution_levels: list[list[str]] = []
    execution_order: list[str] = []

    while current_level:
        # Sort for deterministic ordering within level
        current_level.sort()
        execution_levels.append(current_level)
        execution_order.extend(current_level)

        # Find next level - nodes whose dependencies are all satisfied
        next_level = []
        for node_id in current_level:
            for edge in nodes[node_id].outgoing_edges:
                in_degree[edge.to_node] -= 1
                if in_degree[edge.to_node] == 0:
                    next_level.append(edge.to_node)

        current_level = next_level

    # Check for cycles
    if len(execution_order) != len(nodes):
        remaining = set(nodes.keys()) - set(execution_order)
        raise DAGError(f"Cycle detected in DAG. Nodes involved: {remaining}")

    dag = DAG(nodes=nodes, execution_order=execution_order, execution_levels=execution_levels)

    # Optionally validate edge mappings
    if validate_mappings_flag:
        validation = validate_edge_mappings(project, dag)
        if validation.warnings:
            import sys
            print("Edge mapping warnings:", file=sys.stderr)
            for warning in validation.warnings:
                print(f"  ⚠ {warning.message}", file=sys.stderr)
            print(file=sys.stderr)

    return dag


def get_upstream_nodes(dag: DAG, node_id: str) -> list[str]:
    """Get all nodes that feed into a given node."""
    node = dag.nodes.get(node_id)
    if not node:
        return []
    return [edge.from_node for edge in node.incoming_edges]


def get_downstream_nodes(dag: DAG, node_id: str) -> list[str]:
    """Get all nodes that a given node feeds into."""
    node = dag.nodes.get(node_id)
    if not node:
        return []
    return [edge.to_node for edge in node.outgoing_edges]


def _get_node_symbol(node_type: str) -> str:
    """Get the symbol for a node type.

    Args:
        node_type: The type of the node

    Returns:
        Single character symbol in brackets
    """
    symbols = {
        "input": "[I]",
        "prompt": "[P]",
        "tool": "[T]",
        "output": "[O]",
        "agent": "[A]",
        "branch": "[B]",
    }
    return symbols.get(node_type, "[?]")


def visualize_dag(dag: DAG) -> str:
    """Generate ASCII visualization of the DAG.

    Args:
        dag: The DAG to visualize

    Returns:
        ASCII string representation of the DAG
    """
    if not dag.nodes:
        return "No nodes found"

    lines = []
    lines.append("DAG Visualization:")
    lines.append("")

    # Show nodes in execution order with connections
    for i, node_id in enumerate(dag.execution_order):
        node = dag.nodes[node_id]
        symbol = _get_node_symbol(node.type)

        # Show the node
        lines.append(f"{symbol} {node_id}")

        # Show outgoing connections
        if node.outgoing_edges:
            for j, edge in enumerate(node.outgoing_edges):
                is_last_edge = j == len(node.outgoing_edges) - 1
                connector = "└──" if is_last_edge else "├──"
                target_symbol = _get_node_symbol(dag.nodes[edge.to_node].type)
                lines.append(f"  {connector}> {target_symbol} {edge.to_node}")

        # Add spacing between nodes (except for last)
        if i < len(dag.execution_order) - 1:
            lines.append("")

    lines.append("")
    lines.append("Legend: [I] Input, [P] Prompt, [T] Tool, [A] Agent, [B] Branch, [O] Output")

    return "\n".join(lines)


def visualize_dag_mermaid(dag: DAG, direction: str = "TD") -> str:
    """Generate Mermaid flowchart visualization of the DAG.

    Args:
        dag: The DAG to visualize
        direction: Flow direction - TD (top-down), LR (left-right), etc.

    Returns:
        Mermaid markdown string that renders in GitHub, GitLab, Obsidian, etc.

    Example output:
        ```mermaid
        flowchart TD
            input([input])
            analyze[analyze]
            output([output])

            input --> analyze
            analyze --> output
        ```
    """
    if not dag.nodes:
        return "```mermaid\nflowchart TD\n    empty[No nodes]\n```"

    lines = ["```mermaid", f"flowchart {direction}", ""]

    # Node shape mapping based on type
    # () = stadium/rounded, [] = rectangle, {} = rhombus, (()) = circle
    shape_map = {
        "input": ("([", "])"),  # Stadium shape for input
        "output": ("([", "])"),  # Stadium shape for output
        "prompt": ("[", "]"),  # Rectangle for prompt
        "tool": ("{{", "}}"),  # Hexagon for tool
        "agent": ("[[", "]]"),  # Subroutine for agent
        "branch": ("{", "}"),  # Rhombus for branch/decision
    }

    # Define nodes with shapes
    lines.append("    %% Nodes")
    for node_id in dag.execution_order:
        node = dag.nodes[node_id]
        left, right = shape_map.get(node.type, ("[", "]"))
        # Sanitize node_id for Mermaid (replace hyphens, spaces)
        safe_id = node_id.replace("-", "_").replace(" ", "_")
        label = f"{node.type}: {node_id}" if node.type not in ("input", "output") else node_id
        lines.append(f"    {safe_id}{left}{label}{right}")

    lines.append("")
    lines.append("    %% Edges")

    # Define edges
    seen_edges: set[tuple[str, str]] = set()
    for node_id in dag.execution_order:
        node = dag.nodes[node_id]
        for edge in node.outgoing_edges:
            edge_tuple = (edge.from_node, edge.to_node)
            if edge_tuple not in seen_edges:
                seen_edges.add(edge_tuple)
                safe_from = edge.from_node.replace("-", "_").replace(" ", "_")
                safe_to = edge.to_node.replace("-", "_").replace(" ", "_")
                lines.append(f"    {safe_from} --> {safe_to}")

    lines.append("```")
    return "\n".join(lines)
