# Trident Runtime Telemetry Implementation Plan

## Purpose

Enable real-time observability of Trident workflow executions through structured, tail-friendly telemetry output. This will allow operators to monitor long-running workflows, debug issues as they occur, and maintain a complete audit trail of execution events without waiting for the workflow to complete or parsing JSON artifacts.

## Problem Statement

Currently, Trident provides comprehensive execution tracking through:
- JSON trace files saved after execution completes
- Console output with `--verbose` flag (limited detail)
- A monitoring dashboard (requires separate service)

However, there is no mechanism to:
- Stream execution events in real-time during workflow execution
- Tail workflow progress with structured, parseable output
- Audit execution events as they happen (especially critical for long-running workflows)
- Monitor workflows remotely via log aggregation systems

## Desired Outcome

A robust telemetry system that:

1. **Streams events in real-time** - Each significant execution event is emitted immediately when it occurs
2. **Is tail-friendly** - Output is line-delimited, structured, and suitable for `tail -f`
3. **Is parseable** - Uses JSON Lines format (one JSON object per line) for easy parsing
4. **Is comprehensive** - Captures all significant execution events (node start/end, errors, checkpoints, signals)
5. **Is configurable** - Can be enabled/disabled, filtered by event type, and routed to different outputs
6. **Is backward compatible** - Does not break existing trace/checkpoint mechanisms
7. **Supports multiple outputs** - Can write to stdout, files, or both simultaneously

## Key Requirements

### Functional Requirements

1. **Event Types** - Must capture at minimum:
   - Workflow start/end events
   - Node execution start/completion events
   - Input/output data for each node
   - Token usage and timing metrics
   - Error events with full context
   - Checkpoint save events
   - Signal emission events
   - Branch iteration events
   - Agent turn events (for multi-turn agent nodes)

2. **Event Structure** - Each telemetry event should contain:
   - ISO 8601 timestamp (UTC)
   - Event type identifier
   - Run ID (for correlation)
   - Node ID (if applicable)
   - Event-specific payload
   - Severity level (info, warning, error)

3. **Output Formats**:
   - **JSON Lines** (default): One JSON object per line, machine-readable
   - **Human-readable**: Structured text format for interactive use
   - Must be switchable via CLI flag

4. **Output Destinations**:
   - **stdout** (default for interactive use)
   - **File** (for persistent logging)
   - **Both** (log file + stdout for monitoring)
   - Must be configurable via CLI flags and environment variables

5. **Filtering**:
   - Filter by event type (e.g., only errors, only node events)
   - Filter by severity level
   - Configurable verbosity levels (minimal, normal, verbose, debug)

6. **Performance**:
   - Must not significantly impact execution performance
   - Buffered writes to avoid I/O blocking
   - Async emission where possible

### Non-Functional Requirements

1. **Backward Compatibility**:
   - Existing trace.json, checkpoint.json artifacts remain unchanged
   - Existing `--verbose` flag behavior preserved
   - Existing monitoring dashboard continues to work

2. **Testability**:
   - Telemetry can be captured and asserted in tests
   - Mock telemetry emitter for unit tests
   - Integration tests verify event stream correctness

3. **Extensibility**:
   - Easy to add new event types
   - Pluggable telemetry backends (file, network, observability platforms)
   - Custom event transformers/formatters

## Implementation Architecture

### Core Components

#### 1. **TelemetryEmitter** (New Module)

Central telemetry emission system responsible for:
- Accepting telemetry events from throughout the runtime
- Formatting events according to selected format (JSON Lines vs human-readable)
- Writing events to configured destinations (stdout, file)
- Buffering and flushing events appropriately
- Managing event filtering based on configuration

Key responsibilities:
- Provide simple API for emitting events: `emit(event_type, payload)`
- Handle serialization and formatting
- Manage output destinations and file handles
- Ensure thread-safety for concurrent event emission
- Provide context manager for lifecycle management

#### 2. **Event Schema** (New Module)

Defines telemetry event types and their structure:
- Enum of all event types
- Dataclass definitions for each event type
- Validation of event payloads
- Serialization helpers

Event categories:
- **Lifecycle Events**: workflow_started, workflow_completed, workflow_failed
- **Node Events**: node_started, node_completed, node_failed, node_skipped
- **Execution Events**: input_received, output_produced, condition_evaluated
- **Resource Events**: token_usage, cost_incurred, timing_metric
- **State Events**: checkpoint_saved, signal_emitted, branch_iteration
- **Agent Events**: agent_turn_started, agent_turn_completed, agent_tool_called

#### 3. **Configuration** (Enhanced)

Extend existing configuration system with telemetry options:
- Enable/disable telemetry
- Output format selection
- Output destination configuration
- Event filtering rules
- Verbosity levels

