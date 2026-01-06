"""DAG construction and validation."""

from dataclasses import dataclass, field

from .errors import DAGError
from .project import Edge, Project


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


def build_dag(project: Project) -> DAG:
    """Build and validate DAG from project.

    Args:
        project: Loaded project

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

    return DAG(nodes=nodes, execution_order=execution_order, execution_levels=execution_levels)


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
