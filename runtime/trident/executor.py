"""DAG execution engine."""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from .conditions import evaluate
from .dag import DAG, build_dag
from .errors import NodeExecutionError, SchemaValidationError, TridentError
from .parser import PromptNode, parse_prompt_file
from .project import Edge, Project
from .providers import CompletionConfig, get_registry, setup_providers
from .template import get_nested, render
from .tools.python import PythonToolRunner

# Agent execution (optional - requires trident[agents])
try:
    from .agents import SDK_AVAILABLE as AGENT_SDK_AVAILABLE
    from .agents import execute_agent
except ImportError:
    AGENT_SDK_AVAILABLE = False

    def execute_agent(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise TridentError(
            "Agent execution requires Claude Agent SDK. "
            "Install with: pip install trident[agents]"
        )


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
    error_type: str | None = None  # Type of exception that occurred

    @property
    def input_tokens(self) -> int:
        """Get input token count from tokens dictionary."""
        return self.tokens.get("input", 0)

    @property
    def output_tokens(self) -> int:
        """Get output token count from tokens dictionary."""
        return self.tokens.get("output", 0)

    @property
    def succeeded(self) -> bool:
        """Check if this node executed successfully."""
        return self.error is None and not self.skipped


@dataclass
class ExecutionTrace:
    """Full execution trace."""

    execution_id: str
    start_time: str
    end_time: str | None = None
    nodes: list[NodeTrace] = field(default_factory=list)
    error: str | None = None  # Top-level execution error

    @property
    def succeeded(self) -> bool:
        """Check if execution completed without errors."""
        return self.error is None and all(n.succeeded or n.skipped for n in self.nodes)

    @property
    def failed_node(self) -> NodeTrace | None:
        """Get the first node that failed, if any."""
        for node in self.nodes:
            if node.error:
                return node
        return None


@dataclass
class ExecutionResult:
    """Result of DAG execution.

    Always returned, even on failure. Check `success` or `error` to determine outcome.
    """

    outputs: dict[str, Any]
    trace: ExecutionTrace
    error: NodeExecutionError | None = None  # Set if execution failed

    @property
    def success(self) -> bool:
        """Check if execution completed successfully."""
        return self.error is None and self.trace.succeeded

    def __repr__(self) -> str:
        """Return string representation showing execution metrics and status."""
        executed = sum(1 for node in self.trace.nodes if not node.skipped)
        return f"ExecutionResult(executed={executed}, success={self.success})"

    def summary(self) -> str:
        """Get a human-readable summary of execution."""
        lines = []
        total = len(self.trace.nodes)
        succeeded = sum(1 for n in self.trace.nodes if n.succeeded)
        skipped = sum(1 for n in self.trace.nodes if n.skipped)
        failed = sum(1 for n in self.trace.nodes if n.error)

        lines.append(f"Execution {'succeeded' if self.success else 'FAILED'}")
        lines.append(
            f"  Nodes: {succeeded} succeeded, {skipped} skipped, {failed} failed (of {total})"
        )

        if self.error:
            lines.append(f"  Error: {self.error}")

        if failed > 0:
            lines.append("  Failed nodes:")
            for node in self.trace.nodes:
                if node.error:
                    lines.append(f"    - {node.id}: {node.error}")

        return "\n".join(lines)


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
    verbose: bool = False,
) -> ExecutionResult:
    """Execute a Trident project.

    Args:
        project: Loaded project
        entrypoint: Starting node ID (default: first entrypoint)
        inputs: Input data for input nodes
        dry_run: If True, simulate execution without LLM calls
        verbose: If True, print node execution progress to stdout

    Returns:
        ExecutionResult with outputs and trace. Always returns, even on failure.
        Check result.success or result.error to determine outcome.

    Raises:
        TridentError: Only for unrecoverable setup errors (no entrypoint, DAG cycle)
    """
    # Initialize providers
    setup_providers()
    registry = get_registry()

    # Build DAG - this can raise DAGError for cycles/invalid structure
    dag = build_dag(project)

    # Determine entrypoint - fail early if none
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
    execution_error: NodeExecutionError | None = None

    # Seed input nodes with provided inputs
    if inputs:
        for node_id in project.input_nodes:
            node_outputs[node_id] = inputs.copy()

    # Execute nodes in topological order
    for node_id in dag.execution_order:
        node = dag.nodes[node_id]
        node_trace = NodeTrace(id=node_id, start_time=_now_iso())

        try:
            if verbose:
                print(f"Executing node: {node_id}")

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
                _execute_prompt_node(
                    node_id, project, dag, node_outputs, node_trace, registry, dry_run
                )

            elif node.type == "tool":
                _execute_tool_node(node_id, project, dag, node_outputs, node_trace, tool_runner)

            elif node.type == "agent":
                _execute_agent_node(node_id, project, dag, node_outputs, node_trace, dry_run)

            node_outputs[node_id] = node_trace.output

        except Exception as e:
            # Capture error details in trace
            node_trace.error = str(e)
            node_trace.error_type = type(e).__name__
            node_trace.end_time = _now_iso()
            trace.nodes.append(node_trace)

            # Wrap in NodeExecutionError with full context
            execution_error = NodeExecutionError(
                node_id=node_id,
                node_type=node.type,
                message=str(e),
                cause=e,
                inputs=node_trace.input,
            )
            trace.error = str(execution_error)

            # Stop execution on first error (fail fast)
            break

        node_trace.end_time = _now_iso()
        trace.nodes.append(node_trace)

    # Collect final outputs from output nodes (even partial on failure)
    final_outputs: dict[str, Any] = {}
    for out_node_id in project.output_nodes:
        if out_node_id in node_outputs:
            final_outputs[out_node_id] = node_outputs[out_node_id]

    # If no explicit output nodes, use last successful node's output
    if not final_outputs and dag.execution_order:
        for out_node_id in reversed(dag.execution_order):
            if out_node_id in node_outputs:
                final_outputs = node_outputs[out_node_id]
                break

    trace.end_time = _now_iso()
    return ExecutionResult(outputs=final_outputs, trace=trace, error=execution_error)


