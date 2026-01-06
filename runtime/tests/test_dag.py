"""Tests for DAG construction and validation."""

import unittest
from pathlib import Path

from trident.dag import DAGError, _get_node_symbol, build_dag, visualize_dag
from trident.parser import BranchNode, PromptNode
from trident.project import Edge, InputNode, OutputNode, Project


class TestDAG(unittest.TestCase):
    def _make_project(
        self, edges: list[tuple[str, str]], prompts: list[str] | None = None
    ) -> Project:
        """Create a minimal project with given edges."""
        project = Project(name="test", root=Path("."))

        # Add edges
        for i, (from_node, to_node) in enumerate(edges):
            project.edges[f"e{i}"] = Edge(
                id=f"e{i}",
                from_node=from_node,
                to_node=to_node,
            )

        # Add prompts (if specified)
        if prompts:
            for p in prompts:
                project.prompts[p] = PromptNode(id=p)

        # Add implicit input/output nodes based on edges
        all_from = {e[0] for e in edges}
        all_to = {e[1] for e in edges}

        for node_id in all_from:
            if node_id not in (prompts or []):
                project.input_nodes[node_id] = InputNode(id=node_id)

        for node_id in all_to:
            if node_id not in (prompts or []) and node_id not in project.input_nodes:
                project.output_nodes[node_id] = OutputNode(id=node_id)

        return project

    def test_simple_dag(self):
        project = self._make_project([("a", "b"), ("b", "c")], prompts=["b"])
        dag = build_dag(project)

        self.assertIn("a", dag.nodes)
        self.assertIn("b", dag.nodes)
        self.assertIn("c", dag.nodes)
        self.assertEqual(dag.execution_order, ["a", "b", "c"])

    def test_branching_dag(self):
        project = self._make_project(
            [
                ("input", "a"),
                ("input", "b"),
                ("a", "output"),
                ("b", "output"),
            ],
            prompts=["a", "b"],
        )
        dag = build_dag(project)

        # input should come first, output last
        self.assertEqual(dag.execution_order[0], "input")
        self.assertEqual(dag.execution_order[-1], "output")

    def test_execution_levels_parallel(self):
        """Test that nodes that can run in parallel are grouped together."""
        # Diamond pattern: input -> [a, b] -> output
        project = self._make_project(
            [
                ("input", "a"),
                ("input", "b"),
                ("a", "output"),
                ("b", "output"),
            ],
            prompts=["a", "b"],
        )
        dag = build_dag(project)

        # Should have 3 levels: [input], [a, b], [output]
        self.assertEqual(len(dag.execution_levels), 3)
        self.assertEqual(dag.execution_levels[0], ["input"])
        self.assertEqual(sorted(dag.execution_levels[1]), ["a", "b"])  # a and b in parallel
        self.assertEqual(dag.execution_levels[2], ["output"])

    def test_execution_levels_sequential(self):
        """Test that dependent nodes are in separate levels."""
        # Linear: a -> b -> c
        project = self._make_project([("a", "b"), ("b", "c")], prompts=["b"])
        dag = build_dag(project)

        # Should have 3 levels, each with 1 node
        self.assertEqual(len(dag.execution_levels), 3)
        self.assertEqual(dag.execution_levels[0], ["a"])
        self.assertEqual(dag.execution_levels[1], ["b"])
        self.assertEqual(dag.execution_levels[2], ["c"])

    def test_cycle_detection(self):
        project = self._make_project(
            [
                ("a", "b"),
                ("b", "c"),
                ("c", "a"),
            ],
            prompts=["a", "b", "c"],
        )

        with self.assertRaises(DAGError) as ctx:
            build_dag(project)
        self.assertIn("Cycle", str(ctx.exception))

    def test_self_loop_detection(self):
        project = self._make_project([("a", "a")], prompts=["a"])

        with self.assertRaises(DAGError):
            build_dag(project)

    def test_branch_node_in_dag(self):
        """Test that branch nodes are properly included in the DAG."""
        project = self._make_project(
            [("input", "branch1"), ("branch1", "output")],
            prompts=[],
        )
        # Add branch node
        project.branches["branch1"] = BranchNode(
            id="branch1",
            workflow_path="./sub_workflow.yaml",
        )
        # Remove from input/output nodes since it's a branch
        project.input_nodes.pop("branch1", None)
        project.output_nodes.pop("branch1", None)

        dag = build_dag(project)

        self.assertIn("branch1", dag.nodes)
        self.assertEqual(dag.nodes["branch1"].type, "branch")
        self.assertEqual(dag.execution_order, ["input", "branch1", "output"])

    def test_branch_node_symbol(self):
        """Test that branch nodes get the [B] symbol."""
        self.assertEqual(_get_node_symbol("branch"), "[B]")
        self.assertEqual(_get_node_symbol("input"), "[I]")
        self.assertEqual(_get_node_symbol("output"), "[O]")
        self.assertEqual(_get_node_symbol("prompt"), "[P]")
        self.assertEqual(_get_node_symbol("agent"), "[A]")
        self.assertEqual(_get_node_symbol("tool"), "[T]")
        self.assertEqual(_get_node_symbol("unknown"), "[?]")

    def test_visualize_dag_with_branch(self):
        """Test DAG visualization includes branch nodes."""
        project = self._make_project(
            [("input", "branch1"), ("branch1", "output")],
            prompts=[],
        )
        project.branches["branch1"] = BranchNode(
            id="branch1",
            workflow_path="./sub_workflow.yaml",
        )
        project.input_nodes.pop("branch1", None)
        project.output_nodes.pop("branch1", None)

        dag = build_dag(project)
        viz = visualize_dag(dag)

        self.assertIn("[B] branch1", viz)
        self.assertIn("[I] Input", viz)  # Legend
        self.assertIn("[B] Branch", viz)  # Legend


if __name__ == "__main__":
    unittest.main()
