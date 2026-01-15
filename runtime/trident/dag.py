"""DAG construction and validation."""

from dataclasses import dataclass, field

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
    type: str  # "prompt", "input", "output", "tool", "agent", "branch", "trigger"
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

    elif node_type == "trigger":
        # Trigger nodes output status and optionally downstream outputs (wait mode)
        return {"triggered", "status", "output"}

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

    elif node_type == "trigger":
        # Trigger inputs depend on downstream workflow
        return set()

    return set()


def get_node_output_types(project: Project, node_id: str, node_type: str) -> dict[str, str | None]:
    """Get the fields and their types that a node outputs.

    Args:
        project: The loaded project
        node_id: ID of the node
        node_type: Type of the node

    Returns:
        Dict mapping field names to their types (None if type unknown)
    """
    if node_type == "input":
        if node_id in project.input_nodes:
            schema = project.input_nodes[node_id].schema
            # Input schema is dict[str, tuple[str, str]] where tuple is (type, description)
            types: dict[str, str | None] = {}
            for field_name, spec in schema.items():
                # Handle tuple format from project.py
                if isinstance(spec, tuple):
                    field_type = spec[0]
                else:
                    # Fallback for string format "string, Description"
                    field_type = spec.split(",")[0].strip() if "," in spec else spec.strip()
                types[field_name] = field_type
            return types
        return {}

    elif node_type == "prompt":
        if node_id in project.prompts:
            prompt = project.prompts[node_id]
            types = {"text": "string"}  # text is always string
            if prompt.output.format == "json" and prompt.output.fields:
                for field_name, (field_type, _desc) in prompt.output.fields.items():
                    types[field_name] = field_type
            return types
        return {"text": "string"}

    elif node_type == "agent":
        if node_id in project.agents:
            agent = project.agents[node_id]
            prompt_path = agent.prompt_path
            prompt_id = prompt_path.replace("prompts/", "").replace(".prompt", "")
            if prompt_id in project.prompts:
                prompt = project.prompts[prompt_id]
                types: dict[str, str | None] = {"text": "string"}
                if prompt.output.format == "json" and prompt.output.fields:
                    for field_name, (field_type, _desc) in prompt.output.fields.items():
                        types[field_name] = field_type
                return types
        return {"text": "string"}

    elif node_type == "tool":
        # Tools have unknown output types at validation time
        return {"output": None}

    elif node_type == "branch":
        return {"output": None, "text": "string"}

    elif node_type == "trigger":
        return {"triggered": "boolean", "status": "string", "output": None}

    return {}


def get_node_input_types(project: Project, node_id: str, node_type: str) -> dict[str, str | None]:
    """Get the fields and their expected types for a node's inputs.

    Args:
        project: The loaded project
        node_id: ID of the node
        node_type: Type of the node

    Returns:
        Dict mapping field names to their expected types (None if any type accepted)
    """
    if node_type == "prompt":
        if node_id in project.prompts:
            prompt = project.prompts[node_id]
            return {name: inp.type for name, inp in prompt.inputs.items()}
        return {}

    elif node_type == "agent":
        if node_id in project.agents:
            agent = project.agents[node_id]
            prompt_path = agent.prompt_path
            prompt_id = prompt_path.replace("prompts/", "").replace(".prompt", "")
            if prompt_id in project.prompts:
                prompt = project.prompts[prompt_id]
                return {name: inp.type for name, inp in prompt.inputs.items()}
        return {}

    elif node_type == "tool":
        # Tool parameter types from introspection would require more work
        # For now, return None (accept any type) for tool params
        if node_id in project.tools:
            tool_def = project.tools[node_id]
            params = get_tool_parameters(project.root, tool_def)
            if params is not None:
                return {p: None for p in params}  # Type unknown
        return {}

    # output, input, branch, trigger nodes accept any types
    return {}


def types_compatible(source_type: str | None, target_type: str | None) -> bool:
    """Check if source type is compatible with target type.

    Args:
        source_type: Type of the source field (None = unknown)
        target_type: Expected type of target field (None = any)

    Returns:
        True if types are compatible, False otherwise
    """
    # If either type is unknown, assume compatible
    if source_type is None or target_type is None:
        return True

    # Exact match
    if source_type == target_type:
        return True

    # Compatible type pairs
    compatible_pairs = {
        # number includes integer
        ("integer", "number"),
        ("number", "integer"),  # Allow narrowing too
        # object/array can be passed as string (JSON serialized)
        ("object", "string"),
        ("array", "string"),
    }

    return (source_type, target_type) in compatible_pairs


