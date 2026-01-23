"""Telemetry system for real-time workflow observability."""

import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, TextIO


class EventType(Enum):
    """Types of telemetry events."""

    # Lifecycle events
    WORKFLOW_STARTED = "workflow_started"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_FAILED = "workflow_failed"

    # Node events
    NODE_STARTED = "node_started"
    NODE_COMPLETED = "node_completed"
    NODE_FAILED = "node_failed"
    NODE_SKIPPED = "node_skipped"

    # Execution events
    INPUT_RECEIVED = "input_received"
    OUTPUT_PRODUCED = "output_produced"
    CONDITION_EVALUATED = "condition_evaluated"

    # Resource events
    TOKEN_USAGE = "token_usage"
    COST_INCURRED = "cost_incurred"
    TIMING_METRIC = "timing_metric"

    # State events
    CHECKPOINT_SAVED = "checkpoint_saved"
    SIGNAL_EMITTED = "signal_emitted"
    BRANCH_ITERATION = "branch_iteration"

    # Agent events
    AGENT_TURN_STARTED = "agent_turn_started"
    AGENT_TURN_COMPLETED = "agent_turn_completed"
    AGENT_TOOL_CALLED = "agent_tool_called"

    def to_string(self) -> str:
        """Convert EventType to snake_case string."""
        return self.value


class TelemetryLevel(Enum):
    """Severity levels for telemetry events."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass
class TelemetryEvent:
    """A single telemetry event."""

    event_type: EventType
    run_id: str
    level: TelemetryLevel
    data: dict[str, Any] = field(default_factory=dict)
    node_id: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert event to JSON-serializable dict."""
        result = {
            "timestamp": self.timestamp,
            "run_id": self.run_id,
            "event": self.event_type.to_string(),
            "level": self.level.value,
            "data": self.data,
        }
        if self.node_id is not None:
            result["node_id"] = self.node_id
        return result


@dataclass
class TelemetryConfig:
    """Configuration for telemetry system."""

    enabled: bool = False
    format: str = "jsonl"  # "jsonl" or "human"
    file_path: str | None = None
    stdout: bool = True
    level: TelemetryLevel = TelemetryLevel.INFO
    filter_events: list[EventType] | None = None


class TelemetryEmitter:
    """Central telemetry emission system.

    Manages formatting and writing of telemetry events to configured destinations.
    Thread-safe for concurrent event emission.
    """

    def __init__(
        self,
        config: TelemetryConfig,
        output_stream: TextIO | None = None,
    ):
        """Initialize telemetry emitter.

        Args:
            config: Telemetry configuration
            output_stream: Optional stream for output (default: stdout if config.stdout is True)
        """
        self.config = config
        self._output_stream = output_stream
        self._file_handle: TextIO | None = None

        # Open file if configured
        if config.enabled and config.file_path:
            file_path = Path(config.file_path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            self._file_handle = open(file_path, "a", buffering=1)  # Line buffered  # noqa: SIM115

    def __enter__(self) -> "TelemetryEmitter":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit - flush and close resources."""
        self.close()

    def emit(
        self,
        event_type: EventType,
        run_id: str,
        data: dict[str, Any] | None = None,
        node_id: str | None = None,
        level: TelemetryLevel | None = None,
    ) -> None:
        """Emit a telemetry event.

        Args:
            event_type: Type of event
            run_id: Execution run ID
            data: Event-specific payload
            node_id: Node ID if event is node-specific
            level: Event severity level (default: INFO)
        """
        if not self.config.enabled:
            return

        # Check event filter
        if self.config.filter_events and event_type not in self.config.filter_events:
            return

        event = TelemetryEvent(
            event_type=event_type,
            run_id=run_id,
            level=level or self.config.level,
            data=data or {},
            node_id=node_id,
        )

        self._write_event(event)

    def _write_event(self, event: TelemetryEvent) -> None:
        """Write an event to configured destinations."""
        if self.config.format == "jsonl":
            output_line = self._format_jsonl(event)
        else:  # human
            output_line = self._format_human(event)

        # Write to stdout if configured
        if self.config.stdout and self._output_stream is None:
            print(output_line, file=sys.stdout, flush=True)
        elif self._output_stream is not None:
            print(output_line, file=self._output_stream, flush=True)

        # Write to file if configured
        if self._file_handle:
            print(output_line, file=self._file_handle, flush=True)

    def _format_jsonl(self, event: TelemetryEvent) -> str:
        """Format event as JSON Lines (one JSON object per line)."""
        return json.dumps(event.to_dict(), default=str)

    def _format_human(self, event: TelemetryEvent) -> str:
        """Format event as human-readable text."""
        timestamp = event.timestamp[:23]  # Truncate microseconds
        level = event.level.value
        event_name = event.event_type.to_string().upper()

        # Build key=value pairs
        parts = [f"run={event.run_id}"]
        if event.node_id:
            parts.append(f"node={event.node_id}")

        # Add important data fields
        for key, value in event.data.items():
            # Skip large or complex data in human format
            if isinstance(value, (str, int, float, bool)) and not isinstance(value, bool):
                # Truncate long strings
                str_value = str(value)
                if len(str_value) > 50:
                    str_value = str_value[:47] + "..."
                parts.append(f"{key}={str_value}")
            elif isinstance(value, bool):
                parts.append(f"{key}={value}")

        parts_str = " ".join(parts)
        return f"[{timestamp}] [{level}] {event_name} {parts_str}"

    def close(self) -> None:
        """Close file handles and flush buffers."""
        if self._file_handle:
            self._file_handle.flush()
            self._file_handle.close()
            self._file_handle = None


# Global emitter instance (initialized by executor)
_global_emitter: TelemetryEmitter | None = None


def get_emitter() -> TelemetryEmitter | None:
    """Get the global telemetry emitter."""
    return _global_emitter


def set_emitter(emitter: TelemetryEmitter | None) -> None:
    """Set the global telemetry emitter."""
    global _global_emitter
    _global_emitter = emitter


def emit(
    event_type: EventType,
    run_id: str,
    data: dict[str, Any] | None = None,
    node_id: str | None = None,
    level: TelemetryLevel | None = None,
) -> None:
    """Emit a telemetry event using the global emitter.

    This is a convenience function for emitting events throughout the runtime.
    """
    emitter = get_emitter()
    if emitter:
        emitter.emit(event_type, run_id, data, node_id, level)
