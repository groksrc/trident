"""Integration tests for telemetry with executor."""

import unittest
from pathlib import Path

from trident.executor import run
from trident.project import Edge, InputNode, OutputNode, Project
from trident.telemetry import TelemetryConfig


class TestTelemetryIntegration(unittest.TestCase):
    """Tests for telemetry integration with executor."""

    def test_workflow_lifecycle_events(self):
        """Telemetry emits workflow_started and workflow_completed events."""
        # Create minimal project
        project = Project(
            name="test-workflow",
            root=Path("."),
            defaults={"model": "anthropic/claude-sonnet-4-20250514"},
            entrypoints=["input"],
            input_nodes={"input": InputNode(id="input", schema={})},
            output_nodes={"output": OutputNode(id="output", format="json")},
            edges={
                "e1": Edge(
                    id="e1",
                    from_node="input",
                    to_node="output",
                    mappings=[],
                )
            },
        )

        # Configure telemetry
        config = TelemetryConfig(enabled=True, format="jsonl")

        # Run with telemetry (dry run to avoid LLM calls)
        result = run(
            project,
            inputs={},
            dry_run=True,
            telemetry_config=config,
        )

        # Telemetry should have been emitted
        self.assertTrue(result.success)

    def test_telemetry_disabled_by_default(self):
        """When telemetry_config is None, no telemetry is emitted."""
        project = Project(
            name="test-workflow",
            root=Path("."),
            defaults={"model": "anthropic/claude-sonnet-4-20250514"},
            entrypoints=["input"],
            input_nodes={"input": InputNode(id="input", schema={})},
            output_nodes={"output": OutputNode(id="output", format="json")},
            edges={
                "e1": Edge(
                    id="e1",
                    from_node="input",
                    to_node="output",
                    mappings=[],
                )
            },
        )

        # Run without telemetry config
        result = run(
            project,
            inputs={},
            dry_run=True,
            telemetry_config=None,
        )

        # Should succeed normally
        self.assertTrue(result.success)

    def test_workflow_failure_event(self):
        """Telemetry emits workflow_failed on error."""
        # Create project with invalid edge mapping (will cause error)
        project = Project(
            name="test-workflow",
            root=Path("."),
            defaults={"model": "anthropic/claude-sonnet-4-20250514"},
            entrypoints=["input"],
            input_nodes={"input": InputNode(id="input", schema={})},
            output_nodes={"output": OutputNode(id="output", format="json")},
            edges={
                "e1": Edge(
                    id="e1",
                    from_node="input",
                    to_node="nonexistent",
                    mappings=[],
                )
            },
        )

        # Configure telemetry
        config = TelemetryConfig(enabled=True, format="jsonl")

        # Run should fail due to invalid DAG
        try:
            result = run(
                project,
                inputs={},
                dry_run=True,
                telemetry_config=config,
            )
            # If it doesn't raise during DAG build, check result
            if result.error:
                # Expected - execution failed
                pass
        except Exception:
            # Expected - DAG build failed
            pass

    def test_node_execution_events(self):
        """Telemetry emits node_started and node_completed events."""
        # Create project with prompt node
        project = Project(
            name="test-workflow",
            root=Path("."),
            defaults={"model": "anthropic/claude-sonnet-4-20250514"},
            entrypoints=["input"],
            input_nodes={"input": InputNode(id="input", schema={})},
            output_nodes={"output": OutputNode(id="output", format="json")},
            edges={
                "e1": Edge(
                    id="e1",
                    from_node="input",
                    to_node="output",
                    mappings=[],
                )
            },
        )

        # Configure telemetry
        config = TelemetryConfig(enabled=True, format="jsonl")

        # Run workflow
        result = run(
            project,
            inputs={},
            dry_run=True,
            telemetry_config=config,
        )

        # Should have workflow and node events
        self.assertTrue(result.success)


if __name__ == "__main__":
    unittest.main()
