# Trident Workflow Authoring Guide

## Overview

Trident is a Python-based LLM agent orchestration runtime that executes workflows as directed acyclic graphs (DAGs). This guide covers patterns for authoring Trident workflow manifests (`.tml` files).

## Manifest Structure

A Trident manifest (`agent.tml`) consists of:

- **Metadata**: `trident`, `name`, `description`, `version`
- **Defaults**: `model`, `temperature`, `max_tokens`
- **Entrypoints**: starting node(s)
- **Nodes**: workflow steps (`input`, `output`, `prompt`, `agent`, `branch`)
- **Edges**: connections between nodes with field mappings
- **Tools**: external functions (`python`, `shell`, `http`) - defined separately from nodes

## Output Contracts by Node Type

Understanding what each node type outputs is critical for writing correct edge mappings.

| Node Type | Output Fields | Notes |
|-----------|--------------|-------|
| `input` | Schema field names | Fields from the `schema:` definition |
| `prompt` (text) | `text` | Raw text response |
| `prompt` (json) | `text` + schema fields | `text` contains parsed JSON; schema fields also accessible |
| `tool` (dict return) | Dict keys directly | If function returns `{"count": 42}`, use `count` |
| `tool` (non-dict) | `output` | Wrapped as `{"output": value}` |
| `agent` | `text` + schema fields | Like prompt, depends on output format |
| `branch` | `output`, `text` | Sub-workflow output |

## Edge Mapping Patterns

### From Input Nodes

Input nodes output their schema fields directly:

```yaml
nodes:
  input:
    type: input
    schema:
      date: string, Date in YYYY-MM-DD format
      limit: number, Max results

edges:
  e1:
    from: input
    to: fetch_data
    mapping:
      query_date: date    # Use schema field names
      max_results: limit
```

### From Prompt Nodes

All prompts output a `text` field. JSON prompts also expose schema fields:

```yaml
# prompts/analyze.prompt has output.format: json with schema: {status, score}

edges:
  e1:
    from: analyze
    to: next_node
    mapping:
      result: text      # The full JSON object
      # OR access specific fields:
      current_status: status
      quality: score
```

### From Tool Nodes

Tools that return dicts expose their keys directly. Non-dict returns are wrapped in `output`:

```yaml
tools:
  get_metrics:
    type: python
    module: queries
    function: fetch_metrics  # Returns {"device_count": 42, "volume": 123.5}

  get_count:
    type: python
    module: utils
    function: simple_count   # Returns 42 (integer)

edges:
  # Dict return - use keys directly
  e1:
    from: get_metrics
    to: analyze
    mapping:
      devices: device_count
      vol: volume

  # Non-dict return - use 'output'
  e2:
    from: get_count
    to: report
    mapping:
      total: output
```

## Critical Rules

### 1. Tools Must Be in `tools:` Section

Tools are defined separately from nodes. The validator will error if you put a tool in `nodes:`:

```yaml
# WRONG - will error
nodes:
  fetch_data:
    type: tool
    module: queries
    function: get_data

# CORRECT
tools:
  fetch_data:
    type: python
    module: queries
    function: get_data
```

Tools are automatically available as nodes in edges - just reference them by name.

### 2. Validate Before Running

Always validate your manifest to catch mapping errors early:

```bash
# Basic validation - shows warnings
python -m trident project validate ./my-project

# Strict mode - warnings become errors (use in CI)
python -m trident project validate ./my-project --strict
```

### 3. Match Input Field Names Exactly

The target field in a mapping must match what the destination node expects:

```yaml
# If prompts/process.prompt has: input.content (required)

edges:
  e1:
    from: input
    to: process
    mapping:
      content: text    # 'content' must match the prompt's input field name
      # NOT: data: text  # This would fail - 'data' not expected
```

## Prompt File Structure

Prompts use YAML frontmatter for metadata and Jinja2 templates for the body:

```yaml
---
id: analyze
name: Data Analyzer
description: Analyze metrics and return insights

input:
  data:
    type: string
    required: true
  threshold:
    type: number
    required: false
    default: 0.5

output:
  format: json
  schema:
    status: string, One of "normal", "warning", "critical"
    score: number, Quality score between 0-100
    insights: array, List of insight strings
---
You are a data analyst. Analyze the following data:

{{data}}

Threshold for alerts: {{threshold}}

Return a JSON object with:
- status: "normal", "warning", or "critical"
- score: numeric quality score (0-100)
- insights: array of key observations

IMPORTANT: score must be a number, not a string.
```

**Tips for Structured Output:**
- Be explicit about types in schema descriptions
- Reinforce type requirements in the prompt body
- The LLM response is validated against the schema

