# Trident

Lightweight agent orchestration runtime for LLM pipelines.

Trident lets you define multi-step AI workflows as directed acyclic graphs (DAGs) using simple YAML manifests and prompt templates. It supports prompt chaining, conditional branching, parallel execution, and Claude Agent SDK integration.

## Installation

```bash
cd runtime
uv pip install -e .

# With Claude Agent SDK support
uv pip install -e ".[agents]"
```

## Quick Start

Create a new project:

```bash
python -m trident project init my-project
cd my-project
```

This creates:
```
my-project/
├── agent.tml          # Project manifest (TML format)
└── prompts/
    └── example.prompt # Prompt template
```

Validate and run:

```bash
python -m trident project validate
python -m trident project run --dry-run -i '{"text": "Hello world"}'
```

## TML - Trident Markup Language

Trident uses `.tml` files (Trident Markup Language) as the conventional manifest format. TML files are valid YAML with a semantic file extension.

**Auto-discovery order** (when given a directory):
1. `agent.tml` (primary)
2. `trident.tml` (secondary)
3. `trident.yaml` (legacy)

**Explicit file paths** work with any filename:
```bash
python -m trident project run ./my-workflow.tml
python -m trident project run ./pipelines/support.tml
```

## Project Structure

### Manifest (`agent.tml`)

```yaml
trident: "0.1"
name: my-project
description: Project description

defaults:
  model: anthropic/claude-sonnet-4-20250514
  temperature: 0.7
  max_tokens: 1024

nodes:
  input:
    type: input
    schema:
      text: string, Input text to process

  output:
    type: output
    format: json

edges:
  e1:
    from: input
    to: process
    mapping:
      content: text

  e2:
    from: process
    to: output
    mapping:
      result: output
```

### Prompt Templates (`prompts/*.prompt`)

```yaml
---
id: process
name: Process Text
description: Processes input text

input:
  content:
    type: string
    description: The content to process

output:
  format: json
  schema:
    result: string, The processed result
---
You are a helpful assistant.

Process this: {{content}}

Return JSON with a "result" field.
```

## Node Types

| Type | Description |
|------|-------------|
| `input` | Entry point with schema validation |
| `output` | Exit point, collects final outputs |
| `prompt` | LLM prompt node (from `.prompt` files) |
| `agent` | Claude Agent SDK node with tool access |
| `branch` | Sub-workflow execution |

### Agent Nodes

Agent nodes use Claude Agent SDK for autonomous tool use:

```yaml
nodes:
  analyzer:
    type: agent
    prompt: prompts/analyzer.prompt
    allowed_tools:
      - Read
      - Write
      - Bash
    mcp_servers:
      github:
        command: npx
        args: ["@modelcontextprotocol/server-github"]
    max_turns: 50
    permission_mode: acceptEdits
```

### Branch Nodes

Branch nodes execute sub-workflows with optional looping:

```yaml
nodes:
  refine:
    type: branch
    workflow: ./refine-workflow.tml
    condition: "needs_refinement == true"
    loop_while: "quality_score < 0.9"
    max_iterations: 5
```

## Edges

Edges connect nodes and map outputs to inputs:

```yaml
edges:
  e1:
    from: classify
    to: respond
    mapping:
      intent: intent           # target_var: source_field
      confidence: confidence
    condition: "confidence > 0.5"  # Optional condition
```

## CLI Commands

```bash
# Project management
python -m trident project init [path]        # Create new project
python -m trident project validate [path]    # Validate project
python -m trident project graph [path]       # Visualize DAG (ASCII or Mermaid)
python -m trident project runs [path]        # List past runs

# Execution
python -m trident project run [path] [options]
  -i, --input JSON           # Input data as JSON
  -f, --input-file PATH      # Input from file
  -e, --entrypoint NODE      # Starting node
  -o, --output FORMAT        # json, text, pretty (default)
  --dry-run                  # Simulate without LLM calls
  --trace                    # Show execution trace
  --resume ID|latest         # Resume from checkpoint

# Orchestration options
  --input-from PATH          # Load inputs from file, alias:name, or run:id
  --emit-signal              # Emit orchestration signals (started/completed/failed/ready)
  --publish-to PATH          # Publish outputs to a well-known path
  --wait-for SIGNAL          # Wait for signal file(s) before starting
  --timeout SECONDS          # Timeout for --wait-for (default: 300)

# DAG visualization
python -m trident project graph --format mermaid --open  # Open in browser
```

