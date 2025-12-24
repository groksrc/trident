"""CLI entry point for Trident."""

import argparse
import json
import sys
from pathlib import Path

from . import ExitCode, TridentError, __version__, load_project, run


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

    # project validate
    validate_parser = project_subparsers.add_parser("validate", help="Validate a Trident project")
    validate_parser.add_argument(
        "path", nargs="?", default=".", help="Path to project (default: .)"
    )

    # project graph
    graph_parser = project_subparsers.add_parser("graph", help="Visualize the project DAG")
    graph_parser.add_argument("path", nargs="?", default=".", help="Path to project (default: .)")

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

    # Check if already a trident project
    manifest_path = path / "trident.yaml"
    if manifest_path.exists():
        print(f"Error: {path} already contains a trident.yaml", file=sys.stderr)
        return ExitCode.VALIDATION_ERROR

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
    print("  Manifest: trident.yaml")
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
    from .dag import build_dag

    project = load_project(args.path)
    dag = build_dag(project)

    print(f"Valid: {project.name}")
    print(f"  Prompts: {len(project.prompts)}")
    print(f"  Edges: {len(project.edges)}")
    print(f"  Nodes in execution order: {len(dag.execution_order)}")
    return 0


def cmd_project_graph(args) -> int:
    """Visualize the project DAG."""
    from .dag import build_dag, visualize_dag

    project = load_project(args.path)
    dag = build_dag(project)

    print(visualize_dag(dag))
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

    # Execute
    result = run(
        project,
        entrypoint=args.entrypoint,
        inputs=inputs,
        dry_run=args.dry_run,
        verbose=args.verbose,
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
                "execution_id": result.trace.execution_id,
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
