"""Unified artifact management for Trident runs.

Provides centralized storage for all runtime artifacts:
- Checkpoints (execution state for resumption)
- Traces (detailed execution metrics)
- Outputs (final results)
- Metadata (run information)
- Branch iteration state (for looping workflows)

All artifacts are stored in `.trident/runs/{run_id}/` by default.
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .executor import Checkpoint, ExecutionTrace


@dataclass
class ArtifactConfig:
    """Configuration for artifact persistence."""

    base_dir: Path  # Usually project_root / ".trident"
    persist_trace: bool = True
    persist_outputs: bool = True
    persist_checkpoint: bool = True
    persist_branch_state: bool = True


@dataclass
class RunEntry:
    """Entry in the run manifest."""

    run_id: str
    project_name: str
    entrypoint: str | None
    status: str  # "running", "completed", "failed", "interrupted"
    started_at: str
    ended_at: str | None = None
    success: bool | None = None
    error_summary: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunEntry":
        """Create from dict."""
        return cls(**data)


@dataclass
class RunManifest:
    """Index of all runs in a project."""

    version: str = "1"
    runs: list[RunEntry] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "RunManifest":
        """Load manifest from disk."""
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text())
            runs = [RunEntry.from_dict(r) for r in data.get("runs", [])]
            return cls(version=data.get("version", "1"), runs=runs)
        except (json.JSONDecodeError, KeyError):
            # Corrupted manifest - start fresh
            return cls()

    def save(self, path: Path) -> None:
        """Save manifest to disk."""
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": self.version,
            "runs": [r.to_dict() for r in self.runs],
        }
        path.write_text(json.dumps(data, indent=2))

    def add_run(self, entry: RunEntry) -> None:
        """Add a new run entry."""
        self.runs.append(entry)

    def update_run(self, run_id: str, **updates: Any) -> None:
        """Update an existing run entry."""
        for run in self.runs:
            if run.run_id == run_id:
                for key, value in updates.items():
                    if hasattr(run, key):
                        setattr(run, key, value)
                return

    def get_latest(self) -> RunEntry | None:
        """Get the most recent run."""
        if not self.runs:
            return None
        return self.runs[-1]

    def get_run(self, run_id: str) -> RunEntry | None:
        """Get a run by ID."""
        for run in self.runs:
            if run.run_id == run_id:
                return run
        return None


@dataclass
class RunMetadata:
    """Metadata about a single run."""

    run_id: str
    project_name: str
    project_root: str
    entrypoint: str | None
    inputs: dict[str, Any]
    started_at: str
    ended_at: str | None = None
    trident_version: str = "0.1"

    def save(self, path: Path) -> None:
        """Save metadata to disk."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, default=str))

    @classmethod
    def load(cls, path: Path) -> "RunMetadata":
        """Load metadata from disk."""
        data = json.loads(path.read_text())
        return cls(**data)