Configuration sources (in priority order):
1. CLI flags (highest priority)
2. Environment variables
3. Project manifest defaults
4. Runtime defaults (lowest priority)

#### 4. **Integration Points**

Inject telemetry emission at key points in execution flow:

**In `executor.py::run()`**:
- Emit workflow_started at beginning
- Emit workflow_completed/workflow_failed at end
- Emit checkpoint_saved after each checkpoint write
- Emit signal_emitted when signals are sent

**In node execution functions**:
- Emit node_started before execution
- Emit node_completed after success
- Emit node_failed on error
- Emit node_skipped when conditions not met
- Emit input_received with gathered inputs
- Emit output_produced with node outputs

**In `agents.py` (Agent SDK integration)**:
- Emit agent_turn_started for each agent turn
- Emit agent_turn_completed with turn results
- Emit agent_tool_called when tools are invoked

**In `orchestration.py`**:
- Emit signal_emitted when signals are written
- Emit signal_received when signals are detected

**In `artifacts.py`**:
- Emit checkpoint_saved after successful checkpoint write
- Emit artifact_saved for trace/output writes

### Event Format Specification

#### JSON Lines Format

Each line is a complete JSON object:

```
{"timestamp": "2025-01-23T10:15:30.123Z", "run_id": "abc123", "event": "workflow_started", "data": {"name": "my-workflow", "entrypoint": "main"}}
{"timestamp": "2025-01-23T10:15:30.456Z", "run_id": "abc123", "event": "node_started", "node_id": "input", "data": {"type": "input"}}
{"timestamp": "2025-01-23T10:15:30.789Z", "run_id": "abc123", "event": "node_completed", "node_id": "input", "data": {"duration_ms": 333, "output": {...}}}
```

Schema for each event:
- `timestamp`: ISO 8601 UTC timestamp
- `run_id`: Unique identifier for this execution
- `event`: Event type identifier (from Event enum)
- `level`: Severity level (INFO, WARNING, ERROR)
- `node_id`: Node identifier (if event is node-specific)
- `data`: Event-specific payload (varies by event type)

#### Human-Readable Format

Structured text output for interactive use:

```
[2025-01-23 10:15:30.123] [INFO] WORKFLOW_STARTED run=abc123 workflow=my-workflow
[2025-01-23 10:15:30.456] [INFO] NODE_STARTED run=abc123 node=input type=input
[2025-01-23 10:15:30.789] [INFO] NODE_COMPLETED run=abc123 node=input duration=333ms tokens=0
```

Format:
- Timestamp in brackets
- Severity level in brackets
- Event type in uppercase
- Key=value pairs for important fields
- Truncated output for large payloads

### CLI Interface

New flags for `trident project run`:

```bash
# Enable telemetry with JSON Lines output to stdout (default destination)
trident project run myworkflow --telemetry

# Enable telemetry with human-readable format
trident project run myworkflow --telemetry --telemetry-format human

# Write telemetry to file
trident project run myworkflow --telemetry --telemetry-file workflow.log

# Write telemetry to both stdout and file
trident project run myworkflow --telemetry --telemetry-file workflow.log --telemetry-stdout

# Filter to only show error events
trident project run myworkflow --telemetry --telemetry-filter error

# Set verbosity level (minimal, normal, verbose, debug)
trident project run myworkflow --telemetry --telemetry-level verbose

# Combine with existing flags
trident project run myworkflow --telemetry --verbose --trace
```

Environment variable alternatives:
```bash
export TRIDENT_TELEMETRY_ENABLED=true
export TRIDENT_TELEMETRY_FORMAT=jsonl
export TRIDENT_TELEMETRY_FILE=workflow.log
export TRIDENT_TELEMETRY_LEVEL=verbose
```

### Backward Compatibility Strategy

1. **Telemetry is opt-in**: By default, telemetry is disabled unless `--telemetry` flag or env var is set
2. **Existing flags unchanged**: `--verbose` and `--trace` continue to work as before
3. **Existing artifacts preserved**: trace.json and checkpoint.json remain unchanged
4. **No performance impact when disabled**: Zero-cost abstraction when telemetry is off
5. **Separate from console output**: Telemetry goes to separate stream from user-facing output

### Implementation Phases

#### Phase 1: Core Infrastructure
- Create TelemetryEmitter class with basic functionality
- Define Event schema and event types
- Implement JSON Lines formatter
- Add CLI flags for basic configuration
- Add integration point in executor.py for workflow lifecycle events

Validation criteria:
- Can emit workflow_started and workflow_completed events
- Events are written to stdout in JSON Lines format
- Can be enabled/disabled via CLI flag

#### Phase 2: Node-Level Events
- Add node execution event emission (started, completed, failed, skipped)
- Capture input/output data in events
- Capture timing and token metrics
- Add human-readable formatter

