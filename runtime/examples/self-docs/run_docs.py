"""Run the Trident self-documentation workflow."""

import json
import os
import sys
from pathlib import Path

if not os.environ.get("ANTHROPIC_API_KEY"):
    print("ERROR: ANTHROPIC_API_KEY not set")
    sys.exit(1)

from trident.executor import run
from trident.project import load_project

# Track agent messages
messages = []


def on_message(msg_type: str, content):
    """Track agent messages for analysis."""
    messages.append((msg_type, content))
    if msg_type == "assistant":
        preview = str(content)[:200].replace("\n", " ")
        print(f"  [AGENT] {preview}...")
    elif msg_type == "tool_use":
        print(f"  [TOOL] {content.get('name', 'unknown')}")
    elif msg_type == "result":
        print(
            f"  [RESULT] turns={content.get('num_turns')}, cost=${content.get('cost_usd', 0):.4f}"
        )


# Paths
project_path = Path(__file__).parent
codebase_path = project_path.parent.parent  # trident/runtime
output_dir = project_path / "output"
checkpoint_dir = project_path / ".trident" / "checkpoints"

# Ensure output dir exists
output_dir.mkdir(exist_ok=True)

# Check for resume argument
resume_from = None
if len(sys.argv) > 1 and sys.argv[1] == "--resume":
    if len(sys.argv) > 2:
        resume_from = sys.argv[2]
    else:
        # Find most recent checkpoint
        if checkpoint_dir.exists():
            checkpoints = sorted(checkpoint_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
            if checkpoints:
                resume_from = checkpoints[-1]
                print(f"Resuming from most recent checkpoint: {resume_from.name}")

print("=" * 70, flush=True)
print("Trident Self-Documentation Workflow", flush=True)
print("=" * 70, flush=True)
print(f"Codebase: {codebase_path}", flush=True)
print(f"Output: {output_dir}", flush=True)
print(f"Checkpoints: {checkpoint_dir}", flush=True)
if resume_from:
    print(f"Resuming from: {resume_from}", flush=True)
print(flush=True)

# Load and run
project = load_project(project_path)
print(f"Project: {project.name}")
print(f"Agents: {list(project.agents.keys())}")
print()

print("Starting execution...")
print("-" * 70)

result = run(
    project,
    inputs={
        "codebase_path": str(codebase_path),
        "output_dir": str(output_dir),
    },
    verbose=True,
    on_agent_message=on_message,
    checkpoint_dir=checkpoint_dir,
    resume_from=resume_from,
)

print("-" * 70)
print()

# Results
print("=" * 70)
print("RESULTS")
print("=" * 70)
print(f"Success: {result.success}")

if result.error:
    print(f"Error: {result.error}")

print("\nNode Execution Summary:")
total_cost = 0.0
for node in result.trace.nodes:
    status = "SKIPPED" if node.skipped else ("ERROR" if node.error else "OK")
    cost = node.cost_usd or 0
    total_cost += cost
    turns = node.num_turns or 0
    print(f"  {node.id}: {status} (turns={turns}, cost=${cost:.4f})")
    if node.error:
        print(f"    Error: {node.error}")

print(f"\nTotal cost: ${total_cost:.4f}")

print("\nFinal Output:")
print(json.dumps(result.outputs, indent=2, default=str))

# Save trace for analysis
trace_file = output_dir / "execution_trace.json"
trace_data = {
    "success": result.success,
    "error": str(result.error) if result.error else None,
    "total_cost": total_cost,
    "nodes": [
        {
            "id": n.id,
            "skipped": n.skipped,
            "error": n.error,
            "cost_usd": n.cost_usd,
            "num_turns": n.num_turns,
            "session_id": n.session_id,
        }
        for n in result.trace.nodes
    ],
    "outputs": result.outputs,
}
trace_file.write_text(json.dumps(trace_data, indent=2, default=str))
print(f"\nTrace saved to: {trace_file}")
