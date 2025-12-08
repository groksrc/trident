"""Tests for DAG construction and validation."""

import unittest
from trident.project import Project, Edge, EdgeMapping, InputNode, OutputNode
from trident.parser import PromptNode
from trident.dag import build_dag, DAGError
from pathlib import Path


class TestDAG(unittest.TestCase):
    def _make_project(self, edges: list[tuple[str, str]], prompts: list[str] = None) -> Project:
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
        project = self._make_project([
            ("input", "a"),
            ("input", "b"),
            ("a", "output"),
            ("b", "output"),
        ], prompts=["a", "b"])
        dag = build_dag(project)

        # input should come first, output last
        self.assertEqual(dag.execution_order[0], "input")
        self.assertEqual(dag.execution_order[-1], "output")

    def test_cycle_detection(self):
        project = self._make_project([
            ("a", "b"),
            ("b", "c"),
            ("c", "a"),
        ], prompts=["a", "b", "c"])

        with self.assertRaises(DAGError) as ctx:
            build_dag(project)
        self.assertIn("Cycle", str(ctx.exception))

    def test_self_loop_detection(self):
        project = self._make_project([("a", "a")], prompts=["a"])

        with self.assertRaises(DAGError):
            build_dag(project)


if __name__ == "__main__":
    unittest.main()