@dataclass
class BranchIterationState:
    """State for a single branch iteration.

    Used for tracking progress through loops and enabling
    resumption from a specific iteration.
    """

    branch_id: str
    iteration: int
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    started_at: str
    ended_at: str | None = None
    success: bool = True
    error: str | None = None

    def save(self, path: Path) -> None:
        """Save iteration state to disk."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, default=str))

    @classmethod
    def load(cls, path: Path) -> "BranchIterationState":
        """Load iteration state from disk."""
        data = json.loads(path.read_text())
        return cls(**data)


def _now_iso() -> str:
    """Get current time as ISO string."""
    return datetime.now(UTC).isoformat()


class ArtifactManager:
    """Manages artifact persistence for a run.

    Handles saving and loading of all artifacts for a single run:
    - checkpoint.json - execution state for resumption
    - trace.json - detailed execution metrics
    - outputs.json - final outputs
    - metadata.json - run information
    - branches/{branch_id}/iteration_{n}.json - loop state
    """

    def __init__(self, config: ArtifactConfig, run_id: str):
        self.config = config
        self.run_id = run_id
        self._manifest: RunManifest | None = None

    @property
    def runs_dir(self) -> Path:
        """Directory containing all runs."""
        return self.config.base_dir / "runs"

    @property
    def run_dir(self) -> Path:
        """Directory for this specific run."""
        return self.runs_dir / self.run_id

    @property
    def manifest_path(self) -> Path:
        """Path to the runs manifest."""
        return self.runs_dir / "manifest.json"

    @property
    def checkpoint_path(self) -> Path:
        """Path to checkpoint file."""
        return self.run_dir / "checkpoint.json"

    @property
    def trace_path(self) -> Path:
        """Path to trace file."""
        return self.run_dir / "trace.json"

    @property
    def outputs_path(self) -> Path:
        """Path to outputs file."""
        return self.run_dir / "outputs.json"

    @property
    def metadata_path(self) -> Path:
        """Path to metadata file."""
        return self.run_dir / "metadata.json"

    def branches_dir(self, branch_id: str) -> Path:
        """Directory for branch iteration states."""
        return self.run_dir / "branches" / branch_id

    def iteration_path(self, branch_id: str, iteration: int) -> Path:
        """Path to a specific iteration state file."""
        return self.branches_dir(branch_id) / f"iteration_{iteration}.json"

    def ensure_dirs(self) -> None:
        """Create all necessary directories."""
        self.run_dir.mkdir(parents=True, exist_ok=True)

    def _get_manifest(self) -> RunManifest:
        """Get or load the manifest."""
        if self._manifest is None:
            self._manifest = RunManifest.load(self.manifest_path)
        return self._manifest

    def _save_manifest(self) -> None:
        """Save the manifest to disk."""
        if self._manifest is not None:
            self._manifest.save(self.manifest_path)

    def register_run(
        self,
        project_name: str,
        entrypoint: str | None,
    ) -> None:
        """Register a new run in the manifest."""
        manifest = self._get_manifest()
        entry = RunEntry(
            run_id=self.run_id,
            project_name=project_name,
            entrypoint=entrypoint,
            status="running",
            started_at=_now_iso(),
        )
        manifest.add_run(entry)
        self._save_manifest()

    def update_run_status(
        self,
        status: str,
        success: bool | None = None,
        error_summary: str | None = None,
    ) -> None:
        """Update the run status in the manifest."""
        manifest = self._get_manifest()
        manifest.update_run(
            self.run_id,
            status=status,
            ended_at=_now_iso(),
            success=success,
            error_summary=error_summary,
        )
        self._save_manifest()

    def save_checkpoint(self, checkpoint: "Checkpoint") -> Path:
        """Save checkpoint to disk."""
        if not self.config.persist_checkpoint:
            return self.checkpoint_path

        self.ensure_dirs()

        data = {
            "run_id": checkpoint.run_id,
            "project_name": checkpoint.project_name,
            "started_at": checkpoint.started_at,
            "updated_at": checkpoint.updated_at,
            "status": checkpoint.status,
            "completed_nodes": {k: asdict(v) for k, v in checkpoint.completed_nodes.items()},
            "pending_nodes": checkpoint.pending_nodes,
            "total_cost_usd": checkpoint.total_cost_usd,
            "inputs": checkpoint.inputs,
            "entrypoint": checkpoint.entrypoint,
            "branch_states": getattr(checkpoint, "branch_states", {}),
        }
        self.checkpoint_path.write_text(json.dumps(data, indent=2, default=str))
        return self.checkpoint_path

    def load_checkpoint(self) -> "Checkpoint | None":
        """Load checkpoint from disk."""
        if not self.checkpoint_path.exists():
            return None

        from .executor import Checkpoint, CheckpointNodeData

        data = json.loads(self.checkpoint_path.read_text())
        completed_nodes = {
            k: CheckpointNodeData(**v) for k, v in data.get("completed_nodes", {}).items()
        }
        checkpoint = Checkpoint(
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
        )
        # Restore branch states if present
        if "branch_states" in data:
            checkpoint.branch_states = data["branch_states"]
        return checkpoint

    def save_trace(self, trace: "ExecutionTrace") -> Path:
        """Save execution trace to disk."""
        if not self.config.persist_trace:
            return self.trace_path

        self.ensure_dirs()
        data = trace.to_dict()
        self.trace_path.write_text(json.dumps(data, indent=2, default=str))
        return self.trace_path

    def save_outputs(self, outputs: dict[str, Any]) -> Path:
        """Save final outputs to disk."""
        if not self.config.persist_outputs:
            return self.outputs_path

        self.ensure_dirs()
        self.outputs_path.write_text(json.dumps(outputs, indent=2, default=str))
        return self.outputs_path

    def save_metadata(self, metadata: RunMetadata) -> Path:
        """Save run metadata to disk."""
        self.ensure_dirs()
        metadata.save(self.metadata_path)
        return self.metadata_path

    def save_branch_iteration(
        self,
        branch_id: str,
        state: BranchIterationState,
    ) -> Path:
        """Save branch iteration state to disk."""
        if not self.config.persist_branch_state:
            return self.iteration_path(branch_id, state.iteration)

        path = self.iteration_path(branch_id, state.iteration)
        state.save(path)
        return path

    def load_branch_iterations(self, branch_id: str) -> list[BranchIterationState]:
        """Load all iteration states for a branch."""
        branch_dir = self.branches_dir(branch_id)
        if not branch_dir.exists():
            return []

        iterations = []
        for path in sorted(branch_dir.glob("iteration_*.json")):
            try:
                iterations.append(BranchIterationState.load(path))
            except (json.JSONDecodeError, KeyError):
                continue
        return iterations

    def get_latest_iteration(self, branch_id: str) -> BranchIterationState | None:
        """Get the most recent iteration state for a branch."""
        iterations = self.load_branch_iterations(branch_id)
        return iterations[-1] if iterations else None


def get_artifact_manager(
    project_root: Path,
    run_id: str,
    artifact_dir: Path | None = None,
) -> ArtifactManager:
    """Create an artifact manager for a run.

    Args:
        project_root: Root directory of the project
        run_id: Unique run identifier
        artifact_dir: Custom artifact directory (default: project_root/.trident)

    Returns:
        Configured ArtifactManager
    """
    base_dir = artifact_dir if artifact_dir else project_root / ".trident"
    config = ArtifactConfig(base_dir=base_dir)
    return ArtifactManager(config, run_id)


def find_latest_run(project_root: Path) -> str | None:
    """Find the most recent run ID for a project.

    Args:
        project_root: Root directory of the project

    Returns:
        Run ID of the most recent run, or None if no runs exist
    """
    manifest_path = project_root / ".trident" / "runs" / "manifest.json"
    manifest = RunManifest.load(manifest_path)
    latest = manifest.get_latest()
    return latest.run_id if latest else None
