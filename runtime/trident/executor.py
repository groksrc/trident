"""DAG execution engine."""

import asyncio
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .artifacts import ArtifactManager, RunMetadata, get_artifact_manager
from .conditions import evaluate
from .dag import DAG, build_dag, validate_edge_mappings
from .errors import BranchError, NodeExecutionError, SchemaValidationError, TridentError
from .parser import PromptNode, parse_prompt_file
from .project import Edge, Project
from .providers import CompletionConfig, get_registry, setup_providers
from .template import get_nested, render
from .tools.python import PythonToolRunner

# Agent execution (optional - requires trident[agents])
try:
    from .agents import SDK_AVAILABLE as AGENT_SDK_AVAILABLE
    from .agents import AgentResult, execute_agent
except ImportError:
    AGENT_SDK_AVAILABLE = False
    AgentResult = None  # type: ignore[misc,assignment]

    def execute_agent(*args: Any, **kwargs: Any) -> Any:
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
    # Agent-specific metrics (SPEC-3 Phase 3)
    cost_usd: float | None = None  # Total cost for agent execution
    session_id: str | None = None  # Session ID for resuming
    num_turns: int = 0  # Number of agent turns

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

    run_id: str  # Unified naming (was execution_id)
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

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "run_id": self.run_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "error": self.error,
            "nodes": [asdict(n) for n in self.nodes],
        }


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


@dataclass
class _NodeExecutionResult:
    """Result of executing a single node (internal use for parallel execution)."""

    node_id: str
    node_trace: "NodeTrace"
    output: dict[str, Any] | None = None
    error: Exception | None = None
    skipped: bool = False


@dataclass
class CheckpointNodeData:
    """Data for a completed node in a checkpoint."""

    outputs: dict[str, Any]
    completed_at: str
    session_id: str | None = None
    cost_usd: float | None = None
    num_turns: int = 0


@dataclass
class Checkpoint:
    """Workflow execution checkpoint for resumption."""

    run_id: str
    project_name: str
    started_at: str
    updated_at: str
    status: str  # "running", "interrupted", "completed", "failed"
    completed_nodes: dict[str, CheckpointNodeData] = field(default_factory=dict)
    pending_nodes: list[str] = field(default_factory=list)
    total_cost_usd: float = 0.0
    inputs: dict[str, Any] = field(default_factory=dict)
    entrypoint: str | None = None
    branch_states: dict[str, int] = field(default_factory=dict)  # branch_id -> iteration

    def save(self, checkpoint_dir: Path) -> Path:
        """Save checkpoint to disk."""
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_path = checkpoint_dir / f"{self.run_id}.json"

        # Convert to JSON-serializable dict
        data = {
            "run_id": self.run_id,
            "project_name": self.project_name,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "status": self.status,
            "completed_nodes": {
                k: asdict(v) for k, v in self.completed_nodes.items()
            },
            "pending_nodes": self.pending_nodes,
            "total_cost_usd": self.total_cost_usd,
            "inputs": self.inputs,
            "entrypoint": self.entrypoint,
            "branch_states": self.branch_states,
        }

        checkpoint_path.write_text(json.dumps(data, indent=2, default=str))
        return checkpoint_path

    @classmethod
    def load(cls, checkpoint_path: Path) -> "Checkpoint":
        """Load checkpoint from disk."""
        data = json.loads(checkpoint_path.read_text())

        # Reconstruct CheckpointNodeData objects
        completed_nodes = {
            k: CheckpointNodeData(**v) for k, v in data.get("completed_nodes", {}).items()
        }

        return cls(
            run_id=data["run_id"],
            project_name=data["project_name"],
            started_at=data["started_at"],
            updated_at=data["updated_at"],
            status=data["status"],
            completed_nodes=completed_nodes,
            pending_nodes=data.get("pending_nodes", []),
            total_cost_usd=data.get("total_cost_usd", 0.0),
            inputs=data.get("inputs", {}),
            entrypoint=data.get("entrypoint"),
            branch_states=data.get("branch_states", {}),
        )


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


