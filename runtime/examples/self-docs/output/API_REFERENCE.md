# Trident API Reference

Complete reference documentation for Trident's configuration files, APIs, and data structures.

---

## Table of Contents

1. [Project Configuration (trident.yaml)](#project-configuration-tridentyaml)
2. [Prompt File Format (.prompt)](#prompt-file-format-prompt)
3. [Python API](#python-api)
4. [Node Types](#node-types)
5. [Agent Configuration](#agent-configuration)
6. [Error Types](#error-types)
7. [Execution & Tracing](#execution--tracing)

---

## Project Configuration (trident.yaml)

The `trident.yaml` file defines your workflow's structure, nodes, edges, and configuration.

### Schema

```yaml
trident: "0.1" | "0.2"  # Required: Version string
name: string            # Required: Project name
version: string         # Optional: Project version (default: "0.1")
description: string     # Optional: Project description

defaults:               # Optional: Default configuration for all nodes
  model: string         # Model identifier (e.g., "anthropic/claude-sonnet-4-20250514")
  temperature: float    # Temperature (0-1)
  max_tokens: int       # Max output tokens

entrypoints:            # Optional: List of entry node IDs (defaults to all input nodes)
  - string

env:                    # Optional: Environment variable declarations
  section_name:
    key: value

nodes:                  # Optional: Node definitions (prompt nodes defined in .prompt files)
  node_id:
    type: "input" | "output" | "tool" | "agent"
    # ... type-specific fields (see Node Types section)

edges:                  # Required: Edge definitions connecting nodes
  edge_id:
    from: string        # Source node ID
    to: string          # Target node ID
    mapping:            # Optional: Field mappings
      target_var: source_expr  # source_expr can use dot notation
    condition: string   # Optional: Boolean expression for conditional execution

tools:                  # Optional: Tool definitions
  tool_id:
    type: "python" | "shell" | "http"
    # ... type-specific fields (see Tools section)
```

### Complete Example

```yaml
trident: "0.2"
name: sentiment-analyzer
version: "1.0"
description: Analyze sentiment of customer feedback

defaults:
  model: anthropic/claude-sonnet-4-20250514
  temperature: 0.3
  max_tokens: 2000

entrypoints:
  - input

env:
  database:
    host: localhost
    port: 5432

nodes:
  input:
    type: input
    schema:
      feedback: string, Customer feedback text to analyze
      customer_id: string, Customer identifier

  preprocessor:
    type: tool
    tool: clean_text

  output:
    type: output
    format: json

  analyzer:
    type: agent
    prompt: prompts/analyzer.prompt
    allowed_tools: [Read, Grep]
    max_turns: 10

edges:
  to_preprocessor:
    from: input
    to: preprocessor
    mapping:
      text: feedback

  to_classifier:
    from: preprocessor
    to: classifier
    mapping:
      text: result.cleaned_text

  to_analyzer:
    from: classifier
    to: analyzer
    condition: "output.confidence < 0.7"
    mapping:
      text: feedback
      initial_sentiment: output.sentiment

  to_output:
    from: classifier
    to: output
    condition: "output.confidence >= 0.7"
    mapping:
      sentiment: output.sentiment
      confidence: output.confidence

tools:
  clean_text:
    type: python
    module: tools.preprocessing
    function: clean_text
    description: Clean and normalize text input
```

### Defaults and Inheritance

Configuration follows this precedence (highest to lowest):

1. **Node-level** configuration (in `.prompt` file frontmatter)
2. **Project defaults** (in `trident.yaml` under `defaults:`)
3. **System defaults** (built-in values)

Example:

```yaml
defaults:
  model: anthropic/claude-sonnet-4-20250514
  temperature: 0.5
  max_tokens: 1000
```

```prompt
---
id: creative_writer
temperature: 0.9  # Overrides project default
# model and max_tokens inherited from defaults
---
Write creatively about: {{topic}}
```

### Environment Variables

Environment variables can be declared in `trident.yaml` and referenced in node configurations:

```yaml
env:
  database:
    host: ${DB_HOST}  # References system env var
    port: 5432        # Literal value

  api:
    key: ${API_KEY}
    endpoint: https://api.example.com

nodes:
  data_fetcher:
    type: agent
    mcp_servers:
      database:
        command: npx
        args: [db-mcp-server]
        env:
          DB_HOST: ${database.host}  # References env.database.host
          DB_PORT: ${database.port}
```

---

## Prompt File Format (.prompt)

Prompt files define LLM completion nodes with structured input/output schemas and template bodies.

### File Structure

```
---
<YAML frontmatter>
---
<Template body with {{variable}} substitution>
```

### Frontmatter Schema

```yaml
id: string              # Required: Unique node identifier
name: string            # Optional: Display name
description: string     # Optional: Description

# Model configuration (inherits from project defaults)
model: string           # Optional: Model override
temperature: float      # Optional: Temperature override (0-1)
max_tokens: int         # Optional: Max tokens override

# Input schema
input:
  field_name:
    type: string        # Required: "string" | "number" | "boolean" | "array" | "object"
    description: string # Required: Field description
    required: bool      # Optional: Default true
    default: any        # Optional: Default value if not provided

# Output schema
output:
  format: string        # Optional: "text" | "json" (default: "text")
  schema:               # Required if format is "json"
    field_name: string  # Format: "type, description"
```

### Template Syntax

Templates use Jinja2 with `{{variable}}` substitution:

- **Simple variables**: `{{field_name}}`
- **Dot notation**: `{{output.field.subfield}}`
- **Unknown variables**: Left as-is (not an error)

### Examples

#### Text Output Prompt

```prompt
---
id: summarizer
name: Text Summarizer
description: Summarize long text into key points

input:
  text:
    type: string
    description: Text to summarize
  max_bullets:
    type: number
    description: Maximum number of bullet points
    required: false
    default: 5

output:
  format: text

model: anthropic/claude-sonnet-4-20250514
temperature: 0.3
---
Summarize the following text into {{max_bullets}} key bullet points.

Text:
{{text}}

Provide a concise summary with the most important points.
```

#### JSON Output Prompt

```prompt
---
id: classifier
name: Intent Classifier
description: Classify user intent from text

input:
  message:
    type: string
    description: User message to classify

output:
  format: json
  schema:
    intent: string, The classified intent category
    confidence: number, Confidence score between 0 and 1
    reason: string, Brief explanation of classification
    suggested_action: string, Recommended next action

model: anthropic/claude-sonnet-4-20250514
temperature: 0.2
max_tokens: 500
---
Analyze the following user message and classify their intent.

Message: {{message}}

Consider common intent categories like: question, complaint, praise, request, feedback.

Return a JSON object with the intent classification, confidence score (0-1), reasoning, and suggested action.
```

#### Complex Input Prompt

```prompt
---
id: report_generator
name: Report Generator
description: Generate analytical reports from structured data

input:
  title:
    type: string
    description: Report title
  data:
    type: object
    description: Data object containing metrics
    required: true
  include_charts:
    type: boolean
    description: Whether to include chart descriptions
    default: false
  format_style:
    type: string
    description: Report format style
    default: professional

output:
  format: text

temperature: 0.5
---
Generate a {{format_style}} report titled "{{title}}".

Data:
{{data}}

{{#if include_charts}}
Include descriptions of relevant charts and visualizations.
{{/if}}

Structure the report with:
1. Executive Summary
2. Key Metrics
3. Analysis
4. Recommendations
```

---

## Python API

### Core Functions

#### `load_project(path)`

Load a Trident project from a directory containing `trident.yaml`.

**Signature:**
```python
def load_project(path: str | Path) -> Project
```

**Parameters:**
- `path` (str | Path): Path to project directory

**Returns:**
- `Project`: Loaded project configuration

**Raises:**
- `ParseError`: If files cannot be parsed
- `ValidationError`: If project structure is invalid

**Example:**
```python
from trident import load_project

# Load from relative path
project = load_project("./my-project")

# Load from absolute path
from pathlib import Path
project = load_project(Path("/Users/me/projects/my-workflow"))

print(f"Loaded project: {project.name}")
print(f"Entrypoints: {project.entrypoints}")
print(f"Nodes: {len(project.prompts)} prompts, {len(project.agents)} agents")
```

#### `run(project, ...)`

Execute a Trident project workflow.

**Signature:**
```python
def run(
    project: Project,
    entrypoint: str | None = None,
    inputs: dict[str, Any] | None = None,
    dry_run: bool = False,
    verbose: bool = False,
    resume_sessions: dict[str, str] | None = None,
    on_agent_message: Callable[[str, Any], None] | None = None,
) -> ExecutionResult
```

**Parameters:**
- `project` (Project): Loaded project from `load_project()`
- `entrypoint` (str | None): Starting node ID (default: first entrypoint in project)
- `inputs` (dict[str, Any] | None): Input data for input nodes, keyed by node ID
- `dry_run` (bool): If True, simulate execution without LLM calls (returns mock data)
- `verbose` (bool): If True, print node execution progress to stdout
- `resume_sessions` (dict[str, str] | None): Map of node_id → session_id for resuming agent nodes
- `on_agent_message` (Callable): Callback for agent messages, receives `(message_type, content)`

**Returns:**
- `ExecutionResult`: Always returned, even on failure. Check `result.success` or `result.error`

**Raises:**
- `TridentError`: Only for unrecoverable setup errors (no entrypoint, DAG cycle detected)

**Example:**
```python
from trident import load_project, run

project = load_project("./sentiment-analyzer")

# Basic execution
result = run(
    project,
    inputs={
        "input": {
            "feedback": "Great product, but delivery was slow",
            "customer_id": "C12345"
        }
    }
)

if result.success:
    print("Outputs:", result.outputs)
    print(f"Executed {len(result.trace.nodes)} nodes")

    # Access specific output node
    print("Sentiment:", result.outputs["output"]["sentiment"])
else:
    print(f"Execution failed: {result.error}")
    if result.trace.failed_node:
        print(f"Failed at node: {result.trace.failed_node.id}")

# Verbose execution with progress
result = run(project, inputs={...}, verbose=True)
# Prints:
# Executing node: input
# Executing node: preprocessor
# Executing node: classifier
# ...

# Dry run (no LLM calls)
result = run(project, inputs={...}, dry_run=True)
# Returns mock outputs without calling providers

# Resume agent from previous session
result = run(
    project,
    inputs={...},
    resume_sessions={
        "analyzer": "sess-abc123",  # Resume this agent
    }
)

# Agent message callback
def handle_agent_message(msg_type: str, content: Any):
    if msg_type == "assistant":
        print(f"Agent says: {content}")
    elif msg_type == "tool_use":
        print(f"Using tool: {content['name']}")

result = run(
    project,
    inputs={...},
    on_agent_message=handle_agent_message
)
```

### Data Classes

#### `Project`

Project configuration loaded from `trident.yaml` and prompt files.

**Definition:**
```python
@dataclass
class Project:
    name: str                                    # Project name
    root: Path                                   # Project root directory
    version: str = "0.1"                        # Project version
    description: str = ""                        # Project description
    defaults: dict[str, Any]                    # Default configuration
    entrypoints: list[str]                      # Entry node IDs
    edges: dict[str, Edge]                      # Edge definitions
    prompts: dict[str, PromptNode]              # Prompt nodes by ID
    input_nodes: dict[str, InputNode]           # Input nodes by ID
    output_nodes: dict[str, OutputNode]         # Output nodes by ID
    tools: dict[str, ToolDef]                   # Tool definitions by ID
    agents: dict[str, AgentNode]                # Agent nodes by ID
    env: dict[str, dict[str, Any]]              # Environment variables
```

**Example:**
```python
project = load_project("./my-workflow")

print(f"Project: {project.name} v{project.version}")
print(f"Root: {project.root}")
print(f"Entrypoints: {project.entrypoints}")
print(f"Default model: {project.defaults.get('model')}")

# Iterate over nodes
for node_id, prompt_node in project.prompts.items():
    print(f"Prompt node: {node_id} - {prompt_node.name}")

for node_id, agent_node in project.agents.items():
    print(f"Agent node: {node_id} - {agent_node.prompt_path}")
    print(f"  Tools: {agent_node.allowed_tools}")
    print(f"  Max turns: {agent_node.max_turns}")

# Check edges
for edge_id, edge in project.edges.items():
    print(f"Edge: {edge.from_node} → {edge.to_node}")
    if edge.condition:
        print(f"  Condition: {edge.condition}")
```

#### `ExecutionResult`

Result of workflow execution, always returned even on failure.

**Definition:**
```python
@dataclass
class ExecutionResult:
    outputs: dict[str, Any]              # Output node results, keyed by node ID
    trace: ExecutionTrace                # Full execution trace
    error: NodeExecutionError | None     # Error if execution failed

    @property
    def success(self) -> bool:
        """Check if execution completed successfully."""
        return self.error is None and self.trace.succeeded

    def summary(self) -> str:
        """Get a human-readable summary of execution."""
        # Returns formatted summary string
```

**Example:**
```python
result = run(project, inputs={...})

# Check success
if result.success:
    print("✓ Execution succeeded")
else:
    print("✗ Execution failed")
    print(f"Error: {result.error}")

# Access outputs
for node_id, output in result.outputs.items():
    print(f"Output from {node_id}:", output)

# Get summary
print(result.summary())
# Output:
# Execution succeeded
#
# Outputs:
#   output: {'sentiment': 'positive', 'confidence': 0.85}
#
# Execution trace:
#   Nodes executed: 4
#   Total tokens: 1250 input, 340 output
#   Total cost: $0.008
#   Duration: 2.3s

# Access specific output
sentiment = result.outputs["output"]["sentiment"]
confidence = result.outputs["output"]["confidence"]

# Trace analysis
print(f"Executed {len(result.trace.nodes)} nodes")
print(f"Duration: {result.trace.end_time - result.trace.start_time}")

# Check for failures
if not result.success:
    failed = result.trace.failed_node
    if failed:
        print(f"Failed at node: {failed.id}")
        print(f"Error: {failed.error}")
        print(f"Input was: {failed.input}")
```

#### `ExecutionTrace`

Complete execution trace with per-node metrics.

**Definition:**
```python
@dataclass
class ExecutionTrace:
    execution_id: str                    # Unique execution identifier
    start_time: str                      # ISO 8601 timestamp
    end_time: str | None                 # ISO 8601 timestamp
    nodes: list[NodeTrace]               # Per-node execution traces
    error: str | None                    # Top-level execution error

    @property
    def succeeded(self) -> bool:
        """Check if execution completed without errors."""
        return self.error is None and all(n.succeeded for n in self.nodes)

    @property
    def failed_node(self) -> NodeTrace | None:
        """Get the first node that failed, if any."""
        return next((n for n in self.nodes if not n.succeeded), None)
```

**Example:**
```python
result = run(project, inputs={...})
trace = result.trace

print(f"Execution ID: {trace.execution_id}")
print(f"Started: {trace.start_time}")
print(f"Ended: {trace.end_time}")
print(f"Success: {trace.succeeded}")

# Analyze nodes
total_input_tokens = 0
total_output_tokens = 0
total_cost = 0.0

for node in trace.nodes:
    print(f"\nNode: {node.id}")
    print(f"  Duration: {node.end_time - node.start_time}")
    print(f"  Input tokens: {node.input_tokens}")
    print(f"  Output tokens: {node.output_tokens}")

    if node.cost_usd:
        print(f"  Cost: ${node.cost_usd:.4f}")
        total_cost += node.cost_usd

    if node.session_id:
        print(f"  Session: {node.session_id}")

    if node.num_turns > 0:
        print(f"  Agent turns: {node.num_turns}")

    total_input_tokens += node.input_tokens
    total_output_tokens += node.output_tokens

print(f"\nTotal tokens: {total_input_tokens} input, {total_output_tokens} output")
print(f"Total cost: ${total_cost:.4f}")

# Check for failures
if not trace.succeeded:
    failed = trace.failed_node
    print(f"\nFailed at node: {failed.id}")
    print(f"Error type: {failed.error_type}")
    print(f"Error message: {failed.error}")
```

#### `NodeTrace`

Individual node execution trace with timing, I/O, and metrics.

**Definition:**
```python
@dataclass
class NodeTrace:
    id: str                              # Node identifier
    start_time: str                      # ISO 8601 timestamp
    end_time: str | None                 # ISO 8601 timestamp
    input: dict[str, Any]                # Node input data
    output: dict[str, Any]               # Node output data
    model: str | None                    # Model used (if LLM node)
    tokens: dict[str, int]               # {"input": N, "output": M}
    skipped: bool = False                # True if node was skipped (condition eval)
    error: str | None                    # Error message if failed
    error_type: str | None               # Error type name if failed
    cost_usd: float | None               # Execution cost in USD
    session_id: str | None               # Agent session ID (for resuming)
    num_turns: int = 0                   # Number of agent turns (for agent nodes)

    @property
    def input_tokens(self) -> int:
        """Get input token count."""
        return self.tokens.get("input", 0)

    @property
    def output_tokens(self) -> int:
        """Get output token count."""
        return self.tokens.get("output", 0)

    @property
    def succeeded(self) -> bool:
        """Check if node execution succeeded."""
        return self.error is None
```

**Example:**
```python
result = run(project, inputs={...})

for node in result.trace.nodes:
    print(f"\n{'='*60}")
    print(f"Node: {node.id}")
    print(f"{'='*60}")

    # Timing
    duration = node.end_time - node.start_time if node.end_time else "N/A"
    print(f"Duration: {duration}")

    # Status
    if node.skipped:
        print("Status: SKIPPED (condition evaluated to false)")
        continue

    if node.succeeded:
        print("Status: SUCCESS")
    else:
        print(f"Status: FAILED - {node.error_type}")
        print(f"Error: {node.error}")

    # I/O
    print(f"\nInput: {node.input}")
    print(f"Output: {node.output}")

    # Metrics
    if node.model:
        print(f"\nModel: {node.model}")

    if node.input_tokens > 0 or node.output_tokens > 0:
        print(f"Tokens: {node.input_tokens} in, {node.output_tokens} out")

    if node.cost_usd:
        print(f"Cost: ${node.cost_usd:.4f}")

    # Agent-specific
    if node.num_turns > 0:
        print(f"\nAgent turns: {node.num_turns}")

    if node.session_id:
        print(f"Session ID: {node.session_id}")
        print("(Use this to resume the agent)")
```

#### Supporting Data Classes

##### `Edge`

Edge connection between nodes with optional mapping and condition.

```python
@dataclass
class Edge:
    id: str                              # Edge identifier
    from_node: str                       # Source node ID
    to_node: str                         # Target node ID
    mappings: list[EdgeMapping]          # Field mappings
    condition: str | None = None         # Optional condition expression
```

##### `EdgeMapping`

Field mapping from source to target node.

```python
@dataclass
class EdgeMapping:
    target_var: str                      # Target field name
    source_expr: str                     # Source expression (supports dot notation)
```

Example:
```python
mapping = EdgeMapping(
    target_var="message",
    source_expr="output.result.text"
)
# Maps output.result.text → message
```

##### `PromptNode`

Prompt node definition from .prompt file.

```python
@dataclass
class PromptNode:
    id: str                              # Node identifier
    name: str = ""                       # Display name
    description: str = ""                # Description
    model: str | None = None             # Model override
    temperature: float | None = None     # Temperature override
    max_tokens: int | None = None        # Max tokens override
    inputs: dict[str, InputField]        # Input field definitions
    output: OutputSchema                 # Output schema
    body: str = ""                       # Template body
    file_path: Path | None = None        # Source file path
```

##### `AgentNode`

Agent node configuration.

```python
@dataclass
class AgentNode:
    id: str                              # Node identifier
    prompt_path: str                     # Path to .prompt file
    allowed_tools: list[str]             # SDK tool names
    mcp_servers: dict[str, MCPServerConfig]  # MCP server configs
    max_turns: int = 50                  # Maximum iterations
    permission_mode: str = "acceptEdits" # "acceptEdits" or "bypassPermissions"
    cwd: str | None = None               # Working directory
    prompt_node: PromptNode | None = None  # Loaded prompt (runtime)
```

---

## Node Types

### Input Node

Entry point for data into the workflow.

**Configuration:**
```yaml
nodes:
  input:
    type: input
    schema:
      field_name: type, description
      # type: string | number | boolean | array | object
```

**Example:**
```yaml
nodes:
  user_input:
    type: input
    schema:
      message: string, User message to process
      user_id: string, User identifier
      timestamp: number, Unix timestamp
      metadata: object, Additional metadata
```

**Usage:**
```python
result = run(
    project,
    inputs={
        "user_input": {
            "message": "Hello, world!",
            "user_id": "U12345",
            "timestamp": 1704067200,
            "metadata": {"source": "web"}
        }
    }
)
```

### Output Node

Collects final results from the workflow.

**Configuration:**
```yaml
nodes:
  output:
    type: output
    format: json | text  # Default: json
```

**Example:**
```yaml
nodes:
  results:
    type: output
    format: json

edges:
  to_output:
    from: classifier
    to: results
    mapping:
      sentiment: output.sentiment
      score: output.confidence
      processed_at: timestamp
```

**Accessing outputs:**
```python
result = run(project, inputs={...})
output_data = result.outputs["results"]
print(output_data)
# {'sentiment': 'positive', 'score': 0.89, 'processed_at': 1704067200}
```

### Prompt Node

LLM completion with structured I/O, defined in `.prompt` files.

**File location:** `prompts/node_id.prompt`

**Example:**
```prompt
---
id: classifier
model: anthropic/claude-sonnet-4-20250514
temperature: 0.2

input:
  text:
    type: string
    description: Text to classify

output:
  format: json
  schema:
    category: string, The classification category
    confidence: number, Confidence score 0-1
---
Classify the following text into one of these categories:
- technical
- sales
- support
- feedback

Text: {{text}}

Return a JSON object with the category and confidence score.
```

**Referenced in trident.yaml:**
```yaml
edges:
  to_classifier:
    from: input
    to: classifier  # Automatically finds prompts/classifier.prompt
    mapping:
      text: message
```

### Tool Node

Execute Python, shell, or HTTP tools.

**Configuration:**
```yaml
nodes:
  processor:
    type: tool
    tool: my_tool  # References tools.my_tool

tools:
  my_tool:
    type: python
    module: tools.preprocessing
    function: execute  # Default: "execute"
    description: Preprocess text input
```

**Python tool example:**
```python
# tools/preprocessing.py
def execute(text: str, max_length: int = 100) -> dict:
    """
    Tool function receives mapped inputs as kwargs.
    Must return a dictionary.
    """
    cleaned = text.strip().lower()[:max_length]
    return {
        "cleaned_text": cleaned,
        "length": len(cleaned),
        "truncated": len(text) > max_length
    }
```

**Edge mapping:**
```yaml
edges:
  to_processor:
    from: input
    to: processor
    mapping:
      text: message
      max_length: config.max_len
```

### Agent Node

Multi-turn autonomous execution via Claude Agent SDK.

**Configuration:**
```yaml
nodes:
  analyzer:
    type: agent
    prompt: prompts/analyzer.prompt
    allowed_tools:
      - Read
      - Write
      - Glob
      - Grep
      - Bash
    mcp_servers:
      database:
        command: npx
        args: [db-mcp-server]
        env:
          DB_URL: ${database.url}
    max_turns: 20
    permission_mode: bypassPermissions
    cwd: /path/to/workspace
```

**Prompt file:**
```prompt
---
id: analyzer
model: anthropic/claude-sonnet-4-20250514

input:
  codebase_path:
    type: string
    description: Path to codebase to analyze

output:
  format: json
  schema:
    modules: array, List of module names
    dependencies: array, External dependencies
    entry_points: array, Entry point files
    summary: string, Brief analysis summary
---
Analyze the codebase at: {{codebase_path}}

Use the Read, Glob, and Grep tools to explore the codebase.

Return a JSON object with:
- List of main modules
- External dependencies found
- Entry point files
- Brief summary of the codebase structure
```

**Usage:**
```python
result = run(
    project,
    inputs={
        "analyzer": {
            "codebase_path": "/Users/me/project"
        }
    },
    on_agent_message=lambda msg_type, content: print(f"[{msg_type}] {content}")
)

# Access agent output
analysis = result.outputs["analyzer"]
print(analysis["modules"])
print(analysis["summary"])

# Resume agent from previous session
session_id = result.trace.nodes[0].session_id
result2 = run(
    project,
    inputs={...},
    resume_sessions={"analyzer": session_id}
)
```

**Available SDK Tools:**
- `Read` - Read file contents
- `Write` - Write files
- `Edit` - Edit file contents
- `Bash` - Execute bash commands
- `Glob` - Find files by pattern
- `Grep` - Search file contents
- `WebFetch` - Fetch web content
- `WebSearch` - Search the web
- `SlashCommand` - Execute custom commands
- `Skill` - Execute skills
- `TodoWrite` - Manage task lists

---

## Agent Configuration

Agent nodes enable multi-turn autonomous execution with tool access.

### Agent Node Options

```yaml
nodes:
  agent_id:
    type: agent
    prompt: string              # Required: Path to .prompt file
    allowed_tools: list[str]    # Optional: SDK tool names
    mcp_servers: dict           # Optional: MCP server configurations
    max_turns: int              # Optional: Max iterations (default: 50)
    permission_mode: string     # Optional: "acceptEdits" | "bypassPermissions"
    cwd: string                 # Optional: Working directory
```

### Allowed Tools

List of Claude Code SDK tools the agent can use:

```yaml
allowed_tools:
  - Read           # Read file contents
  - Write          # Write new files
  - Edit           # Edit existing files
  - Bash           # Execute bash commands
  - Glob           # Find files by glob pattern
  - Grep           # Search file contents with regex
  - WebFetch       # Fetch web page content
  - WebSearch      # Search the web
  - SlashCommand   # Execute custom slash commands
  - Skill          # Execute skills
  - TodoWrite      # Manage task lists
```

**Example:**
```yaml
nodes:
  code_reviewer:
    type: agent
    prompt: prompts/reviewer.prompt
    allowed_tools: [Read, Grep, Bash]  # Limited toolset
    max_turns: 10
```

### MCP Servers

Configure Model Context Protocol servers for external tool access:

```yaml
mcp_servers:
  server_name:
    command: string         # Command to execute
    args: list[string]      # Command arguments
    env: dict[str, string]  # Environment variables (supports ${VAR})
```

**Example:**
```yaml
nodes:
  data_analyst:
    type: agent
    prompt: prompts/analyst.prompt
    allowed_tools: [Read, Write]
    mcp_servers:
      database:
        command: npx
        args: [@modelcontextprotocol/server-postgres]
        env:
          DATABASE_URL: ${database.url}
          DB_SCHEMA: public

      filesystem:
        command: npx
        args: [mcp-server-filesystem, /data]
        env:
          READ_ONLY: "false"

      browser:
        command: npx
        args: [@playwright/mcp@latest]
        env:
          PLAYWRIGHT_HEADLESS: "true"
```

### Permission Mode

Control file edit permissions:

- `"acceptEdits"` (default): Prompt user for permission before edits
- `"bypassPermissions"`: Allow edits without prompting

```yaml
nodes:
  automated_fixer:
    type: agent
    prompt: prompts/fixer.prompt
    permission_mode: bypassPermissions  # No prompts
    allowed_tools: [Read, Edit, Bash]
```

### Max Turns

Limit agent iterations to prevent runaway execution:

```yaml
nodes:
  researcher:
    type: agent
    prompt: prompts/researcher.prompt
    max_turns: 30  # Stop after 30 turns
    allowed_tools: [Read, Grep, WebSearch]
```

### Working Directory

Set the agent's working directory:

```yaml
nodes:
  builder:
    type: agent
    prompt: prompts/builder.prompt
    cwd: /path/to/project  # Absolute path
    allowed_tools: [Read, Write, Bash]
```

If not specified, defaults to:
1. Project root directory, or
2. `$TRIDENT_WORKSPACE` environment variable if set

### Agent Callbacks

Handle agent messages during execution:

```python
def handle_agent_message(msg_type: str, content: Any):
    """
    Callback for agent messages.

    msg_type:
      - "assistant": Agent text response
      - "tool_use": Agent using a tool
      - "tool_result": Tool execution result
      - "result": Final agent result

    content: Message content (varies by type)
    """
    if msg_type == "assistant":
        print(f"🤖 Agent: {content}")

    elif msg_type == "tool_use":
        tool_name = content.get("name")
        tool_input = content.get("input", {})
        print(f"🔧 Using tool: {tool_name}")
        print(f"   Input: {tool_input}")

    elif msg_type == "tool_result":
        print(f"✓ Tool result: {content}")

    elif msg_type == "result":
        print(f"✅ Final result: {content}")

result = run(
    project,
    inputs={...},
    on_agent_message=handle_agent_message
)
```

### Agent Session Resumption

Resume agents from previous sessions:

```python
# First execution
result1 = run(project, inputs={...})
session_id = result1.trace.nodes[0].session_id
print(f"Session ID: {session_id}")

# Resume from session
result2 = run(
    project,
    inputs={...},
    resume_sessions={
        "agent_node_id": session_id
    }
)
```

### Agent Output

Agents return structured output matching their prompt's output schema:

```prompt
---
id: analyzer
output:
  format: json
  schema:
    files_analyzed: number, Number of files analyzed
    issues_found: array, List of issues
    summary: string, Analysis summary
---
Analyze the codebase and report issues.
```

```python
result = run(project, inputs={...})
agent_output = result.outputs["analyzer"]

print(f"Analyzed {agent_output['files_analyzed']} files")
print(f"Found {len(agent_output['issues_found'])} issues")
print(agent_output['summary'])
```

---

## Error Types

Trident's exception hierarchy with exit codes for CLI integration.

### Exception Hierarchy

```
TridentError (base)
├── ParseError
├── ValidationError
│   └── DAGError
├── ProviderError
├── SchemaValidationError
├── ConditionError
├── ToolError
├── NodeExecutionError
└── AgentExecutionError
```

### Exit Codes

```python
from trident.errors import ExitCode

ExitCode.SUCCESS = 0           # Successful execution
ExitCode.RUNTIME_ERROR = 1     # Runtime error
ExitCode.VALIDATION_ERROR = 2  # Validation/parse error
ExitCode.PROVIDER_ERROR = 3    # LLM provider error
```

### Error Types

#### `TridentError`

Base exception for all Trident errors.

```python
class TridentError(Exception):
    exit_code: ExitCode = ExitCode.RUNTIME_ERROR
```

**When raised:**
- Base class for all Trident exceptions
- Provides exit code for CLI

#### `ParseError`

Raised when files cannot be parsed.

```python
from trident.errors import ParseError
```

**Common scenarios:**
- Invalid YAML syntax in `trident.yaml`
- Invalid frontmatter in `.prompt` files
- Malformed JSON in configuration

**Example:**
```python
try:
    project = load_project("./my-project")
except ParseError as e:
    print(f"Parse error: {e}")
    print(f"Exit code: {e.exit_code}")
    # Exit code: ExitCode.VALIDATION_ERROR (2)
```

#### `ValidationError`

Raised for invalid project structure or data.

```python
from trident.errors import ValidationError
```

**Common scenarios:**
- Missing required fields in configuration
- Invalid node references in edges
- Missing prompt files
- Invalid tool configuration

**Example:**
```python
try:
    project = load_project("./my-project")
except ValidationError as e:
    print(f"Validation error: {e}")
    # e.g., "Node 'classifier' referenced in edge but not defined"
```

#### `DAGError`

Raised for DAG-related issues (subclass of ValidationError).

```python
from trident.errors import DAGError
```

**Common scenarios:**
- Cycle detected in workflow graph
- No path from entrypoint to output
- Disconnected nodes

**Example:**
```python
try:
    project = load_project("./my-project")
    result = run(project)
except DAGError as e:
    print(f"DAG error: {e}")
    # e.g., "Cycle detected: node1 → node2 → node1"
```

#### `ProviderError`

Raised for LLM provider issues.

```python
from trident.errors import ProviderError
```

**Attributes:**
- `retryable: bool` - Indicates if error is retryable

**Common scenarios:**
- API rate limits (retryable=True)
- Invalid API key (retryable=False)
- Network timeout (retryable=True)
- Model not found (retryable=False)

**Example:**
```python
from trident.errors import ProviderError

try:
    result = run(project, inputs={...})
except ProviderError as e:
    if e.retryable:
        print(f"Retryable error: {e}")
        # Implement retry logic
    else:
        print(f"Permanent error: {e}")
        # Handle permanent failure
```

#### `SchemaValidationError`

Raised when output doesn't match declared schema.

```python
from trident.errors import SchemaValidationError
```

**Common scenarios:**
- JSON output doesn't match schema
- Missing required fields
- Wrong field types

**Example:**
```yaml
# Prompt declares:
output:
  format: json
  schema:
    sentiment: string, Sentiment classification
    score: number, Confidence score
```

```python
# If LLM returns: {"sentiment": "positive"}
# Raises SchemaValidationError: Missing required field 'score'
```

#### `ConditionError`

Raised when evaluating edge conditions.

```python
from trident.errors import ConditionError
```

**Common scenarios:**
- Invalid condition syntax
- Reference to undefined fields
- Type errors in comparisons

**Example:**
```yaml
edges:
  conditional:
    from: classifier
    to: handler
    condition: "output.confidence > threshold"  # 'threshold' not defined
```

```python
try:
    result = run(project, inputs={...})
except ConditionError as e:
    print(f"Condition error: {e}")
    # e.g., "Undefined variable 'threshold' in condition"
```

#### `ToolError`

Raised during tool execution.

```python
from trident.errors import ToolError
```

**Common scenarios:**
- Python tool function not found
- Tool execution exception
- Invalid tool configuration

**Example:**
```python
# tools/processor.py - missing execute function
# Or execute() raises an exception

try:
    result = run(project, inputs={...})
except ToolError as e:
    print(f"Tool error: {e}")
    # e.g., "Tool 'processor' failed: function 'execute' not found"
```

#### `NodeExecutionError`

Raised when a node fails during execution.

```python
from trident.errors import NodeExecutionError
```

**Attributes:**
- `node_id: str` - Failed node identifier
- `node_type: str` - Node type
- `cause: Exception | None` - Original exception
- `cause_type: str | None` - Original exception type name
- `inputs: dict` - Node input data

**Common scenarios:**
- Node execution failure (wraps underlying error)
- Provides full context for debugging

**Example:**
```python
try:
    result = run(project, inputs={...})
except NodeExecutionError as e:
    print(f"Node '{e.node_id}' ({e.node_type}) failed")
    print(f"Cause: {e.cause_type}")
    print(f"Message: {e}")
    print(f"Inputs: {e.inputs}")

    # Check underlying cause
    if isinstance(e.cause, ProviderError):
        print("Provider error - check API key and rate limits")
```

### Error Handling Patterns

#### Basic Try-Catch

```python
from trident import load_project, run
from trident.errors import TridentError

try:
    project = load_project("./my-project")
    result = run(project, inputs={...})

    if result.success:
        print("Success:", result.outputs)
    else:
        print("Failed:", result.error)

except TridentError as e:
    print(f"Trident error: {e}")
    print(f"Exit code: {e.exit_code}")
```

#### Specific Error Handling

```python
from trident import load_project, run
from trident.errors import (
    ParseError,
    ValidationError,
    ProviderError,
    NodeExecutionError,
)

try:
    project = load_project("./my-project")
    result = run(project, inputs={...})

except ParseError as e:
    print(f"Parse error: {e}")
    print("Check YAML syntax in trident.yaml and .prompt files")

except ValidationError as e:
    print(f"Validation error: {e}")
    print("Check node references and configuration")

except ProviderError as e:
    print(f"Provider error: {e}")
    if e.retryable:
        print("This error may be retryable")
    else:
        print("Check API key and configuration")

except NodeExecutionError as e:
    print(f"Node '{e.node_id}' failed: {e}")
    print(f"Inputs: {e.inputs}")
```

#### Checking ExecutionResult

```python
# run() returns ExecutionResult even on failure
# Only unrecoverable errors (cycles, missing entrypoints) raise exceptions

result = run(project, inputs={...})

if result.success:
    print("✓ Execution succeeded")
    print(result.outputs)
else:
    print("✗ Execution failed")
    print(f"Error: {result.error}")

    # Get failed node
    failed_node = result.trace.failed_node
    if failed_node:
        print(f"Failed at: {failed_node.id}")
        print(f"Error type: {failed_node.error_type}")
        print(f"Error message: {failed_node.error}")
```

### Troubleshooting Tips

#### Parse Errors

**Problem:** `ParseError: Invalid YAML syntax`

**Solution:**
- Validate YAML syntax (use online validator)
- Check indentation (use spaces, not tabs)
- Ensure proper quoting of strings with special characters

#### Validation Errors

**Problem:** `ValidationError: Node 'X' referenced but not defined`

**Solution:**
- Check node IDs in edges match prompt file IDs
- Ensure prompt files exist in `prompts/` directory
- Verify node type is correct

#### DAG Errors

**Problem:** `DAGError: Cycle detected`

**Solution:**
- Review edge definitions for circular dependencies
- Use `trident project graph` to visualize DAG
- Ensure workflow has a clear direction

#### Provider Errors

**Problem:** `ProviderError: Rate limit exceeded`

**Solution:**
- Implement retry logic with exponential backoff
- Check provider rate limits
- Consider batching or throttling requests

**Problem:** `ProviderError: Invalid API key`

**Solution:**
- Set `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` environment variable
- Verify API key is valid and active
- Check API key permissions

#### Schema Validation Errors

**Problem:** `SchemaValidationError: Missing required field`

**Solution:**
- Review prompt output schema
- Check if LLM is returning correct format
- Consider making field optional or adding default

---

## Execution & Tracing

### Execution Flow

1. **Load project**: `load_project(path)` parses configuration
2. **Build DAG**: Construct execution graph, validate structure
3. **Topological sort**: Determine execution order
4. **Execute nodes**: Run nodes in dependency order
5. **Evaluate conditions**: Skip nodes based on condition expressions
6. **Map fields**: Transfer data between nodes via edge mappings
7. **Collect outputs**: Gather results from output nodes
8. **Return result**: `ExecutionResult` with outputs and trace

### Execution Modes

#### Normal Execution

```python
result = run(project, inputs={...})
```

- Executes all nodes
- Calls LLM providers
- Returns full trace with tokens and costs

#### Dry Run

```python
result = run(project, inputs={...}, dry_run=True)
```

- Simulates execution without LLM calls
- Returns mock data for testing
- Validates workflow structure
- No costs incurred

#### Verbose Execution

```python
result = run(project, inputs={...}, verbose=True)
```

- Prints node execution progress to stdout
- Shows node IDs as they execute
- Useful for monitoring long-running workflows

### Parallel Execution

Trident automatically executes independent nodes in parallel:

```yaml
# These nodes can run in parallel if they don't depend on each other
nodes:
  classifier_a:
    type: prompt
    # ...

  classifier_b:
    type: prompt
    # ...

edges:
  to_a:
    from: input
    to: classifier_a

  to_b:
    from: input
    to: classifier_b
```

### Conditional Execution

Nodes can be skipped based on condition expressions:

```yaml
edges:
  to_handler:
    from: classifier
    to: handler
    condition: "output.confidence > 0.8"

  to_reviewer:
    from: classifier
    to: reviewer
    condition: "output.confidence <= 0.8"
```

**Condition syntax:**
- Comparisons: `==`, `!=`, `<`, `>`, `<=`, `>=`
- Boolean: `and`, `or`, `not`
- Parentheses: `(expression)`
- Field access: `output.field.subfield`
- Literals: strings, numbers, `true`, `false`, `null`

**Example:**
```yaml
condition: "(output.category == 'urgent' or output.priority > 5) and output.confidence >= 0.9"
```

### Field Mapping

Map data from source to target nodes via edge mappings:

```yaml
edges:
  to_classifier:
    from: input
    to: classifier
    mapping:
      text: message                    # Simple field
      user_name: user.name              # Dot notation
      config_value: metadata.settings   # Nested access
```

**Mapping rules:**
- Source expressions support dot notation
- Target variables become input to target node
- Multiple mappings create combined input object

**Example flow:**
```yaml
# Input node output
{
  "message": "Hello",
  "user": {"name": "Alice", "id": 123},
  "metadata": {"settings": {"lang": "en"}}
}

# After mapping
{
  "text": "Hello",
  "user_name": "Alice",
  "config_value": {"lang": "en"}
}
```

### Tracing

Every execution produces a comprehensive trace:

```python
result = run(project, inputs={...})
trace = result.trace

# Execution metadata
print(f"Execution ID: {trace.execution_id}")
print(f"Duration: {trace.end_time - trace.start_time}")

# Per-node traces
for node in trace.nodes:
    print(f"\nNode: {node.id}")
    print(f"  Model: {node.model}")
    print(f"  Tokens: {node.input_tokens} in, {node.output_tokens} out")
    print(f"  Cost: ${node.cost_usd:.4f}")
    print(f"  Duration: {node.end_time - node.start_time}")

    if node.num_turns > 0:
        print(f"  Agent turns: {node.num_turns}")

# Aggregate metrics
total_tokens_in = sum(n.input_tokens for n in trace.nodes)
total_tokens_out = sum(n.output_tokens for n in trace.nodes)
total_cost = sum(n.cost_usd or 0 for n in trace.nodes)

print(f"\nTotal: {total_tokens_in} in, {total_tokens_out} out")
print(f"Total cost: ${total_cost:.4f}")
```

### Session Management

Agent nodes can be resumed from previous sessions:

```python
# First execution
result1 = run(project, inputs={...})

# Extract session IDs
sessions = {}
for node in result1.trace.nodes:
    if node.session_id:
        sessions[node.id] = node.session_id
        print(f"Agent '{node.id}' session: {node.session_id}")

# Resume execution
result2 = run(
    project,
    inputs={...},
    resume_sessions=sessions
)
```

---

## CLI Reference

Trident includes a command-line interface for project management and execution.

### Project Initialization

```bash
# Create new project
trident project init ./my-project

# With template
trident project init ./my-project --template minimal
```

### Project Validation

```bash
# Validate project structure
trident project validate ./my-project

# Outputs:
# ✓ trident.yaml parsed successfully
# ✓ All prompt files valid
# ✓ All edges reference valid nodes
# ✓ No cycles detected in DAG
```

### Project Visualization

```bash
# Generate DAG visualization
trident project graph ./my-project

# Output formats
trident project graph ./my-project --format dot
trident project graph ./my-project --format mermaid
```

### Project Execution

```bash
# Run project
trident project run ./my-project \
  --input '{"input": {"text": "hello"}}' \
  --verbose

# Dry run
trident project run ./my-project --dry-run

# Pretty output
trident project run ./my-project \
  --output pretty \
  --trace

# JSON output
trident project run ./my-project \
  --output json > result.json
```

---

## Complete Example

Combining all concepts into a full workflow:

### Project Structure

```
sentiment-analyzer/
├── trident.yaml
├── prompts/
│   ├── classifier.prompt
│   ├── analyzer.prompt
│   └── reporter.prompt
└── tools/
    └── preprocessing.py
```

### trident.yaml

```yaml
trident: "0.2"
name: sentiment-analyzer
version: "1.0"
description: Multi-stage sentiment analysis with agent-based review

defaults:
  model: anthropic/claude-sonnet-4-20250514
  temperature: 0.3
  max_tokens: 2000

entrypoints:
  - input

nodes:
  input:
    type: input
    schema:
      feedback: string, Customer feedback text
      customer_id: string, Customer identifier

  preprocessor:
    type: tool
    tool: clean_text

  analyzer:
    type: agent
    prompt: prompts/analyzer.prompt
    allowed_tools: [Read, Grep]
    max_turns: 10
    permission_mode: bypassPermissions

  output:
    type: output
    format: json

edges:
  to_preprocessor:
    from: input
    to: preprocessor
    mapping:
      text: feedback

  to_classifier:
    from: preprocessor
    to: classifier
    mapping:
      text: result.cleaned_text

  high_confidence:
    from: classifier
    to: reporter
    condition: "output.confidence >= 0.8"
    mapping:
      sentiment: output.sentiment
      confidence: output.confidence
      original_text: feedback

  low_confidence:
    from: classifier
    to: analyzer
    condition: "output.confidence < 0.8"
    mapping:
      text: feedback
      initial_classification: output.sentiment
      confidence: output.confidence

  analyzer_to_reporter:
    from: analyzer
    to: reporter
    mapping:
      sentiment: output.final_sentiment
      confidence: output.final_confidence
      analysis: output.detailed_analysis
      original_text: feedback

  to_output:
    from: reporter
    to: output
    mapping:
      customer_id: customer_id
      sentiment: output.sentiment
      confidence: output.confidence
      summary: output.summary

tools:
  clean_text:
    type: python
    module: tools.preprocessing
    function: execute
    description: Clean and normalize text
```

### prompts/classifier.prompt

```prompt
---
id: classifier
name: Sentiment Classifier
description: Quick sentiment classification

temperature: 0.2
max_tokens: 500

input:
  text:
    type: string
    description: Text to classify

output:
  format: json
  schema:
    sentiment: string, Sentiment (positive/negative/neutral)
    confidence: number, Confidence score 0-1
    key_phrases: array, Important phrases that influenced decision
---
Classify the sentiment of the following feedback:

{{text}}

Consider the overall tone, specific words, and context.

Return JSON with sentiment (positive/negative/neutral), confidence score, and key phrases.
```

### prompts/analyzer.prompt

```prompt
---
id: analyzer
name: Deep Sentiment Analyzer
description: Agent-based deep analysis for low-confidence cases

model: anthropic/claude-sonnet-4-20250514
temperature: 0.4

input:
  text:
    type: string
    description: Original feedback text
  initial_classification:
    type: string
    description: Initial sentiment classification
  confidence:
    type: number
    description: Initial confidence score

output:
  format: json
  schema:
    final_sentiment: string, Final sentiment determination
    final_confidence: number, Final confidence score
    detailed_analysis: string, Detailed analysis explanation
    evidence: array, Supporting evidence from text
---
The initial classifier had low confidence ({{confidence}}) classifying this feedback as {{initial_classification}}.

Feedback: {{text}}

Use the Read and Grep tools to search for similar feedback examples in the knowledge base.
Perform a detailed analysis considering:
1. Contextual clues
2. Sarcasm or irony
3. Mixed sentiments
4. Domain-specific language

Return JSON with your final sentiment determination, confidence, detailed analysis, and supporting evidence.
```

### prompts/reporter.prompt

```prompt
---
id: reporter
name: Report Generator
description: Generate final sentiment report

temperature: 0.3

input:
  sentiment:
    type: string
    description: Determined sentiment
  confidence:
    type: number
    description: Confidence score
  original_text:
    type: string
    description: Original feedback
  analysis:
    type: string
    description: Detailed analysis (optional)
    required: false
    default: ""

output:
  format: json
  schema:
    sentiment: string, Final sentiment
    confidence: number, Confidence score
    summary: string, Brief summary for customer
    internal_notes: string, Internal notes for review
---
Generate a final report for this sentiment analysis:

Original Feedback: {{original_text}}
Sentiment: {{sentiment}}
Confidence: {{confidence}}
{{#if analysis}}
Detailed Analysis: {{analysis}}
{{/if}}

Create a brief customer-facing summary and internal notes.
Return JSON with sentiment, confidence, summary, and internal_notes.
```

### tools/preprocessing.py

```python
import re

def execute(text: str) -> dict:
    """Clean and normalize text."""
    # Remove extra whitespace
    cleaned = re.sub(r'\s+', ' ', text.strip())

    # Remove special characters
    cleaned = re.sub(r'[^\w\s.,!?-]', '', cleaned)

    # Normalize case
    cleaned = cleaned.lower()

    return {
        "cleaned_text": cleaned,
        "original_length": len(text),
        "cleaned_length": len(cleaned),
        "removed_chars": len(text) - len(cleaned)
    }
```

### Python Usage

```python
from trident import load_project, run

# Load project
project = load_project("./sentiment-analyzer")

# Run analysis
result = run(
    project,
    inputs={
        "input": {
            "feedback": "Great product but the delivery was really slow!",
            "customer_id": "C12345"
        }
    },
    verbose=True,
    on_agent_message=lambda msg_type, content:
        print(f"[Agent {msg_type}] {content}")
)

# Check results
if result.success:
    output = result.outputs["output"]
    print(f"\nCustomer: {output['customer_id']}")
    print(f"Sentiment: {output['sentiment']}")
    print(f"Confidence: {output['confidence']:.2f}")
    print(f"Summary: {output['summary']}")

    # Print trace summary
    print(f"\n{result.summary()}")
else:
    print(f"Error: {result.error}")
    failed = result.trace.failed_node
    if failed:
        print(f"Failed at: {failed.id}")
        print(f"Error: {failed.error}")
```

### CLI Usage

```bash
# Validate project
trident project validate ./sentiment-analyzer

# Visualize workflow
trident project graph ./sentiment-analyzer --format mermaid

# Run analysis
trident project run ./sentiment-analyzer \
  --input '{
    "input": {
      "feedback": "Amazing service!",
      "customer_id": "C67890"
    }
  }' \
  --verbose \
  --output pretty \
  --trace

# Dry run
trident project run ./sentiment-analyzer --dry-run
```

---

## Additional Resources

### Model Identifiers

Format: `provider/model-name`

**Anthropic:**
- `anthropic/claude-sonnet-4-20250514`
- `anthropic/claude-opus-4-20250514`
- `anthropic/claude-3-5-sonnet-20241022`

**OpenAI:**
- `openai/gpt-4-turbo`
- `openai/gpt-4`
- `openai/gpt-3.5-turbo`

### Environment Variables

- `ANTHROPIC_API_KEY` - Anthropic API key
- `OPENAI_API_KEY` - OpenAI API key
- `TRIDENT_WORKSPACE` - Default workspace directory for agents

### Best Practices

1. **Use descriptive node IDs** - Make workflows self-documenting
2. **Add descriptions** - Document intent in frontmatter
3. **Validate early** - Use `trident project validate` before running
4. **Start with dry runs** - Test structure before incurring costs
5. **Monitor token usage** - Check traces for optimization opportunities
6. **Handle errors gracefully** - Always check `result.success`
7. **Use conditions wisely** - Route complex cases to agents
8. **Limit agent turns** - Prevent runaway execution
9. **Version control** - Track changes to prompts and configuration
10. **Test incrementally** - Build workflows step by step

---

**Version:** 0.2
**Last Updated:** 2025-01-05
