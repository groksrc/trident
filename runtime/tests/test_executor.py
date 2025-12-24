"""Tests for DAG execution and error handling."""

import unittest
from pathlib import Path

from trident.errors import NodeExecutionError
from trident.executor import ExecutionResult, ExecutionTrace, NodeTrace, run
from trident.project import Edge, InputNode, OutputNode, Project


class TestExecutionResult(unittest.TestCase):
    """Tests for ExecutionResult structure."""

    def test_success_property(self):
        """ExecutionResult.success reflects actual success state."""
        trace = ExecutionTrace(execution_id="test", start_time="2024-01-01T00:00:00Z")

        # Success case
        result = ExecutionResult(outputs={}, trace=trace, error=None)
        self.assertTrue(result.success)

        # Failure case
        error = NodeExecutionError(node_id="test_node", node_type="prompt", message="Test error")
        result_with_error = ExecutionResult(outputs={}, trace=trace, error=error)
        self.assertFalse(result_with_error.success)

    def test_summary_on_success(self):
        """ExecutionResult.summary() provides readable output on success."""
        trace = ExecutionTrace(execution_id="test", start_time="2024-01-01T00:00:00Z")
        trace.nodes = [
            NodeTrace(
                id="node1", start_time="2024-01-01T00:00:00Z", end_time="2024-01-01T00:00:01Z"
            ),
            NodeTrace(
                id="node2", start_time="2024-01-01T00:00:01Z", end_time="2024-01-01T00:00:02Z"
            ),
        ]

        result = ExecutionResult(outputs={"test": "value"}, trace=trace)
        summary = result.summary()

        self.assertIn("succeeded", summary)
        self.assertIn("2 succeeded", summary)
        self.assertIn("0 failed", summary)

    def test_summary_on_failure(self):
        """ExecutionResult.summary() shows error details on failure."""
        trace = ExecutionTrace(execution_id="test", start_time="2024-01-01T00:00:00Z")
        trace.nodes = [
            NodeTrace(
                id="node1", start_time="2024-01-01T00:00:00Z", end_time="2024-01-01T00:00:01Z"
            ),
            NodeTrace(
                id="node2",
                start_time="2024-01-01T00:00:01Z",
                error="Something broke",
                error_type="ValueError",
            ),
        ]

        error = NodeExecutionError(node_id="node2", node_type="prompt", message="Something broke")
        result = ExecutionResult(outputs={}, trace=trace, error=error)
        summary = result.summary()

        self.assertIn("FAILED", summary)
        self.assertIn("node2", summary)
        self.assertIn("Something broke", summary)


class TestNodeTrace(unittest.TestCase):
    """Tests for NodeTrace structure."""

    def test_succeeded_property(self):
        """NodeTrace.succeeded reflects actual node state."""
        # Success
        node = NodeTrace(id="test", start_time="2024-01-01T00:00:00Z")
        self.assertTrue(node.succeeded)

        # Skipped
        skipped = NodeTrace(id="test", start_time="2024-01-01T00:00:00Z", skipped=True)
        self.assertFalse(skipped.succeeded)

        # Error
        errored = NodeTrace(id="test", start_time="2024-01-01T00:00:00Z", error="Failed")
        self.assertFalse(errored.succeeded)


class TestExecutionTrace(unittest.TestCase):
    """Tests for ExecutionTrace structure."""

    def test_failed_node_property(self):
        """ExecutionTrace.failed_node returns first failed node."""
        trace = ExecutionTrace(execution_id="test", start_time="2024-01-01T00:00:00Z")
        trace.nodes = [
            NodeTrace(id="node1", start_time="2024-01-01T00:00:00Z"),
            NodeTrace(id="node2", start_time="2024-01-01T00:00:01Z", error="First error"),
            NodeTrace(id="node3", start_time="2024-01-01T00:00:02Z", error="Second error"),
        ]

        failed = trace.failed_node
        self.assertIsNotNone(failed)
        self.assertEqual(failed.id, "node2")
        self.assertEqual(failed.error, "First error")

    def test_failed_node_none_on_success(self):
        """ExecutionTrace.failed_node returns None when all succeed."""
        trace = ExecutionTrace(execution_id="test", start_time="2024-01-01T00:00:00Z")
        trace.nodes = [
            NodeTrace(id="node1", start_time="2024-01-01T00:00:00Z"),
            NodeTrace(id="node2", start_time="2024-01-01T00:00:01Z"),
        ]

        self.assertIsNone(trace.failed_node)


class TestNodeExecutionError(unittest.TestCase):
    """Tests for NodeExecutionError structure."""

    def test_error_includes_node_context(self):
        """NodeExecutionError includes node_id and node_type."""
        error = NodeExecutionError(
            node_id="analyze_code", node_type="prompt", message="Model returned invalid JSON"
        )

        self.assertEqual(error.node_id, "analyze_code")
        self.assertEqual(error.node_type, "prompt")
        self.assertIn("analyze_code", str(error))
        self.assertIn("prompt", str(error))

    def test_error_includes_cause(self):
        """NodeExecutionError preserves and displays cause."""
        cause = ValueError("Invalid model name")
        error = NodeExecutionError(
            node_id="test_node", node_type="prompt", message="Provider error", cause=cause
        )

        self.assertEqual(error.cause, cause)
        self.assertEqual(error.cause_type, "ValueError")
        self.assertIn("ValueError", str(error))

    def test_error_includes_inputs(self):
        """NodeExecutionError shows input context."""
        error = NodeExecutionError(
            node_id="test_node",
            node_type="prompt",
            message="Template error",
            inputs={"code": "def foo(): pass", "lang": "python"},
        )

        error_str = str(error)
        self.assertIn("Inputs:", error_str)

    def test_error_inherits_exit_code(self):
        """NodeExecutionError inherits exit code from TridentError causes."""
        from trident.errors import ExitCode, ProviderError

        cause = ProviderError("Rate limited", retryable=True)
        error = NodeExecutionError(
            node_id="test", node_type="prompt", message="API error", cause=cause
        )

        self.assertEqual(error.exit_code, ExitCode.PROVIDER_ERROR)


class TestDryRunExecution(unittest.TestCase):
    """Tests for dry-run execution mode."""

    def _make_simple_project(self) -> Project:
        """Create a minimal project for testing."""
        project = Project(name="test", root=Path("."))
        project.input_nodes["input"] = InputNode(id="input")
        project.output_nodes["output"] = OutputNode(id="output")
        project.edges["e1"] = Edge(id="e1", from_node="input", to_node="output")
        project.entrypoints = ["input"]
        return project

    def test_dry_run_returns_result(self):
        """Dry run always returns ExecutionResult."""
        project = self._make_simple_project()
        result = run(project, dry_run=True, inputs={"message": "hello"})

        self.assertIsInstance(result, ExecutionResult)
        self.assertTrue(result.success)
        self.assertIsNone(result.error)


if __name__ == "__main__":
    unittest.main()
