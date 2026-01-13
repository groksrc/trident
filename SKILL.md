# Trident Workflow Authoring Guide

## Overview

Trident is a Python-based LLM agent orchestration runtime that executes workflows as directed acyclic graphs (DAGs). This guide covers patterns for authoring Trident workflow manifests (`.tml` files).

## Project Structure

A typical Trident project:

```
my-project/
  agent.tml           # Workflow manifest
  .env                # Environment variables (API keys, etc.)
  prompts/
    analyze.prompt    # Prompt definitions
    report.prompt
  tools/
    queries.py        # Python tool implementations
```

## Environment Variables (.env)

Trident automatically loads a `.env` file from the project root when `load_project()` is called:

```bash
# .env
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
MY_CUSTOM_VAR=value
```

**Behavior:**
- Loaded into `os.environ` before manifest parsing
- Does NOT override existing environment variables
- Supports `KEY=VALUE` format with optional quotes
- Comments (`#`) and empty lines are ignored

This allows you to keep API keys alongside your workflow without polluting your shell environment.

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

Trident provides comprehensive validation to catch errors before execution:

```bash
# Basic validation - shows warnings
python -m trident project validate ./my-project

# Strict mode - warnings become errors (use in CI)
python -m trident project validate ./my-project --strict

# Dry run also validates edge mappings
python -m trident project run ./my-project --dry-run
```

**Validation checks include:**

- **Edge field validation**: Warns if source fields don't exist in node outputs
- **Type compatibility**: Warns if types don't match (e.g., mapping `string` to `number`)
- **Tool parameter introspection**: Automatically detects expected inputs from Python function signatures
- **Required input detection**: Fails at runtime if required prompt inputs are missing

**Type compatibility rules:**
- Exact type matches always work
- `integer` ↔ `number` are compatible
- `object`/`array` → `string` are compatible (JSON serialization)
- Unknown types (from tools) are assumed compatible

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

## Branch Nodes and Iterative Loops

Branch nodes execute sub-workflows with optional iterative looping. This is how you implement patterns like "refine until quality is good" or "retry until success".

### How Branch Nodes Work

```yaml
# Main workflow
nodes:
  refine_loop:
    type: branch
    workflow: ./workflows/quality-check.tml
    loop_while: "needs_refinement == true"
    max_iterations: 3

edges:
  e1:
    from: input
    to: refine_loop
    mapping:
      text: text
```

**Key behaviors:**
- Branch node loads and executes a separate sub-workflow
- The sub-workflow receives inputs via edge mappings
- If `loop_while` is specified, the sub-workflow re-executes until condition is false
- Each iteration receives the **previous iteration's output as its input**
- Loop terminates when condition is false OR `max_iterations` is reached
- The branch node outputs the final iteration's output

### Critical Requirements for Loops

#### 1. Sub-Workflow Must Be Self-Contained

**WRONG**: Sub-workflow in same directory shares prompts
```
my-project/
  agent.tml              # Main workflow
  sub-workflow.tml       # Sub-workflow (WRONG LOCATION)
  prompts/
    process.prompt       # Shared prompts cause conflicts!
```

**CORRECT**: Sub-workflow in separate directory
```
my-project/
  agent.tml              # Main workflow
  workflows/
    quality-loop.tml     # Sub-workflow
    prompts/
      process.prompt     # Sub-workflow's prompts
```

**Why**: Trident loads all prompts from the project root. If the main workflow and sub-workflow share the same `prompts/` directory, they will conflict during DAG construction.

#### 2. Sub-Workflow Output Schema Must Match Input Schema

For loops to work, iteration N+1 must be able to consume iteration N's output:

```yaml
# Sub-workflow: quality-loop.tml
nodes:
  loop_input:
    type: input
    schema:
      text: string, Text to process

  loop_output:
    type: output
    format: json
    # Output MUST include 'text' field for next iteration

edges:
  e1:
    from: process
    to: loop_output
    mapping:
      text: text                    # Required for loop
      needs_refinement: needs_refinement  # Used by loop_while condition
      quality_score: quality_score  # Additional data
```

**Critical**: The output must contain at least the same fields as the input for the loop to continue.

#### 3. Loop Condition Evaluates Output Fields

```yaml
loop_while: "needs_refinement == true"
```

The condition has access to:
- `output` - the entire output dict
- All output field names directly (e.g., `needs_refinement`, `quality_score`)

**Condition Syntax:**