def validate_edge_mappings(project: Project, dag: "DAG", strict: bool = False) -> ValidationResult:
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

        # Get type information for type checking
        source_types = get_node_output_types(project, edge.from_node, source_node.type)
        target_types = get_node_input_types(project, edge.to_node, target_node.type)

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

            # Type compatibility check (only if both fields exist)
            source_type = source_types.get(base_field)
            target_type = target_types.get(mapping.target_var)
            if not types_compatible(source_type, target_type):
                warning = ValidationWarning(
                    message=(
                        f"Type mismatch: '{base_field}' ({source_type}) from "
                        f"'{edge.from_node}' may not be compatible with "
                        f"'{mapping.target_var}' ({target_type}) in '{edge.to_node}'"
                    ),
                    edge_id=edge.id,
                    node_id=edge.from_node,
                )
                result.warnings.append(warning)

    # In strict mode, warnings become errors
    if strict and result.warnings:
        result.valid = False
        result.errors = [w.message for w in result.warnings]

    return result


def validate_subworkflows(
    project: Project,
    visited: set[str] | None = None,
    strict: bool = False,
) -> ValidationResult:
    """Recursively validate all sub-workflows referenced by branch nodes.

    Args:
        project: The loaded project
        visited: Set of already-visited workflow paths (for cycle detection)
        strict: If True, treat warnings as errors

    Returns:
        ValidationResult with any errors and warnings from sub-workflows
    """

    from .project import load_project

    result = ValidationResult(valid=True)

    if visited is None:
        visited = set()

    # Add current project to visited set
    current_path = str(project.root.resolve())
    if current_path in visited:
        result.valid = False
        result.errors.append(f"Circular workflow reference detected: {current_path}")
        return result
    visited.add(current_path)

    # Validate each branch node's sub-workflow
    for branch_id, branch in project.branches.items():
        workflow_path = branch.workflow_path

        # Handle "self" reference (recursion is allowed, not a cycle)
        if workflow_path == "self":
            continue

        # Resolve path relative to project root
        resolved_path = (project.root / workflow_path).resolve()

        # Check if file exists
        if not resolved_path.exists():
            result.valid = False
            result.errors.append(f"Branch '{branch_id}': workflow file not found: {workflow_path}")
            continue

        # Check for cycles (same file referenced again)
        resolved_str = str(resolved_path)
        if resolved_str in visited:
            result.valid = False
            result.errors.append(
                f"Branch '{branch_id}': circular workflow reference to {workflow_path}"
            )
            continue

        # Try to load and validate the sub-workflow
        try:
            sub_project = load_project(resolved_path)
        except Exception as e:
            result.valid = False
            result.errors.append(
                f"Branch '{branch_id}': failed to load workflow {workflow_path}: {e}"
            )
            continue

        # Build DAG to validate structure
        try:
            sub_dag = build_dag(sub_project)
        except DAGError as e:
            result.valid = False
            result.errors.append(f"Branch '{branch_id}': invalid DAG in {workflow_path}: {e}")
            continue

        # Validate edge mappings in sub-workflow
        sub_validation = validate_edge_mappings(sub_project, sub_dag, strict=strict)
        if not sub_validation.valid:
            result.valid = False
            for error in sub_validation.errors:
                result.errors.append(f"Branch '{branch_id}' ({workflow_path}): {error}")
        for warning in sub_validation.warnings:
            result.warnings.append(
                ValidationWarning(
                    message=f"Branch '{branch_id}' ({workflow_path}): {warning.message}",
                    edge_id=warning.edge_id,
                    node_id=warning.node_id,
                )
            )

        # Recursively validate sub-workflows in the sub-workflow
        sub_subworkflow_result = validate_subworkflows(sub_project, visited.copy(), strict)
        if not sub_subworkflow_result.valid:
            result.valid = False
            result.errors.extend(sub_subworkflow_result.errors)
        result.warnings.extend(sub_subworkflow_result.warnings)

    # In strict mode, warnings become errors
    if strict and result.warnings:
        result.valid = False
        for w in result.warnings:
            if w.message not in result.errors:
                result.errors.append(w.message)

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

    for node_id in project.triggers:
        nodes[node_id] = DAGNode(id=node_id, type="trigger")

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


def get_ancestors(dag: DAG, node_id: str) -> set[str]:
    """Get all ancestor nodes (transitive upstream) of a given node.

    This recursively finds all nodes that feed into the given node,
    directly or indirectly. The node itself is NOT included.

    Args:
        dag: The DAG to search
        node_id: The node to find ancestors for

    Returns:
        Set of node IDs that are ancestors of the given node
    """
    ancestors: set[str] = set()
    to_visit = get_upstream_nodes(dag, node_id)

    while to_visit:
        current = to_visit.pop()
        if current not in ancestors:
            ancestors.add(current)
            to_visit.extend(get_upstream_nodes(dag, current))

    return ancestors


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
        "trigger": "[R]",  # R for tRigger (T is taken by Tool)
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
    lines.append("Legend: [I] Input, [P] Prompt, [T] Tool, [A] Agent, [B] Branch, [R] Trigger, [O] Output")

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
        "trigger": ("((", "))"),  # Circle for trigger
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
