"""Trident error types and exit codes."""

from enum import IntEnum
from typing import Any


class ExitCode(IntEnum):
    """Exit codes per SPEC-1 Section 4.5.2."""

    SUCCESS = 0
    RUNTIME_ERROR = 1
    VALIDATION_ERROR = 2
    PROVIDER_ERROR = 3
    TIMEOUT = 4  # Signal wait timeout


class TridentError(Exception):
    """Base error for all Trident errors."""

    exit_code: ExitCode = ExitCode.RUNTIME_ERROR

    def __str__(self) -> str:
        return super().__str__()


class ParseError(TridentError):
    """Error parsing project files."""

    exit_code = ExitCode.VALIDATION_ERROR


class ValidationError(TridentError):
    """Error validating project structure or data."""

    exit_code = ExitCode.VALIDATION_ERROR


class DAGError(ValidationError):
    """Error in DAG structure (cycles, missing nodes)."""

    pass


class ProviderError(TridentError):
    """Error from model provider."""

    exit_code = ExitCode.PROVIDER_ERROR

    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class SchemaValidationError(TridentError):
    """Output doesn't match declared schema."""

    exit_code = ExitCode.RUNTIME_ERROR


class ConditionError(TridentError):
    """Error evaluating edge condition."""

    exit_code = ExitCode.RUNTIME_ERROR


class ToolError(TridentError):
    """Error executing a tool."""

    exit_code = ExitCode.RUNTIME_ERROR


class NodeExecutionError(TridentError):
    """Error during node execution with full context.

    This error wraps the underlying cause and provides context about
    which node failed, what inputs it received, and what went wrong.
    """

    exit_code = ExitCode.RUNTIME_ERROR

    def __init__(
        self,
        node_id: str,
        node_type: str,
        message: str,
        cause: Exception | None = None,
        inputs: dict[str, Any] | None = None,
    ):
        self.node_id = node_id
        self.node_type = node_type
        self.cause = cause
        self.inputs = inputs or {}
        self.cause_type = type(cause).__name__ if cause else None

        # Inherit exit code from cause if it's a TridentError
        if cause and isinstance(cause, TridentError):
            self.exit_code = cause.exit_code

        super().__init__(message)

    def __str__(self) -> str:
        parts = [f"Node '{self.node_id}' ({self.node_type}) failed: {self.args[0]}"]
        if self.cause:
            parts.append(f"  Caused by {self.cause_type}: {self.cause}")
        if self.inputs:
            # Truncate large inputs for readability
            input_summary = {k: _truncate(v) for k, v in self.inputs.items()}
            parts.append(f"  Inputs: {input_summary}")
        return "\n".join(parts)


class BranchError(TridentError):
    """Error executing a branch node (sub-workflow call).

    This error is raised when a branch node fails, either due to:
    - Sub-workflow execution failure
    - Max iterations exceeded
    - Condition evaluation error
    """

    exit_code = ExitCode.RUNTIME_ERROR

    def __init__(
        self,
        message: str,
        iteration: int = 0,
        max_iterations: int = 0,
        cause: Exception | None = None,
    ):
        super().__init__(message)
        self.iteration = iteration
        self.max_iterations = max_iterations
        self.cause = cause

    def __str__(self) -> str:
        parts = [self.args[0]]
        if self.iteration > 0:
            parts.append(f"  Iteration: {self.iteration}/{self.max_iterations}")
        if self.cause:
            parts.append(f"  Caused by: {type(self.cause).__name__}: {self.cause}")
        return "\n".join(parts)


def _truncate(value: Any, max_len: int = 100) -> Any:
    """Truncate long values for error display."""
    if isinstance(value, str) and len(value) > max_len:
        return value[:max_len] + "..."
    if isinstance(value, (list, dict)) and len(str(value)) > max_len:
        return f"<{type(value).__name__} with {len(value)} items>"
    return value
