# Trident Telemetry

Real-time workflow observability through structured event streaming.

## Overview

Trident's telemetry system emits structured events during workflow execution, enabling:
- **Real-time monitoring** of long-running workflows
- **Debugging** with complete execution context
- **Audit trails** for compliance and analysis
- **Performance analysis** via timing and token metrics
- **Log aggregation** integration for centralized monitoring

## Quick Start

Enable telemetry with the `--telemetry` flag:

```bash
# JSON Lines output to stdout (default)
trident project run myworkflow --telemetry

# Human-readable format
trident project run myworkflow --telemetry --telemetry-format human

# Write to file
trident project run myworkflow --telemetry --telemetry-file workflow.log

# Both file and stdout
trident project run myworkflow --telemetry --telemetry-file workflow.log --telemetry-stdout

# Filter by level
trident project run myworkflow --telemetry --telemetry-level warning
```

## Output Formats

### JSON Lines (jsonl)

One JSON object per line, machine-readable:

```json
{"timestamp": "2026-01-23T10:15:30.123Z", "run_id": "abc123", "event": "workflow_started", "level": "INFO", "data": {"name": "my-workflow", "entrypoint": "main"}}
{"timestamp": "2026-01-23T10:15:30.456Z", "run_id": "abc123", "event": "node_started", "level": "INFO", "node_id": "input", "data": {"type": "input"}}
{"timestamp": "2026-01-23T10:15:30.789Z", "run_id": "abc123", "event": "node_completed", "level": "INFO", "node_id": "input", "data": {"type": "input", "duration_ms": 333, "input_tokens": 0, "output_tokens": 0}}
```

### Human-Readable (human)

Structured text format:

```
[2026-01-23T10:15:30.123] [INFO] WORKFLOW_STARTED run=abc123 name=my-workflow entrypoint=main
[2026-01-23T10:15:30.456] [INFO] NODE_STARTED run=abc123 node=input type=input
[2026-01-23T10:15:30.789] [INFO] NODE_COMPLETED run=abc123 node=input type=input duration_ms=333 input_tokens=0 output_tokens=0
```

## Event Types

### Lifecycle Events

| Event | Level | Description | Data Fields |
|-------|-------|-------------|-------------|
| `workflow_started` | INFO | Workflow execution begins | `name`, `entrypoint`, `dry_run` |
| `workflow_completed` | INFO | Workflow execution succeeds | `name`, `duration_ms` |
| `workflow_failed` | ERROR | Workflow execution fails | `name`, `error`, `duration_ms` |

### Node Events

| Event | Level | Description | Data Fields |
|-------|-------|-------------|-------------|
| `node_started` | INFO | Node execution begins | `type` |
| `node_completed` | INFO | Node execution succeeds | `type`, `duration_ms`, `input_tokens`, `output_tokens` |
| `node_failed` | ERROR | Node execution fails | `type`, `error`, `error_type` |
| `node_skipped` | INFO | Node skipped due to condition | `reason` |

### State Events

| Event | Level | Description | Data Fields |
|-------|-------|-------------|-------------|
| `checkpoint_saved` | INFO | Checkpoint persisted | `completed_nodes`, `pending_nodes`, `total_cost_usd` |
| `signal_emitted` | INFO | Orchestration signal sent | `signal_type`, `workflow` |
| `branch_iteration` | INFO | Branch loop iteration | `iteration`, `max_iterations` |

### Agent Events

| Event | Level | Description | Data Fields |
|-------|-------|-------------|-------------|
| `agent_turn_started` | INFO | Agent turn begins | `turn_number` |
| `agent_turn_completed` | INFO | Agent turn completes | `turn_number`, `tool_calls` |
| `agent_tool_called` | INFO | Agent invokes tool | `tool_name`, `tool_input` |

## Event Schema

Every telemetry event contains:

```typescript
{
  timestamp: string;      // ISO 8601 UTC timestamp
  run_id: string;         // Execution run ID (UUID)
  event: string;          // Event type (snake_case)
  level: string;          // Severity: DEBUG, INFO, WARNING, ERROR
  node_id?: string;       // Node ID (if node-specific event)
  data: {                 // Event-specific payload
    [key: string]: any;
  }
}
```

## Configuration Options

### CLI Flags

