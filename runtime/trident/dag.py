"""DAG construction and validation."""

from dataclasses import dataclass, field

from .errors import DAGError
from .project import Edge, Project


@dataclass
class DAGNode:
    """Node in the execution DAG."""

    id: str
    type: str  # "prompt", "input", "output", "tool"
    incoming_edges: list[Edge] = field(default_factory=list)
    outgoing_edges: list[Edge] = field(default_factory=list)


@dataclass
class DAG:
    """Directed Acyclic Graph for execution."""

    nodes: dict[str, DAGNode]
    execution_order: list[str]  # Topologically sorted node IDs


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

    # Topological sort (Kahn's algorithm)
    in_degree = {node_id: len(node.incoming_edges) for node_id, node in nodes.items()}
    queue = [node_id for node_id, degree in in_degree.items() if degree == 0]
    execution_order = []

    while queue:
        # Sort for deterministic ordering
        queue.sort()
        current = queue.pop(0)
        execution_order.append(current)

        for edge in nodes[current].outgoing_edges:
            in_degree[edge.to_node] -= 1
            if in_degree[edge.to_node] == 0:
                queue.append(edge.to_node)

    # Check for cycles
    if len(execution_order) != len(nodes):
        remaining = set(nodes.keys()) - set(execution_order)
        raise DAGError(f"Cycle detected in DAG. Nodes involved: {remaining}")

    return DAG(nodes=nodes, execution_order=execution_order)


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
    symbols = {"input": "[I]", "prompt": "[P]", "tool": "[T]", "output": "[O]"}
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
    lines.append("Legend: [I] Input, [P] Prompt, [T] Tool, [O] Output")

    return "\n".join(lines)
