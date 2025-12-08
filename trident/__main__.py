"""CLI entry point for Trident."""

import argparse
import json
import sys

from . import ExitCode, TridentError, load_project, run


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="trident",
        description="Trident - Lightweight agent orchestration runtime",
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Run command
    run_parser = subparsers.add_parser("run", help="Execute a Trident pipeline")
    run_parser.add_argument("project", nargs="?", default=".", help="Path to project")
    run_parser.add_argument("--input", "-i", help="JSON input data")
    run_parser.add_argument("--input-file", "-f", help="Path to JSON input file")
    run_parser.add_argument("--entrypoint", "-e", help="Starting node ID")
    run_parser.add_argument(
        "--output",
        "-o",
        choices=["json", "text", "pretty"],
        default="pretty",
        help="Output format",
    )
    run_parser.add_argument("--trace", action="store_true", help="Output execution trace")

    # Validate command
    validate_parser = subparsers.add_parser("validate", help="Validate a Trident project")
    validate_parser.add_argument("project", nargs="?", default=".", help="Path to project")

    # List command
    list_parser = subparsers.add_parser("list", help="List nodes and edges")
    list_parser.add_argument("project", nargs="?", default=".", help="Path to project")
    list_parser.add_argument(
        "--format",
        choices=["text", "json", "mermaid"],
        default="text",
        help="Output format",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    try:
        if args.command == "validate":
            return cmd_validate(args)
        elif args.command == "run":
            return cmd_run(args)
        elif args.command == "list":
            return cmd_list(args)
    except TridentError as e:
        print(f"Error: {e}", file=sys.stderr)
        return e.exit_code
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        return ExitCode.RUNTIME_ERROR

    return 0


def cmd_validate(args) -> int:
    """Validate a project."""
    from .dag import build_dag

    project = load_project(args.project)
    dag = build_dag(project)

    print(f"Valid: {project.name}")
    print(f"  Prompts: {len(project.prompts)}")
    print(f"  Edges: {len(project.edges)}")
    print(f"  Nodes in execution order: {len(dag.execution_order)}")
    return 0


def cmd_run(args) -> int:
    """Execute a pipeline."""
    project = load_project(args.project)

    # Parse inputs
    inputs = {}
    if args.input:
        inputs = json.loads(args.input)
    elif args.input_file:
        with open(args.input_file) as f:
            inputs = json.load(f)

    # Execute
    result = run(project, entrypoint=args.entrypoint, inputs=inputs)

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


def cmd_list(args) -> int:
    """List nodes and edges."""
    from .dag import build_dag

    project = load_project(args.project)
    dag = build_dag(project)

    if args.format == "json":
        output = {
            "nodes": [{"id": n.id, "type": n.type} for n in dag.nodes.values()],
            "edges": [
                {"id": e.id, "from": e.from_node, "to": e.to_node} for e in project.edges.values()
            ],
            "execution_order": dag.execution_order,
        }
        print(json.dumps(output, indent=2))

    elif args.format == "mermaid":
        print("graph LR")
        for node_id, node in dag.nodes.items():
            shape = {"input": "([", "output": "([", "prompt": "[", "tool": "{{"}
            end_shape = {"input": "])", "output": "])", "prompt": "]", "tool": "}}"}
            s, e = shape.get(node.type, "["), end_shape.get(node.type, "]")
            print(f"    {node_id}{s}{node_id}{e}")
        for edge in project.edges.values():
            label = edge.condition or ""
            if label:
                print(f"    {edge.from_node} -->|{label}| {edge.to_node}")
            else:
                print(f"    {edge.from_node} --> {edge.to_node}")

    else:  # text
        print(f"Project: {project.name}")
        print()
        print("Nodes:")
        for node_id, node in dag.nodes.items():
            print(f"  {node.type:8} {node_id}")
        print()
        print("Edges:")
        for edge in project.edges.values():
            cond = f" [{edge.condition}]" if edge.condition else ""
            print(f"  {edge.from_node} -> {edge.to_node}{cond}")
        print()
        print(f"Execution order: {' -> '.join(dag.execution_order)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
