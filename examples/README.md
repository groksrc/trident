# Trident Examples

Learn Trident through progressive examples, from basic workflows to advanced patterns.

## Prerequisites

1. Install dependencies:
   ```bash
   cd runtime
   uv sync
   ```

2. Set your API key:
   ```bash
   export ANTHROPIC_API_KEY=sk-ant-...
   ```

## Running Examples

From the `runtime/` directory:

```bash
# Basic syntax
uv run python -m trident project run ../examples/<example-name> --input '{"key": "value"}'

# With verbose output
uv run python -m trident project run ../examples/<example-name> --input-file input.json --verbose

# Validate without running
uv run python -m trident project validate ../examples/<example-name>
```

## Examples

### 1. hello-world
**Concepts:** Input nodes, prompt nodes, output nodes, edge mappings

The simplest possible workflow - takes a name and generates a greeting.

```bash
uv run python -m trident project run ../examples/hello-world --input '{"name": "World"}'
```

### 2. branching-demo
**Concepts:** Conditional edges, classification, routing

Routes messages to different handlers based on sentiment classification.

```bash
uv run python -m trident project run ../examples/branching-demo --input '{"message": "I got promoted!"}'
uv run python -m trident project run ../examples/branching-demo --input '{"message": "I lost my job"}'
```

### 3. looping-demo
**Concepts:** Branch nodes, loop_while, iterative refinement

Refines text iteratively until quality threshold is met.

```bash
uv run python -m trident project run ../examples/looping-demo \
  --input '{"text": "the quick brown fox jump over lazy dog"}' \
  --verbose
```

### 4. tools-demo
**Concepts:** Python tools, external functions, data transformation

Calls a Python function to get data, then summarizes it with an LLM.

```bash
uv run python -m trident project run ../examples/tools-demo --input '{"city": "Austin"}'
```

### 5. workflows-demo
**Concepts:** Trigger nodes, skills, workflow composition

Composes multiple workflows: research skill → summarize skill.

```bash
uv run python -m trident project run ../examples/workflows-demo \
  --input '{"topic": "octopuses"}' \
  --verbose
```

## Project Structure

Each example follows this structure:

```
example-name/
├── agent.tml           # Workflow definition
├── prompts/            # Prompt templates
│   └── *.prompt
├── tools/              # Python tools (if any)
│   └── *.py
└── skills/             # Sub-workflows (if any)
    └── skill-name/
        ├── agent.tml
        └── prompts/
```

## Next Steps

- Read `SKILL.md` for comprehensive documentation
- Explore the `runtime/` source code
- Build your own workflows!