| Syntax | Description | Example |
|--------|-------------|---------|
| `field` | Truthy evaluation (simplest for booleans) | `needs_refinement` |
| `not field` | Negated truthy evaluation | `not is_complete` |
| `field == true` | Explicit boolean comparison | `needs_refinement == true` |
| `field == false` | Explicit boolean comparison | `is_done == false` |
| `field < N` | Numeric comparison | `quality_score < 80` |
| `field != 'value'` | String comparison | `status != 'complete'` |
| `field == null` | Null check | `error == null` |
| `a and b` | Logical AND | `needs_work and has_content` |
| `a or b` | Logical OR | `retry or fallback` |

**Recommended for boolean fields:**
```yaml
# PREFERRED - simpler and cleaner
loop_while: "needs_refinement"

# Also works - explicit comparison
loop_while: "needs_refinement == true"
```

**Type matching is strict:**
- Boolean `true` ≠ String `'true'`
- If your output schema defines `boolean`, use `== true` (not `== 'true'`)
- If using structured output (JSON schema), types are enforced correctly

#### 4. Max Iterations Must Be Set

```yaml
max_iterations: 3  # REQUIRED when using loop_while
```

Without this, Trident will error. This prevents infinite loops.

If max iterations is reached and `loop_while` is still true, the branch node **fails** with a `BranchError: Max iterations (N) reached`.

### Common Gotchas

#### ❌ Dry Run Doesn't Simulate Loops

Dry runs skip branch node execution entirely:
```bash
python -m trident project run --dry-run  # Won't test loop logic
```

To test loops, you **must** do a real execution with LLM calls.

#### ❌ DAGs Cannot Have Cycles

You **cannot** create loops in the main DAG like this:

**WRONG**:
```yaml
edges:
  e1: input → process
  e2: process → refine
  e3: refine → process  # ❌ CYCLE! DAG validation will fail
```

**CORRECT**: Use a branch node with `loop_while` instead.

### Complete Loop Example

See `examples/text-refinement-loop/` for a working example.

**Main workflow** (`agent.tml`):
```yaml
nodes:
  input:
    type: input
    schema:
      text: string, Text to refine

  refine_loop:
    type: branch
    workflow: ./workflows/quality-loop.tml
    loop_while: "needs_refinement == true"
    max_iterations: 3

  output:
    type: output
    format: json

edges:
  e1:
    from: input
    to: refine_loop
    mapping:
      text: text

  e2:
    from: refine_loop
    to: output
    mapping:
      result: output
```

**Sub-workflow** (`workflows/quality-loop.tml`):
```yaml
nodes:
  loop_input:
    type: input
    schema:
      text: string, Text to evaluate and refine

  process:
    type: prompt
    prompt: prompts/process.prompt

  loop_output:
    type: output
    format: json

edges:
  e1:
    from: loop_input
    to: process
    mapping:
      text: text

  e2:
    from: process
    to: loop_output
    mapping:
      text: text
      needs_refinement: needs_refinement
      quality_score: quality_score
```

**Prompt** (`workflows/prompts/process.prompt`):
```yaml
---
id: process
input:
  text:
    type: string
    required: true

output:
  format: json
  schema:
    text: string, The refined text
    quality_score: number, Quality score 0-100
    needs_refinement: boolean, True if score < 85
---
Evaluate and refine this text:

{{text}}

Return JSON with:
- text: refined version (or original if quality >= 85)
- quality_score: numeric score
- needs_refinement: true if score < 85
```

### Debugging Loop Issues

**Check iteration artifacts:**
```bash
ls .trident/runs/<run-id>/branches/<branch-name>/
cat .trident/runs/<run-id>/branches/<branch-name>/iteration_0.json
```

Each iteration saves:
- `inputs` - what the sub-workflow received
- `outputs` - what the sub-workflow produced
- `success` - whether it succeeded
- `started_at`, `ended_at` - timing info

**Common issues:**
1. Loop condition never becomes false → hits max_iterations
2. Output schema mismatch → next iteration fails with missing input fields
3. Prompt directory shared between workflows → DAG construction conflicts

## Prompt File Structure

Prompts use YAML frontmatter for metadata and Jinja2 templates for the body:

```yaml
---
id: analyze
name: Data Analyzer
description: Analyze metrics and return insights

input:
  data:
    type: string       # Used for type validation in edge mappings
    required: true     # Fails at runtime if not provided
  threshold:
    type: number
    required: false
    default: 0.5       # Used when input not mapped

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

## Structured Output (JSON Schema)

When you define `output.format: json` with a `schema`, Trident enforces structured output using Claude's **tool_use** feature rather than relying on prompt instructions alone.

### How It Works

1. **Schema converted to tool**: Your `output.schema` is converted to a Claude tool definition
2. **Forced tool call**: The API request includes `tool_choice: {"type": "tool", "name": "structured_output"}` which forces Claude to return data via the tool
3. **Response validation**: The tool response is validated against your schema

This is significantly more reliable than asking for JSON in the prompt text.

### Example Flow

Your prompt schema:
```yaml
output:
  format: json
  schema:
    sentiment: string, The detected sentiment
    confidence: number, Score from 0-100
```

Becomes this tool definition sent to Claude:
```json
{
  "name": "structured_output",
  "input_schema": {
    "type": "object",
    "properties": {
      "sentiment": {"type": "string", "description": "The detected sentiment"},
      "confidence": {"type": "number", "description": "Score from 0-100"}
    },
    "required": ["sentiment", "confidence"]
  }
}
```

Claude responds with a `tool_use` block containing your structured data:
```json
{
  "type": "tool_use",
  "name": "structured_output",
  "input": {"sentiment": "positive", "confidence": 95}
}
```

### Important Notes

- **Schema is required for enforcement**: If you only set `format: json` without a `schema`, no tool enforcement happens—you're relying on prompt instructions alone
- **Supported types**: `string`, `number`, `boolean`, `array`, `object` (unknown types default to `string`)
- **All fields are required**: Every field in your schema becomes a required field in the tool definition
- **Prompt text still helps**: While the tool enforces structure, clear instructions in your prompt help Claude understand *what* values to return

### Best Practices

```yaml
output:
  format: json
  schema:
    status: string, Must be one of: success, failure, pending
    score: number, Integer between 0 and 100
    tags: array, List of relevant keyword strings
```

- Be explicit about allowed values and ranges in descriptions
- Use precise type names (`number` not `int` or `float`)
- Reinforce constraints in your prompt body for better results

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

### Missing Required Input

**Symptom**: `SchemaValidationError: Missing required input(s) for 'node_name': field_name`
**Cause**: A required input field wasn't provided via edge mapping
**Solution**:
1. Check that an edge maps to the missing field
2. Verify the source node actually outputs that field
3. If the field is optional, mark it `required: false` in the prompt

### Type Mismatch Warning

**Symptom**: `Type mismatch: 'field' (string) may not be compatible with 'target' (number)`
**Cause**: Source field type doesn't match expected target type
**Solution**:
- Use compatible types (see type compatibility rules above)
- Or convert the value in your prompt/tool logic

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

### API Key Not Found

**Symptom**: `ANTHROPIC_API_KEY environment variable not set`
**Cause**: API key not in environment
**Solution**:
- Add to `.env` file in project root: `ANTHROPIC_API_KEY=sk-ant-...`
- Or export in shell: `export ANTHROPIC_API_KEY=sk-ant-...`

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

# Resume but start from a specific node (replay from that point)
python -m trident project run ./my-project --resume latest --start-from refine

# Visualize DAG
python -m trident project graph ./my-project --format mermaid --open
```

## Resuming and Replaying Workflows

Trident automatically saves checkpoints after each successful node execution. This enables two use cases:

### Resuming Interrupted Runs

If a workflow fails or is interrupted, resume from the last checkpoint:

```bash
python -m trident project run ./my-project --resume latest
```

Completed nodes are skipped, and execution continues from where it left off.

### Replaying from a Specific Node

Sometimes a workflow completes but produces unexpected results. Rather than re-running everything, you can replay from a specific node:

```bash
# Re-run starting from the "refine" node
python -m trident project run ./my-project --resume latest --start-from refine
```

**How it works:**
- Loads the checkpoint from the previous run
- Keeps cached outputs only for nodes that are *ancestors* of the start-from node
- Re-executes the start-from node and all downstream nodes

**Example:**
```
input → process → refine → output
```

With `--start-from refine`:
- `input` and `process` outputs are reused from cache
- `refine` and `output` are re-executed

**Use cases:**
- Prompt iteration: Tweak a prompt and re-run only that node and downstream
- Debugging: Isolate which node is producing incorrect output
- Cost savings: Avoid re-running expensive LLM calls for nodes that worked correctly

## References

- Source: `runtime/trident/`
- Examples: `examples/`
- README: `README.md`
