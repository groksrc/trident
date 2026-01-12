"""CLI entry point for Trident."""

import argparse
import json
import sys
from pathlib import Path

from . import (
    ExitCode,
    RunManifest,
    TridentError,
    __version__,
    find_latest_run,
    load_project,
    run,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="trident",
        description="Trident - Lightweight agent orchestration runtime",
    )
    parser.add_argument("--version", action="version", version=f"trident {__version__}")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Version command
    subparsers.add_parser("version", help="Show version")

    # Project command with subcommands
    project_parser = subparsers.add_parser("project", help="Project commands")
    project_subparsers = project_parser.add_subparsers(
        dest="subcommand", help="Project subcommands"
    )

    # project init
    init_parser = project_subparsers.add_parser("init", help="Create a new Trident project")
    init_parser.add_argument(
        "path", nargs="?", default=".", help="Path to create project (default: .)"
    )
    init_parser.add_argument(
        "--template",
        "-t",
        choices=["minimal", "standard"],
        default="minimal",
        help="Project template (default: minimal)",
    )

    # project run
    run_parser = project_subparsers.add_parser("run", help="Execute a Trident pipeline")
    run_parser.add_argument("path", nargs="?", default=".", help="Path to project (default: .)")
    run_parser.add_argument("--input", "-i", help="JSON input data")
    run_parser.add_argument("--input-file", "-f", help="Path to JSON input file")
    run_parser.add_argument("--entrypoint", "-e", help="Starting node ID")
    run_parser.add_argument(
        "--output",
        "-o",
        choices=["json", "text", "pretty"],
        default="pretty",
        help="Output format (default: pretty)",
    )
    run_parser.add_argument("--trace", action="store_true", help="Output execution trace")
    run_parser.add_argument("--dry-run", action="store_true", help="Simulate without LLM calls")
    run_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show node execution progress"
    )
    # Artifact options
    run_parser.add_argument(
        "--no-artifacts",
        action="store_true",
        help="Disable artifact persistence (default: artifacts saved to .trident/)",
    )
    run_parser.add_argument(
        "--artifact-dir",
        help="Custom directory for artifacts (default: .trident/)",
    )
    run_parser.add_argument(
        "--run-id",
        help="Custom run ID (default: auto-generated UUID)",
    )
    run_parser.add_argument(
        "--resume",
        help='Resume from a previous run. Use run ID or "latest"',
    )

    # project validate
    validate_parser = project_subparsers.add_parser("validate", help="Validate a Trident project")
    validate_parser.add_argument(
        "path", nargs="?", default=".", help="Path to project (default: .)"
    )
    validate_parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors (e.g., edge mapping mismatches)",
    )

    # project graph
    graph_parser = project_subparsers.add_parser("graph", help="Visualize the project DAG")
    graph_parser.add_argument("path", nargs="?", default=".", help="Path to project (default: .)")
    graph_parser.add_argument(
        "--format",
        "-f",
        choices=["ascii", "mermaid"],
        default="ascii",
        help="Output format (default: ascii)",
    )
    graph_parser.add_argument(
        "--direction",
        "-d",
        choices=["TD", "LR", "BT", "RL"],
        default="TD",
        help="Mermaid flow direction: TD (top-down), LR (left-right), etc.",
    )
    graph_parser.add_argument(
        "--open",
        action="store_true",
        help="Open Mermaid diagram in browser (mermaid.live)",
    )

    # project runs
    runs_parser = project_subparsers.add_parser("runs", help="List past runs")
    runs_parser.add_argument("path", nargs="?", default=".", help="Path to project (default: .)")
    runs_parser.add_argument(
        "--limit", "-n", type=int, default=10, help="Number of runs to show (default: 10)"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    try:
        if args.command == "version":
            return cmd_version()
        elif args.command == "project":
            if not args.subcommand:
                project_parser.print_help()
                return 0
            if args.subcommand == "init":
                return cmd_project_init(args)
            elif args.subcommand == "run":
                return cmd_project_run(args)
            elif args.subcommand == "validate":
                return cmd_project_validate(args)
            elif args.subcommand == "graph":
                return cmd_project_graph(args)
            elif args.subcommand == "runs":
                return cmd_project_runs(args)
    except TridentError as e:
        print(f"Error: {e}", file=sys.stderr)
        return e.exit_code
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return ExitCode.RUNTIME_ERROR

    return 0


def cmd_version() -> int:
    """Show version."""
    print(f"trident {__version__}")
    return 0


def cmd_project_init(args) -> int:
    """Create a new project."""
    path = Path(args.path).resolve()

    # Create directory if it doesn't exist
    path.mkdir(parents=True, exist_ok=True)

    # Check if already a trident project (any manifest format)
    for existing in ["agent.tml", "trident.tml", "trident.yaml"]:
        if (path / existing).exists():
            print(f"Error: {path} already contains {existing}", file=sys.stderr)
            return ExitCode.VALIDATION_ERROR
    manifest_path = path / "agent.tml"

    # Determine project name from directory
    project_name = path.name if path.name != "." else Path.cwd().name

    # Create manifest
    manifest_content = f"""trident: "0.1"
name: {project_name}
description: A Trident project

defaults:
  model: anthropic/claude-sonnet-4-20250514
  temperature: 0.7
  max_tokens: 1024

entrypoints:
  - input

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
    to: example
    mapping:
      content: text

  e2:
    from: example
    to: output
    mapping:
      result: output
"""
    manifest_path.write_text(manifest_content)

    # Create prompts directory
    prompts_dir = path / "prompts"
    prompts_dir.mkdir(exist_ok=True)

    # Create example prompt
    example_prompt = """---
id: example
name: Example Prompt
description: An example prompt that echoes input

input:
  content:
    type: string
    description: The content to process

output:
  format: json
  schema:
    result: string, The processed result
    length: number, Length of the input
---
You are a helpful assistant. Process the following input and return a result.

Input: {{content}}

Respond with a JSON object containing:
- result: A brief summary or echo of the input
- length: The character count of the input
"""
    (prompts_dir / "example.prompt").write_text(example_prompt)

    # Create additional files for standard template
    if args.template == "standard":
        (path / "tools").mkdir(exist_ok=True)
        (path / "schemas").mkdir(exist_ok=True)

        # Create example tool
        tool_content = '''"""Example tool for Trident."""


def process(text: str) -> dict:
    """Process text and return metadata."""
    return {
        "word_count": len(text.split()),
        "char_count": len(text),
    }
'''
        (path / "tools" / "example_tool.py").write_text(tool_content)

    print(f"Created Trident project at {path}")
    print(f"  Template: {args.template}")
    print("  Manifest: agent.tml")
    print("  Prompts:  prompts/example.prompt")
    if args.template == "standard":
        print("  Tools:    tools/")
        print("  Schemas:  schemas/")
    print()
    print("Next steps:")
    print(f"  cd {path}")
    print("  trident project validate")
    print("  trident project run --dry-run")

    return 0


def cmd_project_validate(args) -> int:
    """Validate a project."""
    from .dag import build_dag, validate_edge_mappings, validate_subworkflows

    project = load_project(args.path)
    dag = build_dag(project)

    # Validate edge mappings
    validation = validate_edge_mappings(project, dag, strict=args.strict)

    # Validate sub-workflows (recursive)
    subworkflow_validation = validate_subworkflows(project, strict=args.strict)

    # Merge results
    all_warnings = validation.warnings + subworkflow_validation.warnings
    all_errors = validation.errors + subworkflow_validation.errors
    all_valid = validation.valid and subworkflow_validation.valid

    print(f"Project: {project.name}")
    print(f"  Prompts: {len(project.prompts)}")
    print(f"  Tools: {len(project.tools)}")
    print(f"  Agents: {len(project.agents)}")
    print(f"  Branches: {len(project.branches)}")
    print(f"  Edges: {len(project.edges)}")
    print(f"  Nodes in execution order: {len(dag.execution_order)}")
    print()

    # Show warnings
    if all_warnings:
        print("Warnings:")
        for warning in all_warnings:
            edge_info = f" (edge: {warning.edge_id})" if warning.edge_id else ""
            print(f"  ⚠ {warning.message}{edge_info}")
        print()

    # In strict mode, warnings are errors
    if args.strict and all_warnings:
        print(f"FAILED: {len(all_warnings)} warning(s) in strict mode", file=sys.stderr)
        return ExitCode.VALIDATION_ERROR

    if all_valid:
        print("✓ Validation passed")
        return 0
    else:
        print(f"✗ Validation failed: {len(all_errors)} error(s)", file=sys.stderr)
        for error in all_errors:
            print(f"  ✗ {error}", file=sys.stderr)
        return ExitCode.VALIDATION_ERROR


def cmd_project_graph(args) -> int:
    """Visualize the project DAG."""
    import base64
    import webbrowser
    import zlib

    from .dag import build_dag, visualize_dag, visualize_dag_mermaid

    project = load_project(args.path)
    dag = build_dag(project)

    if args.format == "mermaid" or args.open:
        mermaid_output = visualize_dag_mermaid(dag, direction=args.direction)

        if args.open:
            # Extract just the mermaid code (without ```mermaid wrapper)
            mermaid_code = mermaid_output.replace("```mermaid\n", "").replace("\n```", "")

            # Encode for mermaid.live URL
            # mermaid.live uses pako compression + base64
            json_state = json.dumps(
                {
                    "code": mermaid_code,
                    "mermaid": {"theme": "default"},
                    "autoSync": True,
                    "updateDiagram": True,
                }
            )
            compressed = zlib.compress(json_state.encode("utf-8"), level=9)
            encoded = base64.urlsafe_b64encode(compressed).decode("ascii")
            url = f"https://mermaid.live/edit#pako:{encoded}"

            print("Opening diagram in browser...")
            print(f"URL: {url[:80]}...")
            webbrowser.open(url)
        else:
            print(mermaid_output)
    else:
        print(visualize_dag(dag))

    return 0


def cmd_project_runs(args) -> int:
    """List past runs for a project."""
    project_path = Path(args.path).resolve()
    manifest_path = project_path / ".trident" / "runs" / "manifest.json"

    manifest = RunManifest.load(manifest_path)

    if not manifest.runs:
        print("No runs found.")
        print(f"  Run a project with: trident project run {args.path}")
        return 0

    # Show most recent runs (reversed, limited)
    runs_to_show = list(reversed(manifest.runs))[: args.limit]

    print(f"Recent runs ({len(runs_to_show)} of {len(manifest.runs)}):")
    print()

    for run_entry in runs_to_show:
        status_icon = {
            "completed": "✓",
            "failed": "✗",
            "running": "…",
            "interrupted": "⊘",
        }.get(run_entry.status, "?")

        success_str = ""
        if run_entry.success is not None:
            success_str = " (success)" if run_entry.success else " (failed)"

        print(f"  [{status_icon}] {run_entry.run_id[:8]}...")
        print(f"      Status: {run_entry.status}{success_str}")
        print(f"      Started: {run_entry.started_at}")
        if run_entry.ended_at:
            print(f"      Ended: {run_entry.ended_at}")
        if run_entry.error_summary:
            print(f"      Error: {run_entry.error_summary[:60]}...")
        print()

    print(f"Artifacts directory: {project_path / '.trident' / 'runs'}")
    return 0


def cmd_project_run(args) -> int:
    """Execute a pipeline."""
    project = load_project(args.path)

    # Parse inputs
    inputs = {}
    if args.input:
        inputs = json.loads(args.input)
    elif args.input_file:
        with open(args.input_file) as f:
            inputs = json.load(f)

    # Determine artifact directory (default: .trident/ unless --no-artifacts)
    artifact_dir = None
    if not args.no_artifacts:
        if args.artifact_dir:
            artifact_dir = Path(args.artifact_dir)
        else:
            artifact_dir = project.root / ".trident"

    # Handle resume
    resume_from = None
    if args.resume:
        if args.resume == "latest":
            resume_from = find_latest_run(project.root)
            if not resume_from:
                print("Error: No previous runs found to resume", file=sys.stderr)
                return ExitCode.VALIDATION_ERROR
            if args.verbose:
                print(f"Resuming from latest run: {resume_from}")
        else:
            resume_from = args.resume

    # Execute
    result = run(
        project,
        entrypoint=args.entrypoint,
        inputs=inputs,
        dry_run=args.dry_run,
        verbose=args.verbose,
        artifact_dir=artifact_dir,
        run_id=args.run_id,
        resume_from=resume_from,
    )

    # Output
    if args.output == "json":
        output = {
            "success": result.success,
            "outputs": result.outputs,
        }
        if result.error:
            output["error"] = {
                "node_id": result.error.node_id,
                "node_type": result.error.node_type,
                "message": str(result.error.args[0]),
                "cause_type": result.error.cause_type,
            }
        if args.trace:
            output["trace"] = {
                "run_id": result.trace.run_id,
                "start_time": result.trace.start_time,
                "end_time": result.trace.end_time,
                "nodes": [
                    {
                        "id": n.id,
                        "start_time": n.start_time,
                        "end_time": n.end_time,
                        "model": n.model,
                        "tokens": n.tokens,
                        "skipped": n.skipped,
                        "error": n.error,
                        "error_type": n.error_type,
                    }
                    for n in result.trace.nodes
                ],
            }
        print(json.dumps(output, indent=2))

    elif args.output == "text":
        if not result.success:
            print(f"FAILED: {result.error}", file=sys.stderr)
        elif isinstance(result.outputs, dict):
            for _key, value in result.outputs.items():
                if isinstance(value, dict):
                    print(json.dumps(value))
                else:
                    print(value)
        else:
            print(result.outputs)

    else:  # pretty
        if result.success:
            print("=== Execution Complete ===")
        else:
            print("=== Execution FAILED ===")
        print()

        if args.trace or not result.success:
            print("Trace:")
            for node in result.trace.nodes:
                if node.error:
                    status = "FAILED"
                elif node.skipped:
                    status = "SKIPPED"
                else:
                    status = "OK"
                tokens = (
                    f" ({node.tokens.get('input', 0)}+{node.tokens.get('output', 0)} tokens)"
                    if node.tokens
                    else ""
                )
                error_msg = f" - {node.error}" if node.error else ""
                print(f"  [{status}] {node.id}{tokens}{error_msg}")
            print()

        if result.error:
            print("Error:")
            print(f"  {result.error}")
            print()

        print("Outputs:")
        print(json.dumps(result.outputs, indent=2))

    # Return appropriate exit code
    if result.error:
        return result.error.exit_code
    return 0


if __name__ == "__main__":
    sys.exit(main())