Validation criteria:
- All node executions emit corresponding events
- Input/output data is captured correctly
- Timing metrics match trace.json
- Human-readable format is clear and useful

#### Phase 3: Enhanced Features
- Add event filtering by type and level
- Add file output destination
- Add checkpoint and signal events
- Add agent turn events

Validation criteria:
- Can filter events by type (e.g., only errors)
- Can write to file, stdout, or both
- Agent executions show turn-by-turn progress

#### Phase 4: Polish and Documentation
- Add comprehensive tests for telemetry system
- Document event schema in TELEMETRY.md
- Update SKILL.md with telemetry usage examples
- Add example workflows demonstrating telemetry
- Performance testing and optimization

Validation criteria:
- Test coverage >80% for telemetry code
- Documentation is clear and comprehensive
- No performance regression in benchmarks

## Use Cases

### 1. Real-Time Monitoring During Development
Developer runs workflow with telemetry to stdout, watches progress in real-time:
```bash
trident project run myworkflow --telemetry --telemetry-format human
```

### 2. Production Audit Trail
Production workflow logs telemetry to file for compliance/debugging:
```bash
trident project run myworkflow --telemetry --telemetry-file /var/log/trident/runs.log
```

### 3. Remote Monitoring via Tail
Operator tails telemetry file on remote server:
```bash
ssh production-server "tail -f /var/log/trident/runs.log | grep ERROR"
```

### 4. Log Aggregation Integration
Telemetry file is ingested by log aggregation system (Splunk, ELK, etc.) for centralized monitoring and alerting.

### 5. Debugging Failed Workflows
When a workflow fails, telemetry log shows exactly which node failed and why, with full input/output context at the time of failure.

### 6. Performance Analysis
Parse telemetry JSON Lines to analyze node execution times, token usage, and identify bottlenecks:
```bash
cat workflow.log | jq -r 'select(.event=="node_completed") | [.node_id, .data.duration_ms] | @csv'
```

## Success Metrics

1. **Completeness**: All significant execution events are captured in telemetry
2. **Real-time**: Events are emitted within 100ms of occurrence
3. **Performance**: <5% overhead when telemetry is enabled, <0.1% when disabled
4. **Usability**: Developers can understand workflow progress from telemetry alone
5. **Reliability**: Telemetry system never causes workflow failures
6. **Adoption**: Telemetry is used in production deployments and developer workflows

## Future Enhancements (Out of Scope for Initial Implementation)

1. **Structured logging backends**: Support for sending telemetry to Splunk, Datadog, CloudWatch
2. **Real-time streaming**: WebSocket or SSE streaming for monitoring dashboard
3. **Telemetry aggregation**: Aggregate metrics across multiple runs
4. **Custom event hooks**: Allow user-defined telemetry events in workflows
5. **Distributed tracing**: OpenTelemetry integration for distributed workflows
6. **Metrics export**: Prometheus-compatible metrics endpoint

## Dependencies and Constraints

### Dependencies
- No new external dependencies required for basic implementation
- Optional: `rich` library for enhanced human-readable formatting
- Optional: `structlog` for structured logging integration

### Constraints
- Must maintain <5% performance overhead
- Must work in containerized environments (Docker, Kubernetes)
- Must handle file system errors gracefully (disk full, permissions)
- Must be thread-safe for concurrent node execution
- Must not buffer indefinitely (bounded buffers, flush on size/time)

## Risk Mitigation

### Risk: Performance Degradation
- **Mitigation**: Async I/O for telemetry writes, buffering, benchmarking in CI
- **Fallback**: Disable telemetry if overhead exceeds threshold

### Risk: Disk Space Exhaustion
- **Mitigation**: Log rotation support, configurable max file size
- **Fallback**: Gracefully handle write failures, continue execution

### Risk: Breaking Changes
- **Mitigation**: Opt-in design, comprehensive test coverage, beta testing
- **Fallback**: Feature flag to disable telemetry globally

### Risk: Event Ordering Issues
- **Mitigation**: Monotonic timestamps, sequence numbers in events
- **Fallback**: Document that some events may be out of order in high-concurrency scenarios

## Open Questions to Resolve

1. **Default behavior**: Should telemetry be enabled by default in future versions? (Current plan: opt-in)
2. **Event retention**: Should telemetry files be rotated/cleaned automatically?
3. **Sensitive data**: Should input/output data be redacted in telemetry? (PII, credentials)
4. **Event buffering**: What's the optimal buffer size for performance vs latency?
5. **Backward compatibility timeline**: When can we make telemetry default-enabled?

## Conclusion

This implementation will transform Trident from a batch-oriented workflow engine with post-execution observability into a real-time observable system with streaming telemetry. Operators will gain immediate visibility into workflow execution, enabling faster debugging, better production monitoring, and comprehensive audit trails without sacrificing performance or backward compatibility.