## Validation

Trident validates your workflow at multiple levels:

### Basic Validation
```bash
python -m trident project validate ./my-project
```

Checks:
- Manifest syntax and required fields
- DAG structure (no cycles, valid node references)
- Edge mapping warnings (source/target field mismatches)

### Strict Mode
```bash
python -m trident project validate ./my-project --strict
```

In strict mode, warnings become errors. Use this in CI/CD to catch:
- Edge mappings that reference non-existent output fields
- Edge mappings that target unexpected input fields

### Example Output
```
Project: my-project
  Prompts: 2
  Tools: 1
  Edges: 3
  Nodes in execution order: 4

Warnings:
  ⚠ Target field 'wrong_name' not expected by 'process' (prompt).
    Expected inputs: ['content'] (edge: e1)

✓ Validation passed
```

### Common Validation Errors

**Tools must be in `tools:` section:**
```yaml
# ❌ Wrong - tool in nodes section
nodes:
  my_tool:
    type: tool
    module: mymodule

# ✅ Correct - tool in tools section
tools:
  my_tool:
    type: python
    module: mymodule
    function: myfunction
```

## Python API

```python
from trident import load_project, run

# Load and execute
project = load_project("./my-project")
result = run(
    project,
    inputs={"text": "Hello world"},
    dry_run=False,
    verbose=True,
)

# Check results
if result.success:
    print(result.outputs)
else:
    print(f"Failed: {result.error}")

# Access trace
for node in result.trace.nodes:
    print(f"{node.id}: {node.tokens}")
```

## Features

- **DAG Execution**: Automatic topological ordering and dependency resolution
- **Parallel Execution**: Independent nodes run concurrently
- **Conditional Edges**: Skip nodes based on runtime conditions
- **Checkpoints**: Resume interrupted runs from last successful node
- **Artifacts**: Automatic persistence of runs, traces, and outputs
- **Dry Run**: Test pipelines without LLM calls
- **Mermaid Visualization**: Generate interactive DAG diagrams
- **Workflow Orchestration**: Chain workflows with signals, wait conditions, and shared outputs

## Workflow Orchestration

Trident supports file-based workflow orchestration for chaining workflows, scheduled execution, and event-driven triggers.

### Signal Files

Workflows can emit signal files to indicate state transitions:

```bash
# Emit signals when running
python -m trident project run ./my-workflow --emit-signal
```

Creates signal files in `.trident/signals/`:
- `{workflow}.started` - Workflow began execution
- `{workflow}.completed` - Workflow finished successfully
- `{workflow}.failed` - Workflow encountered an error
- `{workflow}.ready` - Outputs are available for downstream workflows

### Input Chaining

Load inputs from previous workflow outputs:

```bash
# From a file path
python -m trident project run --input-from ../upstream/.trident/outputs/latest.json

# From an alias
python -m trident project run --input-from alias:upstream-workflow

# From a specific run
python -m trident project run --input-from run:abc123
```

### Wait Conditions

Block execution until signals are present:

```bash
# Wait for upstream workflow to complete
python -m trident project run ./downstream \
  --wait-for ../upstream/.trident/signals/upstream.ready \
  --timeout 600

# Wait for multiple signals
python -m trident project run ./final \
  --wait-for ./step1/.trident/signals/step1.ready \
  --wait-for ./step2/.trident/signals/step2.ready
```

### Publishing Outputs

Publish outputs to well-known paths for downstream consumption:

```bash
python -m trident project run ./my-workflow --publish-to ./outputs/latest.json
```

### Manifest Configuration

Configure orchestration in the manifest:

```yaml
orchestration:
  publish:
    path: .trident/outputs/latest.json
    alias: my-workflow

  signals:
    enabled: true
```

## Examples

See the `examples/` directory:

- `support-triage/` - Customer support ticket classification
- `dev-team/` - Multi-agent development workflow
- `browser-screenshot/` - Browser automation with Chrome DevTools MCP
- `todomvc-python/` - TodoMVC app generation
- `todomvc-vue/` - Vue.js TodoMVC generation

## License

MIT