def _validate_required_inputs(
    gathered: dict[str, Any],
    prompt_node: PromptNode,
) -> None:
    """Validate that all required inputs are present.

    Args:
        gathered: The gathered inputs from upstream nodes
        prompt_node: The prompt node with input definitions

    Raises:
        SchemaValidationError: If a required input is missing
    """
    missing = []
    for name, input_field in prompt_node.inputs.items():
        if not input_field.required:
            continue
        if input_field.default is not None:
            continue
        if name not in gathered or gathered[name] is None:
            missing.append(name)

    if missing:
        raise SchemaValidationError(
            f"Missing required input(s) for '{prompt_node.id}': {', '.join(missing)}. "
            f"Check edge mappings to ensure these fields are provided."
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

        # Skip edges from nodes that produced no output (e.g., skipped nodes)
        if not source_output:
            continue

        for mapping in edge.mappings:
            # Source expression can be "field" or "output.field.subfield"
            value = get_nested(source_output, mapping.source_expr)
            if value is None and "." in mapping.source_expr:
                # Try without "output." prefix
                alt_expr = mapping.source_expr
                if alt_expr.startswith("output."):
                    alt_expr = alt_expr[7:]
                value = get_nested(source_output, alt_expr)

            # Only set if value is not None (don't overwrite with None from skipped nodes)
            if value is not None or mapping.target_var not in inputs:
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
    # Include text field (raw JSON) + schema fields for consistency
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
    # Include text field with JSON representation
    return {"text": json.dumps(mock), **mock}


def run(
    project: Project,
    entrypoint: str | None = None,
    inputs: dict[str, Any] | None = None,
    dry_run: bool = False,
    verbose: bool = False,
    resume_sessions: dict[str, str] | None = None,
    on_agent_message: "Callable[[str, Any], None] | None" = None,
    checkpoint_dir: str | Path | None = None,
    resume_from: str | Path | None = None,
    artifact_dir: str | Path | None = None,
    run_id: str | None = None,
) -> ExecutionResult:
    """Execute a Trident project.

    Args:
        project: Loaded project
        entrypoint: Starting node ID (default: first entrypoint)
        inputs: Input data for input nodes
        dry_run: If True, simulate execution without LLM calls
        verbose: If True, print node execution progress to stdout
        resume_sessions: Optional dict mapping node_id to session_id for resuming agents
        on_agent_message: Optional callback for agent messages (type, content)
        checkpoint_dir: Directory to save checkpoints (enables checkpointing) [DEPRECATED]
        resume_from: Checkpoint path or run_id to resume from
        artifact_dir: Directory for all artifacts (default: project_root/.trident)
        run_id: Custom run ID (default: auto-generated UUID)

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

    # Validate edge mappings - print warnings in dry-run or verbose mode
    if dry_run or verbose:
        validation = validate_edge_mappings(project, dag)
        if validation.warnings:
            import sys

            print("⚠ Edge mapping warnings:", file=sys.stderr)
            for warning in validation.warnings:
                print(f"  - {warning.message}", file=sys.stderr)
            print(file=sys.stderr)

    # Determine entrypoint - fail early if none
    if entrypoint is None:
        if project.entrypoints:
            entrypoint = project.entrypoints[0]
        else:
            raise TridentError("No entrypoint specified and none defined in project")

    # Handle checkpointing and resume
    checkpoint: Checkpoint | None = None
    checkpoint_path_obj: Path | None = None

    if checkpoint_dir:
        checkpoint_path_obj = Path(checkpoint_dir) if isinstance(checkpoint_dir, str) else checkpoint_dir

    if resume_from:
        # Load checkpoint to resume from
        resume_path = Path(resume_from) if isinstance(resume_from, str) else resume_from

        # If it's just a run_id (not a full path), look in checkpoint_dir
        if not resume_path.exists() and checkpoint_path_obj:
            resume_path = checkpoint_path_obj / f"{resume_from}.json"

        if not resume_path.exists():
            raise TridentError(f"Checkpoint not found: {resume_from}")

        checkpoint = Checkpoint.load(resume_path)
        checkpoint.status = "running"
        checkpoint.updated_at = _now_iso()

        if verbose:
            completed = len(checkpoint.completed_nodes)
            print(f"Resuming from checkpoint: {checkpoint.run_id}")
            print(f"  Completed nodes: {completed}")
            print(f"  Pending nodes: {len(checkpoint.pending_nodes)}")

        # Use inputs from checkpoint if not provided
        if not inputs and checkpoint.inputs:
            inputs = checkpoint.inputs

        # Build resume_sessions from checkpoint if not provided
        if not resume_sessions:
            resume_sessions = {}
            for node_id, node_data in checkpoint.completed_nodes.items():
                if node_data.session_id:
                    resume_sessions[node_id] = node_data.session_id

    # Initialize execution state
    # Determine run_id: provided > checkpoint > generated
    effective_run_id: str
    if run_id:
        effective_run_id = run_id
    elif checkpoint:
        effective_run_id = checkpoint.run_id
    else:
        effective_run_id = str(uuid4())

    trace = ExecutionTrace(run_id=effective_run_id, start_time=_now_iso())
    node_outputs: dict[str, dict[str, Any]] = {}
    tool_runner = PythonToolRunner(project.root)
    execution_error: NodeExecutionError | None = None

    # Initialize artifact manager if artifact_dir is provided
    artifact_manager: ArtifactManager | None = None
    if artifact_dir:
        artifact_path = Path(artifact_dir) if isinstance(artifact_dir, str) else artifact_dir
        artifact_manager = get_artifact_manager(project.root, effective_run_id, artifact_path)
        artifact_manager.register_run(project.name, entrypoint)

        # Save initial metadata
        metadata = RunMetadata(
            run_id=effective_run_id,
            project_name=project.name,
            project_root=str(project.root),
            entrypoint=entrypoint,
            inputs=inputs or {},
            started_at=_now_iso(),
        )
        artifact_manager.save_metadata(metadata)

        if verbose:
            print(f"Artifacts: {artifact_manager.run_dir}")

    # Create new checkpoint if checkpointing is enabled and not resuming
    if checkpoint_path_obj and not checkpoint:
        checkpoint = Checkpoint(
            run_id=effective_run_id,
            project_name=project.name,
            started_at=_now_iso(),
            updated_at=_now_iso(),
            status="running",
            pending_nodes=list(dag.execution_order),
            inputs=inputs or {},
            entrypoint=entrypoint,
        )
        checkpoint.save(checkpoint_path_obj)
        if verbose:
            print(f"Checkpoint created: {run_id}")

    # Seed input nodes with provided inputs
    if inputs:
        for node_id in project.input_nodes:
            node_outputs[node_id] = inputs.copy()

    # Restore outputs from checkpoint for completed nodes
    if checkpoint:
        for node_id, node_data in checkpoint.completed_nodes.items():
            node_outputs[node_id] = node_data.outputs

    # Execute nodes level by level (parallel within each level)
    async def _execute_levels() -> None:
        nonlocal execution_error

        for level in dag.execution_levels:
            if execution_error:
                break  # Stop if previous level had error

            # Partition nodes: those to skip vs those to execute
            nodes_to_skip = []
            nodes_to_execute = []

            for node_id in level:
                if checkpoint and node_id in checkpoint.completed_nodes:
                    nodes_to_skip.append(node_id)
                else:
                    nodes_to_execute.append(node_id)

            # Handle skipped nodes (from checkpoint)
            for node_id in nodes_to_skip:
                node_data = checkpoint.completed_nodes[node_id]
                node_trace = NodeTrace(id=node_id, start_time=_now_iso())
                node_trace.output = node_data.outputs
                node_trace.session_id = node_data.session_id
                node_trace.cost_usd = node_data.cost_usd
                node_trace.num_turns = node_data.num_turns
                node_trace.end_time = node_data.completed_at
                trace.nodes.append(node_trace)
                if verbose:
                    print(f"Skipping completed node: {node_id}")

            if not nodes_to_execute:
                continue

            # Execute all nodes in this level in parallel
            if verbose and len(nodes_to_execute) > 1:
                print(f"Executing {len(nodes_to_execute)} nodes in parallel: {nodes_to_execute}")

            tasks = [
                _execute_node_async(
                    node_id=node_id,
                    project=project,
                    dag=dag,
                    node_outputs=node_outputs,
                    registry=registry,
                    tool_runner=tool_runner,
                    dry_run=dry_run,
                    verbose=verbose,
                    resume_sessions=resume_sessions,
                    on_agent_message=on_agent_message,
                    checkpoint_dir=checkpoint_dir,
                    artifact_manager=artifact_manager,
                    checkpoint=checkpoint,
                )
                for node_id in nodes_to_execute
            ]

            results = await asyncio.gather(*tasks)

            # Process results from this level
            for result in results:
                trace.nodes.append(result.node_trace)

                if result.error:
                    # First error fails the execution
                    if not execution_error:
                        node = dag.nodes[result.node_id]
                        execution_error = NodeExecutionError(
                            node_id=result.node_id,
                            node_type=node.type,
                            message=str(result.error),
                            cause=result.error,
                            inputs=result.node_trace.input,
                        )
                        trace.error = str(execution_error)

                        # Update checkpoint with failure status
                        if checkpoint and checkpoint_path_obj:
                            checkpoint.status = "failed"
                            checkpoint.updated_at = _now_iso()
                            checkpoint.save(checkpoint_path_obj)
                elif not result.skipped:
                    # Store output for downstream nodes
                    node_outputs[result.node_id] = result.output

                    # Save checkpoint after successful node
                    if checkpoint and checkpoint_path_obj:
                        checkpoint.completed_nodes[result.node_id] = CheckpointNodeData(
                            outputs=result.node_trace.output,
                            completed_at=result.node_trace.end_time,
                            session_id=result.node_trace.session_id,
                            cost_usd=result.node_trace.cost_usd,
                            num_turns=result.node_trace.num_turns,
                        )
                        if result.node_id in checkpoint.pending_nodes:
                            checkpoint.pending_nodes.remove(result.node_id)
                        if result.node_trace.cost_usd:
                            checkpoint.total_cost_usd += result.node_trace.cost_usd
                        checkpoint.updated_at = _now_iso()
                        checkpoint.save(checkpoint_path_obj)

    # Run the async execution
    asyncio.run(_execute_levels())

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

    # Final checkpoint update
    if checkpoint and checkpoint_path_obj:
        checkpoint.status = "completed" if not execution_error else "failed"
        checkpoint.updated_at = _now_iso()
        checkpoint.save(checkpoint_path_obj)

    # Save artifacts if artifact manager is active
    if artifact_manager:
        # Save checkpoint via artifact manager
        if checkpoint:
            artifact_manager.save_checkpoint(checkpoint)
        elif not checkpoint_path_obj:
            # Create checkpoint from execution state if not already tracking
            final_checkpoint = Checkpoint(
                run_id=effective_run_id,
                project_name=project.name,
                started_at=trace.start_time,
                updated_at=trace.end_time or _now_iso(),
                status="completed" if not execution_error else "failed",
                inputs=inputs or {},
                entrypoint=entrypoint,
            )
            for node_trace in trace.nodes:
                if not node_trace.skipped and not node_trace.error:
                    final_checkpoint.completed_nodes[node_trace.id] = CheckpointNodeData(
                        outputs=node_trace.output,
                        completed_at=node_trace.end_time or _now_iso(),
                        session_id=node_trace.session_id,
                        cost_usd=node_trace.cost_usd,
                        num_turns=node_trace.num_turns,
                    )
            artifact_manager.save_checkpoint(final_checkpoint)

        # Save trace
        artifact_manager.save_trace(trace)

        # Save outputs
        artifact_manager.save_outputs(final_outputs)

        # Update run status
        artifact_manager.update_run_status(
            status="completed" if not execution_error else "failed",
            success=execution_error is None,
            error_summary=str(execution_error) if execution_error else None,
        )

        if verbose:
            print(f"Artifacts saved to: {artifact_manager.run_dir}")

    result = ExecutionResult(outputs=final_outputs, trace=trace, error=execution_error)
    return result


async def _execute_node_async(
    node_id: str,
    project: Project,
    dag: DAG,
    node_outputs: dict[str, dict[str, Any]],
    registry: Any,
    tool_runner: PythonToolRunner,
    dry_run: bool,
    verbose: bool,
    resume_sessions: dict[str, str] | None,
    on_agent_message: Callable[[str, Any], None] | None,
    checkpoint_dir: str | Path | None,
    artifact_manager: ArtifactManager | None,
    checkpoint: "Checkpoint | None",
) -> _NodeExecutionResult:
    """Execute a single node asynchronously. Returns result without raising."""
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
            return _NodeExecutionResult(
                node_id=node_id,
                node_trace=node_trace,
                skipped=True,
            )

        # Handle different node types - wrap sync operations in to_thread
        if node.type == "input":
            node_trace.output = node_outputs.get(node_id, {})

        elif node.type == "output":
            node_trace.input = _gather_inputs(node_id, dag, node_outputs)
            node_trace.output = node_trace.input

        elif node.type == "prompt":
            # Run prompt execution in thread pool (I/O-bound)
            await asyncio.to_thread(
                _execute_prompt_node,
                node_id, project, dag, node_outputs, node_trace, registry, dry_run
            )

        elif node.type == "tool":
            # Run tool execution in thread pool
            await asyncio.to_thread(
                _execute_tool_node,
                node_id, project, dag, node_outputs, node_trace, tool_runner
            )

        elif node.type == "agent":
            session_to_resume = resume_sessions.get(node_id) if resume_sessions else None
            # Agent execution already supports async via asyncio.run inside
            await asyncio.to_thread(
                _execute_agent_node,
                node_id, project, dag, node_outputs, node_trace,
                dry_run, session_to_resume, on_agent_message
            )

        elif node.type == "branch":
            # Branch nodes run sub-workflows
            await asyncio.to_thread(
                _execute_branch_node,
                node_id, project, dag, node_outputs, node_trace,
                dry_run, verbose, resume_sessions, on_agent_message,
                checkpoint_dir, artifact_manager, checkpoint
            )

        node_trace.end_time = _now_iso()
        return _NodeExecutionResult(
            node_id=node_id,
            node_trace=node_trace,
            output=node_trace.output,
        )

    except Exception as e:
        node_trace.error = str(e)
        node_trace.error_type = type(e).__name__
        node_trace.end_time = _now_iso()
        return _NodeExecutionResult(
            node_id=node_id,
            node_trace=node_trace,
            error=e,
        )


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

    # Validate required inputs are present
    _validate_required_inputs(gathered, prompt_node)

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

        # Include both text (raw JSON string) and parsed schema fields
        node_trace.output = {"text": result.content, **parsed}
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
    resume_session: str | None = None,
    on_message: Callable[[str, Any], None] | None = None,
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

    # Validate required inputs are present
    _validate_required_inputs(gathered, agent_node.prompt_node)

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
        resume_session=resume_session,
        on_message=on_message,
    )

    # Extract output and metrics from AgentResult
    node_trace.output = result.output
    node_trace.tokens = result.tokens
    node_trace.cost_usd = result.cost_usd
    node_trace.session_id = result.session_id
    node_trace.num_turns = result.num_turns


def _execute_branch_node(
    node_id: str,
    project: Project,
    dag: DAG,
    node_outputs: dict[str, dict[str, Any]],
    node_trace: NodeTrace,
    dry_run: bool,
    verbose: bool,
    resume_sessions: dict[str, str] | None = None,
    on_agent_message: Callable[[str, Any], None] | None = None,
    checkpoint_dir: str | Path | None = None,
    artifact_manager: ArtifactManager | None = None,
    checkpoint: "Checkpoint | None" = None,
) -> None:
    """Execute a branch node (sub-workflow call with optional looping).

    Branch nodes execute another workflow with the gathered inputs.
    If `loop_while` is specified, the workflow repeats until the condition
    is false or `max_iterations` is reached.

    Loop behavior:
    - Each iteration receives the previous iteration's outputs as inputs
    - Iteration state is saved to artifacts if artifact_manager is provided
    - The loop condition is evaluated after each iteration
    - Loop terminates when condition is false or max_iterations reached
    """
    from .project import load_project

    branch_node = project.branches.get(node_id)
    if not branch_node:
        raise TridentError(f"Branch definition not found: {node_id}")

    # Gather inputs from upstream nodes
    gathered = _gather_inputs(node_id, dag, node_outputs)
    node_trace.input = gathered

    # Evaluate pre-condition (skip if false)
    if branch_node.condition:
        context = {"output": gathered, **gathered}
        try:
            should_execute = evaluate(branch_node.condition, context)
        except Exception as e:
            raise BranchError(
                f"Failed to evaluate branch condition: {branch_node.condition}",
                cause=e,
            ) from e

        if not should_execute:
            node_trace.skipped = True
            node_trace.output = gathered  # Pass through inputs as outputs
            if verbose:
                print(f"  Branch {node_id} skipped (condition false)")
            return

    if dry_run:
        # Dry run: skip actual execution, pass through inputs
        node_trace.output = {"dry_run": True, **gathered}
        return

    # Resolve workflow path
    if branch_node.workflow_path == "self":
        # Self-recursion: re-execute the current project
        sub_project = project
    else:
        # External workflow: load from path
        workflow_path = project.root / branch_node.workflow_path
        if not workflow_path.exists():
            raise BranchError(f"Sub-workflow not found: {workflow_path}")
        sub_project = load_project(workflow_path)

    # Determine starting iteration (for resumption)
    # branch_states stores the last COMPLETED iteration, so we start at +1
    start_iteration = 0
    if checkpoint and node_id in checkpoint.branch_states:
        start_iteration = checkpoint.branch_states[node_id] + 1
        if verbose:
            print(f"  Resuming branch {node_id} from iteration {start_iteration}")

    # Execute with optional looping
    current_inputs = gathered
    iteration = start_iteration
    final_outputs: dict[str, Any] = {}

    while True:
        if verbose:
            if branch_node.loop_while:
                print(f"  [{node_id}] Iteration {iteration + 1}/{branch_node.max_iterations}")
            else:
                print(f"  Executing sub-workflow: {branch_node.workflow_path}")

        iteration_start = _now_iso()

        # Determine sub-workflow artifact dir (nested under branch iteration)
        sub_artifact_dir = None
        if artifact_manager:
            sub_artifact_dir = artifact_manager.branches_dir(node_id) / f"iter_{iteration}"

        # Execute sub-workflow
        sub_result = run(
            project=sub_project,
            inputs=current_inputs,
            dry_run=dry_run,
            verbose=verbose,
            resume_sessions=resume_sessions,
            on_agent_message=on_agent_message,
            checkpoint_dir=checkpoint_dir,
            artifact_dir=sub_artifact_dir,
        )

        iteration_end = _now_iso()

        # Save iteration state if artifact manager is available
        if artifact_manager:
            from .artifacts import BranchIterationState

            iteration_state = BranchIterationState(
                branch_id=node_id,
                iteration=iteration,
                inputs=current_inputs,
                outputs=sub_result.outputs,
                started_at=iteration_start,
                ended_at=iteration_end,
                success=sub_result.success,
                error=str(sub_result.error) if sub_result.error else None,
            )
            artifact_manager.save_branch_iteration(node_id, iteration_state)

        # Update checkpoint with current iteration and save for crash recovery
        if checkpoint:
            checkpoint.branch_states[node_id] = iteration
            checkpoint.updated_at = _now_iso()
            # Save checkpoint if checkpoint_dir is available
            if checkpoint_dir:
                checkpoint_path = Path(checkpoint_dir) if isinstance(checkpoint_dir, str) else checkpoint_dir
                checkpoint.save(checkpoint_path)

        if not sub_result.success:
            raise BranchError(
                f"Sub-workflow failed at iteration {iteration + 1}: {sub_result.error}",
                cause=sub_result.error,
                iteration=iteration,
                max_iterations=branch_node.max_iterations,
            )

        # Flatten outputs from sub-workflow
        # sub_result.outputs has shape {"output_node_id": {...}}
        # For loops, we need flat access to values
        raw_outputs = sub_result.outputs
        if len(raw_outputs) == 1:
            # Single output node - use its contents directly
            final_outputs = next(iter(raw_outputs.values()))
            if not isinstance(final_outputs, dict):
                final_outputs = raw_outputs
        else:
            # Multiple output nodes or complex structure - flatten all values
            final_outputs = {}
            for node_outputs in raw_outputs.values():
                if isinstance(node_outputs, dict):
                    final_outputs.update(node_outputs)
                else:
                    final_outputs = raw_outputs
                    break

        # If no loop_while, we're done after one iteration
        if not branch_node.loop_while:
            break

        # Evaluate loop condition
        context = {"output": final_outputs, **final_outputs}
        try:
            should_continue = evaluate(branch_node.loop_while, context)
        except Exception as e:
            raise BranchError(
                f"Failed to evaluate loop condition: {branch_node.loop_while}",
                cause=e,
                iteration=iteration,
                max_iterations=branch_node.max_iterations,
            ) from e

        if not should_continue:
            if verbose:
                print(f"  [{node_id}] Loop condition false, stopping after {iteration + 1} iterations")
            break

        iteration += 1

        # Check max iterations
        if iteration >= branch_node.max_iterations:
            raise BranchError(
                f"Max iterations ({branch_node.max_iterations}) reached",
                iteration=iteration,
                max_iterations=branch_node.max_iterations,
            )

        # Use outputs as inputs for next iteration
        current_inputs = final_outputs

    # Output is the final iteration's outputs
    node_trace.output = final_outputs
