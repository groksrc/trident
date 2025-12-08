"""DAG execution engine."""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from .conditions import evaluate
from .dag import DAG, build_dag
from .errors import SchemaValidationError, TridentError
from .parser import PromptNode
from .project import Edge, Project
from .providers import CompletionConfig, get_registry, setup_providers
from .template import get_nested, render
from .tools.python import PythonToolRunner


@dataclass
class NodeTrace:
    """Execution trace for a single node."""

    id: str
    start_time: str
    end_time: str | None = None
    input: dict[str, Any] = field(default_factory=dict)
    output: dict[str, Any] = field(default_factory=dict)
    model: str | None = None
    tokens: dict[str, int] = field(default_factory=dict)
    skipped: bool = False
    error: str | None = None

    @property
    def input_tokens(self) -> int:
        """Get input token count from tokens dictionary."""
        return self.tokens.get("input", 0)

    @property
    def output_tokens(self) -> int:
        """Get output token count from tokens dictionary."""
        return self.tokens.get("output", 0)


@dataclass
class ExecutionTrace:
    """Full execution trace."""

    execution_id: str
    start_time: str
    end_time: str | None = None
    nodes: list[NodeTrace] = field(default_factory=list)


@dataclass
class ExecutionResult:
    """Result of DAG execution."""

    outputs: dict[str, Any]
    trace: ExecutionTrace

    def __repr__(self) -> str:
        """Return string representation showing execution metrics and status."""
        executed = sum(1 for node in self.trace.nodes if not node.skipped)
        success = not any(node.error is not None for node in self.trace.nodes)
        return f"ExecutionResult(executed={executed}, success={success})"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _validate_schema(data: dict[str, Any], schema: dict[str, tuple[str, str]]) -> None:
    """Validate data against schema. Strict on required, lenient on extras."""
    for field_name, (field_type, _) in schema.items():
        if field_name not in data:
            raise SchemaValidationError(f"Missing required field: {field_name}")

        value = data[field_name]
        expected_types = {
            "string": str,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        expected = expected_types.get(field_type)
        if expected and not isinstance(value, expected):
            raise SchemaValidationError(
                f"Field '{field_name}' expected {field_type}, got {type(value).__name__}"
            )


def _gather_inputs(
    node_id: str,
    dag: DAG,
    node_outputs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Gather inputs for a node from upstream outputs via edge mappings."""
    inputs: dict[str, Any] = {}
    node = dag.nodes[node_id]

    for edge in node.incoming_edges:
        source_output = node_outputs.get(edge.from_node, {})

        for mapping in edge.mappings:
            # Source expression can be "field" or "output.field.subfield"
            value = get_nested(source_output, mapping.source_expr)
            if value is None and "." in mapping.source_expr:
                # Try without "output." prefix
                alt_expr = mapping.source_expr
                if alt_expr.startswith("output."):
                    alt_expr = alt_expr[7:]
                value = get_nested(source_output, alt_expr)

            inputs[mapping.target_var] = value

    return inputs


def _should_execute(edge: Edge, source_output: dict[str, Any]) -> bool:
    """Check if edge condition allows execution."""
    if not edge.condition:
        return True

    context = {"output": source_output, **source_output}
    try:
        return evaluate(edge.condition, context)
    except Exception:
        # Condition errors treated as false per spec
        return False


def _generate_mock_output(prompt_node: PromptNode) -> dict[str, Any]:
    """Generate mock output for dry-run mode based on output schema."""
    if prompt_node.output.format == "text":
        return {"text": "[DRY RUN] Mock text response"}

    # JSON format - generate mock data matching schema
    mock: dict[str, Any] = {}
    for field_name, (field_type, _desc) in prompt_node.output.fields.items():
        if field_type == "string":
            mock[field_name] = f"[mock_{field_name}]"
        elif field_type == "number":
            mock[field_name] = 0
        elif field_type == "boolean":
            mock[field_name] = True
        elif field_type == "array":
            mock[field_name] = []
        elif field_type == "object":
            mock[field_name] = {}
        else:
            mock[field_name] = None
    return mock


def run(
    project: Project,
    entrypoint: str | None = None,
    inputs: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> ExecutionResult:
    """Execute a Trident project.

    Args:
        project: Loaded project
        entrypoint: Starting node ID (default: first entrypoint)
        inputs: Input data for input nodes
        dry_run: If True, simulate execution without LLM calls

    Returns:
        ExecutionResult with outputs and trace
    """
    # Initialize providers
    setup_providers()
    registry = get_registry()

    # Build DAG
    dag = build_dag(project)

    # Determine entrypoint
    if entrypoint is None:
        if project.entrypoints:
            entrypoint = project.entrypoints[0]
        else:
            raise TridentError("No entrypoint specified and none defined in project")

    # Initialize execution state
    execution_id = str(uuid4())
    trace = ExecutionTrace(execution_id=execution_id, start_time=_now_iso())
    node_outputs: dict[str, dict[str, Any]] = {}
    tool_runner = PythonToolRunner(project.root)

    # Seed input nodes with provided inputs
    if inputs:
        for node_id in project.input_nodes:
            node_outputs[node_id] = inputs.copy()

    # Execute nodes in topological order
    for node_id in dag.execution_order:
        node = dag.nodes[node_id]
        node_trace = NodeTrace(id=node_id, start_time=_now_iso())

        try:
            # Check if any incoming edge condition blocks execution
            should_run = True
            for edge in node.incoming_edges:
                source_output = node_outputs.get(edge.from_node, {})
                if not _should_execute(edge, source_output):
                    should_run = False
                    break

            if not should_run:
                node_trace.skipped = True
                node_trace.end_time = _now_iso()
                trace.nodes.append(node_trace)
                continue

            # Handle different node types
            if node.type == "input":
                # Input nodes already seeded
                node_trace.output = node_outputs.get(node_id, {})

            elif node.type == "output":
                # Output nodes collect upstream data
                node_trace.input = _gather_inputs(node_id, dag, node_outputs)
                node_trace.output = node_trace.input
                node_outputs[node_id] = node_trace.output

            elif node.type == "prompt":
                prompt_node = project.prompts.get(node_id)
                if not prompt_node:
                    raise TridentError(f"Prompt node {node_id} not found")

                # Gather inputs
                gathered = _gather_inputs(node_id, dag, node_outputs)
                node_trace.input = gathered

                # Resolve model (node override > project default)
                model = prompt_node.model or project.defaults.get("model")
                if not model:
                    raise TridentError(f"No model specified for node {node_id}")
                node_trace.model = model

                if dry_run:
                    # Dry run: skip LLM call, generate mock output
                    node_trace.output = _generate_mock_output(prompt_node)
                    node_trace.tokens = {"input": 0, "output": 0}
                else:
                    # Get provider
                    provider_result = registry.get_for_model(model)
                    if not provider_result:
                        raise TridentError(f"No provider found for model: {model}")
                    provider, model_name = provider_result

                    # Render template
                    rendered = render(prompt_node.body, gathered)

                    # Build completion config
                    config = CompletionConfig(
                        model=model_name,
                        temperature=prompt_node.temperature or project.defaults.get("temperature"),
                        max_tokens=prompt_node.max_tokens or project.defaults.get("max_tokens"),
                        output_format=prompt_node.output.format,
                        output_schema=prompt_node.output.fields
                        if prompt_node.output.format == "json"
                        else None,
                    )

                    # Execute completion
                    result = provider.complete(rendered, config)
                    node_trace.tokens = {
                        "input": result.input_tokens,
                        "output": result.output_tokens,
                    }

                    # Parse output
                    if prompt_node.output.format == "json":
                        try:
                            parsed = json.loads(result.content)
                        except json.JSONDecodeError as e:
                            raise SchemaValidationError(f"Invalid JSON output: {e}")

                        # Validate schema
                        if prompt_node.output.fields:
                            _validate_schema(parsed, prompt_node.output.fields)

                        node_trace.output = parsed
                    else:
                        node_trace.output = {"text": result.content}

                node_outputs[node_id] = node_trace.output

            elif node.type == "tool":
                # Find tool definition
                tool_def = project.tools.get(node_id)
                if not tool_def:
                    raise TridentError(f"Tool definition not found: {node_id}")

                # Gather inputs
                gathered = _gather_inputs(node_id, dag, node_outputs)
                node_trace.input = gathered

                # Execute tool
                result = tool_runner.execute(tool_def, gathered)
                node_trace.output = result
                node_outputs[node_id] = result

        except TridentError as e:
            node_trace.error = str(e)
            node_trace.end_time = _now_iso()
            trace.nodes.append(node_trace)
            raise

        node_trace.end_time = _now_iso()
        trace.nodes.append(node_trace)

    # Collect final outputs from output nodes
    final_outputs: dict[str, Any] = {}
    for node_id in project.output_nodes:
        if node_id in node_outputs:
            final_outputs[node_id] = node_outputs[node_id]

    # If no explicit output nodes, use last node's output
    if not final_outputs and dag.execution_order:
        last_node = dag.execution_order[-1]
        final_outputs = node_outputs.get(last_node, {})

    trace.end_time = _now_iso()
    return ExecutionResult(outputs=final_outputs, trace=trace)
