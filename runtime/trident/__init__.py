"""Trident - Lightweight agent orchestration runtime."""

from .artifacts import (
    ArtifactConfig,
    ArtifactManager,
    BranchIterationState,
    RunEntry,
    RunManifest,
    RunMetadata,
    find_latest_run,
    get_artifact_manager,
)
from .errors import (
    ConditionError,
    DAGError,
    ExitCode,
    NodeExecutionError,
    ParseError,
    ProviderError,
    SchemaValidationError,
    ToolError,
    TridentError,
    ValidationError,
)
from .executor import (
    Checkpoint,
    CheckpointNodeData,
    ExecutionResult,
    ExecutionTrace,
    NodeTrace,
    run,
)
from .project import Project, load_project

__version__ = "0.1.0"

__all__ = [
    # Project loading
    "load_project",
    "run",
    "Project",
    # Execution results
    "ExecutionResult",
    "ExecutionTrace",
    "NodeTrace",
    "Checkpoint",
    "CheckpointNodeData",
    # Artifacts
    "ArtifactConfig",
    "ArtifactManager",
    "BranchIterationState",
    "RunEntry",
    "RunManifest",
    "RunMetadata",
    "find_latest_run",
    "get_artifact_manager",
    # Errors
    "TridentError",
    "ParseError",
    "ValidationError",
    "DAGError",
    "ProviderError",
    "SchemaValidationError",
    "ConditionError",
    "ToolError",
    "NodeExecutionError",
    "ExitCode",
]
