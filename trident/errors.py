"""Trident error types and exit codes."""

from dataclasses import dataclass
from enum import IntEnum
from typing import Any


class ExitCode(IntEnum):
    """Exit codes per SPEC-1 Section 4.5.2."""
    SUCCESS = 0
    RUNTIME_ERROR = 1
    VALIDATION_ERROR = 2
    PROVIDER_ERROR = 3


class TridentError(Exception):
    """Base error for all Trident errors."""
    exit_code: ExitCode = ExitCode.RUNTIME_ERROR


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