| Flag | Description | Default |
|------|-------------|---------|
| `--telemetry` | Enable telemetry | disabled |
| `--telemetry-format` | Output format: `jsonl` or `human` | `jsonl` |
| `--telemetry-file PATH` | Write to file | stdout only |
| `--telemetry-stdout` | Write to stdout | true if no file, false if file |
| `--telemetry-level` | Minimum level: `debug`, `info`, `warning`, `error` | `info` |

### Environment Variables

```bash
export TRIDENT_TELEMETRY_ENABLED=true
export TRIDENT_TELEMETRY_FORMAT=jsonl
export TRIDENT_TELEMETRY_FILE=/var/log/trident/workflow.log
export TRIDENT_TELEMETRY_LEVEL=info
```

## Use Cases

### Real-Time Monitoring During Development

Watch workflow progress as it executes:

```bash
trident project run myworkflow --telemetry --telemetry-format human
```

### Production Audit Trail

Log all execution events to file:

```bash
trident project run myworkflow \
  --telemetry \
  --telemetry-file /var/log/trident/$(date +%Y%m%d-%H%M%S).log
```

### Remote Monitoring via Tail

Monitor remote workflow execution:

```bash
ssh production-server "tail -f /var/log/trident/workflow.log | grep ERROR"
```

### Log Aggregation

Parse JSON Lines for ingestion into log aggregation systems:

```bash
# Stream to Splunk
trident project run myworkflow --telemetry | splunk-forwarder

# Parse with jq
cat workflow.log | jq 'select(.event=="node_failed")'
```

### Performance Analysis

Extract timing metrics:

```bash
cat workflow.log | \
  jq -r 'select(.event=="node_completed") | [.node_id, .data.duration_ms] | @csv' | \
  sort -t, -k2 -n
```

### Error Debugging

Find failed nodes with full context:

```bash
cat workflow.log | jq 'select(.level=="ERROR")'
```

## Python API

Use telemetry programmatically:

```python
from trident import load_project, run
from trident.telemetry import TelemetryConfig, TelemetryLevel

# Configure telemetry
config = TelemetryConfig(
    enabled=True,
    format="jsonl",
    file_path="workflow.log",
    level=TelemetryLevel.INFO,
)

# Run with telemetry
project = load_project("./myworkflow")
result = run(project, inputs={}, telemetry_config=config)
```

## Performance

Telemetry is designed for minimal overhead:
- **<1% CPU overhead** when enabled
- **Line-buffered I/O** for immediate availability
- **Zero-cost abstraction** when disabled
- **Async-safe** for parallel node execution

## Best Practices

1. **Use JSON Lines in production** for machine parsing
2. **Use human format during development** for readability
3. **Write to files** for persistent logs
4. **Set appropriate level** (`warning` or `error` for production to reduce volume)
5. **Rotate log files** to prevent disk exhaustion
6. **Parse with jq** for analysis and filtering
7. **Integrate with log aggregation** for centralized monitoring

## Examples

### Filter by Node Type

```bash
cat workflow.log | jq 'select(.data.type=="prompt")'
```

### Calculate Total Tokens

```bash
cat workflow.log | \
  jq -s 'map(select(.event=="node_completed")) |
         map(.data.input_tokens + .data.output_tokens) |
         add'
```

### Find Slowest Nodes

```bash
cat workflow.log | \
  jq -r 'select(.event=="node_completed") |
         "\(.data.duration_ms)\t\(.node_id)"' | \
  sort -rn | head -5
```

### Extract Error Messages

```bash
cat workflow.log | \
  jq -r 'select(.event=="node_failed") |
         "\(.node_id): \(.data.error)"'
```

## Troubleshooting

### No telemetry output

Check that `--telemetry` flag is set:
```bash
trident project run myworkflow --telemetry
```

### File not created

Verify parent directory exists and has write permissions:
```bash
mkdir -p /var/log/trident
chmod 755 /var/log/trident
```

### Telemetry to stdout and file

Explicitly enable stdout when using file:
```bash
trident project run myworkflow \
  --telemetry \
  --telemetry-file workflow.log \
  --telemetry-stdout
```

## Future Enhancements

Planned features:
- **Structured logging backends** (Splunk, Datadog, CloudWatch)
- **Real-time streaming** (WebSocket, SSE)
- **Custom event hooks** in workflows
- **Distributed tracing** (OpenTelemetry)
- **Metrics export** (Prometheus)

## Related

- [SKILL.md](../SKILL.md) - Workflow authoring guide
- [README.md](../README.md) - Project overview
- [TELEMETRY_PLAN.md](./TELEMETRY_PLAN.md) - Implementation plan