def _execute_prompt_node(
    node_id: str,
    project: Project,
    dag: DAG,
    node_outputs: dict[str, dict[str, Any]],
    node_trace: NodeTrace,
    registry: Any,
    dry_run: bool,
) -> None:
    """Execute a prompt node. Raises on error."""
    prompt_node = project.prompts.get(node_id)
    if not prompt_node:
        raise TridentError("Prompt definition not found in project")

    # Gather inputs
    gathered = _gather_inputs(node_id, dag, node_outputs)
    node_trace.input = gathered

    # Resolve model (node override > project default)
    model = prompt_node.model or project.defaults.get("model")
    if not model:
        raise TridentError("No model specified. Set 'model' in prompt or project defaults.")
    node_trace.model = model

    if dry_run:
        # Dry run: skip LLM call, generate mock output
        node_trace.output = _generate_mock_output(prompt_node)
        node_trace.tokens = {"input": 0, "output": 0}
        return

    # Get provider
    provider_result = registry.get_for_model(model)
    if not provider_result:
        raise TridentError(
            f"No provider found for model '{model}'. "
            f"Check ANTHROPIC_API_KEY or OPENAI_API_KEY is set."
        )
    provider, model_name = provider_result

    # Render template
    rendered = render(prompt_node.body, gathered)

    # Build completion config
    config = CompletionConfig(
        model=model_name,
        temperature=prompt_node.temperature or project.defaults.get("temperature"),
        max_tokens=prompt_node.max_tokens or project.defaults.get("max_tokens"),
        output_format=prompt_node.output.format,
        output_schema=prompt_node.output.fields if prompt_node.output.format == "json" else None,
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
            raise SchemaValidationError(
                f"LLM returned invalid JSON. Response started with: {result.content[:100]!r}"
            ) from e

        # Validate schema
        if prompt_node.output.fields:
            _validate_schema(parsed, prompt_node.output.fields)

        node_trace.output = parsed
    else:
        node_trace.output = {"text": result.content}


def _execute_tool_node(
    node_id: str,
    project: Project,
    dag: DAG,
    node_outputs: dict[str, dict[str, Any]],
    node_trace: NodeTrace,
    tool_runner: PythonToolRunner,
) -> None:
    """Execute a tool node. Raises on error."""
    tool_def = project.tools.get(node_id)
    if not tool_def:
        raise TridentError("Tool definition not found in project")

    # Gather inputs
    gathered = _gather_inputs(node_id, dag, node_outputs)
    node_trace.input = gathered

    # Execute tool
    result = tool_runner.execute(tool_def, gathered)
    node_trace.output = result


def _execute_agent_node(
    node_id: str,
    project: Project,
    dag: DAG,
    node_outputs: dict[str, dict[str, Any]],
    node_trace: NodeTrace,
    dry_run: bool,
) -> None:
    """Execute an agent node via Claude Agent SDK. Raises on error."""
    agent_node = project.agents.get(node_id)
    if not agent_node:
        raise TridentError("Agent definition not found in project")

    # Load prompt if not already loaded
    if not agent_node.prompt_node:
        prompt_path = project.root / agent_node.prompt_path
        if prompt_path.exists():
            agent_node.prompt_node = parse_prompt_file(prompt_path)
        else:
            raise TridentError(f"Agent prompt not found: {prompt_path}")

    # Gather inputs
    gathered = _gather_inputs(node_id, dag, node_outputs)
    node_trace.input = gathered

    if dry_run:
        # Dry run: generate mock output
        if agent_node.prompt_node.output.format == "json":
            mock: dict[str, Any] = {}
            for field_name, (field_type, _) in agent_node.prompt_node.output.fields.items():
                if field_type == "string":
                    mock[field_name] = f"[mock_{field_name}]"
                elif field_type == "array":
                    mock[field_name] = []
                else:
                    mock[field_name] = None
            node_trace.output = mock
        else:
            node_trace.output = {"text": "[DRY RUN] Mock agent response"}
        node_trace.tokens = {"input": 0, "output": 0}
        return

    # Execute agent via SDK
    result = execute_agent(
        agent_node=agent_node,
        inputs=gathered,
        project_root=str(project.root),
    )
    node_trace.output = result
