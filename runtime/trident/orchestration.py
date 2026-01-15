"""Workflow orchestration utilities.

Provides functionality for coordinating multiple workflow runs:
- Signal waiting (wait for other workflows to complete)
- Signal file resolution
"""

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .artifacts import Signal


@dataclass
class WaitConfig:
    """Configuration for signal waiting."""

    signals: list[Path] = field(default_factory=list)
    timeout_seconds: float = 300.0
    poll_interval: float = 5.0


class SignalTimeoutError(Exception):
    """Raised when waiting for signals times out."""

    def __init__(self, missing_signals: list[str], timeout: float):
        self.missing_signals = missing_signals
        self.timeout = timeout
        super().__init__(
            f"Timed out after {timeout}s waiting for signals: {', '.join(missing_signals)}"
        )


def resolve_signal_path(signal_spec: str, project_root: Path) -> Path:
    """Resolve a signal specification to a file path.

    Supports:
    - signal:<workflow>.<type> - Look in .trident/signals/<workflow>.<type>
    - Relative paths - Resolved against project root
    - Absolute paths - Used as-is

    Args:
        signal_spec: Signal specification string
        project_root: Root directory of the project

    Returns:
        Resolved Path to the signal file
    """
    if signal_spec.startswith("signal:"):
        # signal:workflow.ready -> .trident/signals/workflow.ready
        signal_name = signal_spec[7:]
        return project_root / ".trident" / "signals" / signal_name
    else:
        path = Path(signal_spec)
        if path.is_absolute():
            return path
        return project_root / path


def wait_for_signals(
    config: WaitConfig,
    verbose: bool = False,
) -> dict[str, Signal]:
    """Poll for all signals to be present.

    Blocks until all specified signal files exist, or timeout is reached.

    Args:
        config: Wait configuration with signals, timeout, and poll interval
        verbose: If True, print progress messages

    Returns:
        Dict mapping signal path string to loaded Signal data

    Raises:
        SignalTimeoutError: If timeout exceeded before all signals appear
    """
    if not config.signals:
        return {}

    start = time.monotonic()
    results: dict[str, Signal] = {}

    while True:
        elapsed = time.monotonic() - start
        if elapsed > config.timeout_seconds:
            missing = [str(s) for s in config.signals if str(s) not in results]
            raise SignalTimeoutError(missing, config.timeout_seconds)

        for signal_path in config.signals:
            path_str = str(signal_path)
            if path_str in results:
                continue
            if signal_path.exists():
                try:
                    results[path_str] = Signal.load(signal_path)
                    if verbose:
                        print(f"Signal found: {signal_path}")
                except Exception:
                    # Signal file exists but couldn't be parsed - skip for now
                    pass

        if len(results) == len(config.signals):
            return results

        if verbose:
            remaining = len(config.signals) - len(results)
            print(f"Waiting for {remaining} signal(s)... ({elapsed:.1f}s elapsed)")

        time.sleep(config.poll_interval)


def wait_for_signal_files(
    signal_paths: list[str | Path],
    project_root: Path,
    timeout: float = 300.0,
    poll_interval: float = 5.0,
    verbose: bool = False,
) -> dict[str, Signal]:
    """Convenience function to wait for multiple signals.

    Args:
        signal_paths: List of signal paths or specifications
        project_root: Root directory of the project (for resolving relative paths)
        timeout: Maximum time to wait in seconds
        poll_interval: How often to check for signals
        verbose: If True, print progress messages

    Returns:
        Dict mapping signal path string to loaded Signal data

    Raises:
        SignalTimeoutError: If timeout exceeded before all signals appear
    """
    resolved_paths = []
    for spec in signal_paths:
        if isinstance(spec, str):
            resolved_paths.append(resolve_signal_path(spec, project_root))
        else:
            resolved_paths.append(spec)

    config = WaitConfig(
        signals=resolved_paths,
        timeout_seconds=timeout,
        poll_interval=poll_interval,
    )
    return wait_for_signals(config, verbose=verbose)


def check_signals_ready(
    signal_paths: list[str | Path],
    project_root: Path,
) -> tuple[bool, list[str]]:
    """Check if all signals are ready without blocking.

    Args:
        signal_paths: List of signal paths or specifications
        project_root: Root directory of the project

    Returns:
        Tuple of (all_ready, missing_signals)
    """
    missing = []
    for spec in signal_paths:
        if isinstance(spec, str):
            path = resolve_signal_path(spec, project_root)
        else:
            path = spec
        if not path.exists():
            missing.append(str(spec))

    return len(missing) == 0, missing


def get_signal_info(signal_path: Path) -> dict[str, Any] | None:
    """Get information from a signal file if it exists.

    Args:
        signal_path: Path to signal file

    Returns:
        Signal data as dict, or None if signal doesn't exist
    """
    if not signal_path.exists():
        return None
    try:
        signal = Signal.load(signal_path)
        return signal.to_dict()
    except Exception:
        return None