## Complete Example

```yaml
trident: "0.1"
name: daily-report
description: Generate daily summary report

defaults:
  model: anthropic/claude-sonnet-4-20250514
  temperature: 0.7
  max_tokens: 4096

entrypoints:
  - input

nodes:
  input:
    type: input
    schema:
      date: string, Date in YYYY-MM-DD format (optional)

  output:
    type: output
    format: json

edges:
  # Input -> Tool
  e1:
    from: input
    to: fetch_data
    mapping:
      query_date: date

  # Tool -> Prompt
  e2:
    from: fetch_data
    to: analyze
    mapping:
      metrics: output  # Tool returns non-dict, use 'output'

  # Prompt -> Prompt
  e3:
    from: analyze
    to: generate_report
    mapping:
      analysis: text   # Prompt output uses 'text'
      status: status   # Or access schema fields directly

  # Prompt -> Output
  e4:
    from: generate_report
    to: output
    mapping:
      report: text

tools:
  fetch_data:
    type: python
    module: data_queries
    function: get_daily_data
    description: Query database for daily metrics
```

## Python Tool Implementation

Tools are Python functions that receive mapped inputs as keyword arguments:

```python
# tools/data_queries.py
import json
from datetime import datetime, timedelta

def get_daily_data(query_date: str = "") -> str:
    """
    Fetch daily data from database.

    Args:
        query_date: Date in YYYY-MM-DD format (defaults to yesterday)

    Returns:
        JSON string with metrics (wrapped as {"output": "..."} by runtime)
    """
    if not query_date:
        query_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    # Query database...
    results = {"count": 42, "volume": 123.5, "date": query_date}
    return json.dumps(results, indent=2)


def get_metrics_dict(query_date: str = "") -> dict:
    """
    Alternative: Return dict directly.
    Dict keys become available directly in edge mappings.
    """
    return {
        "device_count": 42,
        "volume": 123.5,
        "date": query_date
    }
```

## Common Patterns

### Fan-Out (One to Many)

```yaml
edges:
  e1:
    from: analyze
    to: generate_summary
    mapping:
      data: text

  e2:
    from: analyze
    to: generate_alerts
    mapping:
      data: text

  e3:
    from: analyze
    to: update_dashboard
    mapping:
      metrics: text
```

### Fan-In (Many to One)

```yaml
edges:
  e1:
    from: fetch_users
    to: combine
    mapping:
      users: output

  e2:
    from: fetch_orders
    to: combine
    mapping:
      orders: output

  e3:
    from: fetch_metrics
    to: combine
    mapping:
      metrics: output
```

### Conditional Edges

```yaml
edges:
  e1:
    from: classify
    to: handle_urgent
    condition: "priority == 'high'"
    mapping:
      ticket: text

  e2:
    from: classify
    to: handle_normal
    condition: "priority != 'high'"
    mapping:
      ticket: text
```

## Troubleshooting

### Empty Input to Node

**Symptom**: Node receives `{}` as input
**Cause**: Incorrect edge mapping field name
**Solution**:
1. Run `python -m trident project validate` to see warnings
2. Check the source node type and use correct field:
   - Prompts: `text` (or schema field names for JSON)
   - Tools returning dict: dict key names
   - Tools returning non-dict: `output`
   - Input nodes: schema field names

### Schema Validation Error

**Symptom**: `Field 'X' expected number, got str`
**Cause**: LLM returning wrong type despite schema
**Solution**: Add explicit type instructions in prompt body

### Tool Not Found

**Symptom**: `Tool definition not found in project`
**Cause**: Tool defined in `nodes:` instead of `tools:`
**Solution**: Move tool definition to `tools:` section

### Validation Warning About Missing Field

**Symptom**: `Source field 'X' may not exist in 'Y' output`
**Cause**: The validator can't verify tool return types statically
**Solution**:
- If the tool returns a dict with that field, the warning is safe to ignore
- Use `--strict` in CI only after confirming mappings work

## Running Workflows

```bash
# Validate first
python -m trident project validate ./my-project

# Dry run (no LLM calls)
python -m trident project run ./my-project \
  --input '{"date": "2026-01-05"}' \
  --dry-run

# Full execution
python -m trident project run ./my-project \
  --input '{"date": "2026-01-05"}' \
  --verbose

# Resume from checkpoint
python -m trident project run ./my-project --resume latest

# Visualize DAG
python -m trident project graph ./my-project --format mermaid --open
```

## References

- Source: `runtime/trident/`
- Examples: `examples/`
- README: `README.md`
