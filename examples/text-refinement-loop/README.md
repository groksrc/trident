# Text Refinement Loop Example

Demonstrates iterative refinement using Trident branch nodes with `loop_while`.

## What This Shows

- **Branch node with looping**: Sub-workflow re-executes until quality threshold is met
- **Loop condition**: `needs_refinement == true` evaluated after each iteration
- **Max iterations**: Safety limit of 3 prevents infinite loops
- **Output-to-input flow**: Each iteration receives the previous iteration's output
- **Proper sub-workflow isolation**: Sub-workflow in separate directory with own prompts

## Structure

```
text-refinement-loop/
├── agent.tml              # Main workflow
├── workflows/
│   ├── quality-loop.tml   # Sub-workflow that loops
│   └── prompts/
│       └── process.prompt # Evaluation and refinement logic
└── README.md
```

## How It Works

### Main Workflow (`agent.tml`)

1. Takes text input
2. Calls `refine_loop` branch node
3. Branch node executes sub-workflow repeatedly until:
   - `needs_refinement == false` (quality score >= 85), OR
   - Max iterations (3) reached
4. Outputs final result

### Sub-Workflow (`workflows/quality-loop.tml`)

Single-pass workflow that:
1. Receives text input
2. Evaluates quality (grammar, clarity, completeness)
3. Refines text if quality score < 85
4. Returns:
   - `text`: refined version (or original if quality good)
   - `quality_score`: numeric score 0-100
   - `needs_refinement`: boolean flag for loop condition

### Iteration Flow

```
Iteration 0:
  Input: "this text has many mistake and need improve"
  Output: "This text contains several grammatical errors and requires improvement."
  Score: 75, needs_refinement: true → LOOP

Iteration 1:
  Input: (previous output)
  Output: "This text demonstrates several grammatical errors..."
  Score: 75, needs_refinement: true → LOOP

Iteration 2:
  Input: (previous output)
  Output: (similar refinement)
  Score: 72, needs_refinement: true → LOOP

Iteration 3:
  Max iterations reached → FAIL with BranchError
```

## Running the Example

### Prerequisites

```bash
cd ~/code/trident/runtime
uv pip install -e .
```

### Set API Key

Create `.env` file in example directory:
```bash
ANTHROPIC_API_KEY=sk-ant-...
```

### Validate

```bash
cd ~/code/trident/examples/text-refinement-loop
python -m trident project validate
```

### Run

```bash
python -m trident project run \
  --input '{"text": "this text has many mistake and need improve"}' \
  --verbose
```

### Check Iteration Artifacts

```bash
# Find the run ID
ls .trident/runs/

# View iteration outputs
cat .trident/runs/<run-id>/branches/refine_loop/iteration_*.json
```

Each iteration saves:
- `inputs` - what the sub-workflow received
- `outputs` - what it produced
- `started_at`, `ended_at` - timing
- `success` - whether it succeeded

## Expected Behavior

**Success case** (quality threshold met):
- Loop terminates when `needs_refinement == false`
- Branch node outputs final refined text

**Max iterations case** (threshold never met):
- Loop runs 3 times
- Fails with `BranchError: Max iterations (3) reached`
- This is **by design** - prompts intentionally keep score < 85 to demonstrate loop

## Key Learnings

### ✓ Correct Patterns

1. **Sub-workflow isolation**:
   - Sub-workflow in `workflows/` subdirectory
   - Prompts in `workflows/prompts/`
   - Prevents DAG construction conflicts

2. **Output matches input schema**:
   - Sub-workflow outputs `text` field
   - Next iteration can use it as input
   - Required for loops to work

3. **Loop condition on output fields**:
   - Direct field access: `needs_refinement == true`
   - No template syntax needed
   - Evaluated after each iteration

### ✗ Common Mistakes

1. **Shared prompts directory**:
   - Sub-workflow sharing main workflow's `prompts/` causes conflicts
   - Trident loads all prompts during DAG construction

2. **Output schema mismatch**:
   - If sub-workflow output doesn't include input fields
   - Next iteration fails with "Missing required input"

3. **Testing with dry-run**:
   - Dry runs skip branch node execution
   - Must use real execution to test loops

4. **Cycles in main DAG**:
   - Cannot create loops with edges in main workflow
   - Must use branch nodes with `loop_while` instead

## Modifying This Example

**Change quality threshold:**
Edit `workflows/prompts/process.prompt`:
```yaml
needs_refinement: boolean, True if score < 90  # Increase threshold
```

**Add more iteration data:**
Edit sub-workflow output mapping:
```yaml
e2:
  from: process
  to: loop_output
  mapping:
    text: text
    needs_refinement: needs_refinement
    quality_score: quality_score
    iteration_count: iteration_count  # Add iteration tracking
```

**Change max iterations:**
Edit main workflow:
```yaml
refine_loop:
  type: branch
  workflow: ./workflows/quality-loop.tml
  loop_while: "needs_refinement == true"
  max_iterations: 5  # Increase limit
```

## Related Examples

- `support-triage/` - Conditional branching without loops
- `dev-team/` - Multi-agent workflows
- `browser-screenshot/` - Agent nodes with MCP tools
