"""Tests for DAG construction and validation."""

import unittest
from pathlib import Path

from trident.dag import DAGError, _get_node_symbol, build_dag, visualize_dag, visualize_dag_mermaid
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

    def test_visualize_dag_mermaid_basic(self):
        """Test Mermaid DAG visualization generates valid syntax."""
        project = self._make_project([("input", "analyze"), ("analyze", "output")], prompts=["analyze"])
        dag = build_dag(project)
        mermaid = visualize_dag_mermaid(dag)

        # Check structure
        self.assertIn("```mermaid", mermaid)
        self.assertIn("flowchart TD", mermaid)
        self.assertIn("```", mermaid)

        # Check nodes with correct shapes
        self.assertIn("input([input])", mermaid)  # Stadium for input
        self.assertIn("analyze[prompt: analyze]", mermaid)  # Rectangle for prompt
        self.assertIn("output([output])", mermaid)  # Stadium for output

        # Check edges
        self.assertIn("input --> analyze", mermaid)
        self.assertIn("analyze --> output", mermaid)

    def test_visualize_dag_mermaid_parallel(self):
        """Test Mermaid visualization shows parallel branches."""
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
        mermaid = visualize_dag_mermaid(dag)

        # Both branches should have edges from input
        self.assertIn("input --> a", mermaid)
        self.assertIn("input --> b", mermaid)

        # Both branches should connect to output
        self.assertIn("a --> output", mermaid)
        self.assertIn("b --> output", mermaid)

    def test_visualize_dag_mermaid_direction(self):
        """Test Mermaid visualization supports different directions."""
        project = self._make_project([("a", "b")], prompts=["b"])
        dag = build_dag(project)

        lr_mermaid = visualize_dag_mermaid(dag, direction="LR")
        self.assertIn("flowchart LR", lr_mermaid)

        td_mermaid = visualize_dag_mermaid(dag, direction="TD")
        self.assertIn("flowchart TD", td_mermaid)


class TestTypesCompatible(unittest.TestCase):
    """Tests for types_compatible() function."""

    def test_exact_match_is_compatible(self):
        """Exact type match is compatible."""
        from trident.dag import types_compatible

        self.assertTrue(types_compatible("string", "string"))
        self.assertTrue(types_compatible("number", "number"))
        self.assertTrue(types_compatible("integer", "integer"))
        self.assertTrue(types_compatible("boolean", "boolean"))
        self.assertTrue(types_compatible("array", "array"))
        self.assertTrue(types_compatible("object", "object"))

    def test_none_source_is_compatible(self):
        """Unknown source type (None) is compatible with any target."""
        from trident.dag import types_compatible

        self.assertTrue(types_compatible(None, "string"))
        self.assertTrue(types_compatible(None, "number"))
        self.assertTrue(types_compatible(None, "object"))

    def test_none_target_is_compatible(self):
        """Any source type is compatible with unknown target (None)."""
        from trident.dag import types_compatible

        self.assertTrue(types_compatible("string", None))
        self.assertTrue(types_compatible("number", None))
        self.assertTrue(types_compatible("object", None))

    def test_both_none_is_compatible(self):
        """Both unknown types are compatible."""
        from trident.dag import types_compatible

        self.assertTrue(types_compatible(None, None))

    def test_integer_number_compatible(self):
        """Integer and number are compatible in both directions."""
        from trident.dag import types_compatible

        self.assertTrue(types_compatible("integer", "number"))
        self.assertTrue(types_compatible("number", "integer"))

    def test_object_to_string_compatible(self):
        """Object can be passed as string (JSON serialization)."""
        from trident.dag import types_compatible

        self.assertTrue(types_compatible("object", "string"))

    def test_array_to_string_compatible(self):
        """Array can be passed as string (JSON serialization)."""
        from trident.dag import types_compatible

        self.assertTrue(types_compatible("array", "string"))

    def test_incompatible_types(self):
        """Truly incompatible types return False."""
        from trident.dag import types_compatible

        self.assertFalse(types_compatible("string", "number"))
        self.assertFalse(types_compatible("string", "boolean"))
        self.assertFalse(types_compatible("boolean", "string"))
        self.assertFalse(types_compatible("string", "object"))
        self.assertFalse(types_compatible("string", "array"))
        self.assertFalse(types_compatible("number", "boolean"))
        self.assertFalse(types_compatible("array", "object"))


class TestGetNodeOutputTypes(unittest.TestCase):
    """Tests for get_node_output_types() function."""

    def _make_project(self) -> Project:
        """Create a minimal project for testing."""
        return Project(name="test", root=Path("."))

    def test_input_node_output_types(self):
        """Input node returns types from schema."""
        from trident.dag import get_node_output_types
        from trident.parser import OutputSchema

        project = self._make_project()
        project.input_nodes["input"] = InputNode(
            id="input",
            schema={
                "query": "string, The search query",
                "limit": "integer, Max results",
                "score": "number, Minimum score",
            },
        )

        types = get_node_output_types(project, "input", "input")

        self.assertEqual(types["query"], "string")
        self.assertEqual(types["limit"], "integer")
        self.assertEqual(types["score"], "number")

    def test_input_node_missing_returns_empty(self):
        """Missing input node returns empty dict."""
        from trident.dag import get_node_output_types

        project = self._make_project()
        types = get_node_output_types(project, "missing", "input")
        self.assertEqual(types, {})

    def test_prompt_text_output_type(self):
        """Text prompt outputs text as string."""
        from trident.dag import get_node_output_types
        from trident.parser import OutputSchema

        project = self._make_project()
        project.prompts["summarize"] = PromptNode(
            id="summarize",
            name="Summarize",
            body="Summarize: {{text}}",
            output=OutputSchema(format="text"),
        )

        types = get_node_output_types(project, "summarize", "prompt")

        self.assertEqual(types, {"text": "string"})

    def test_prompt_json_output_types(self):
        """JSON prompt outputs text plus schema field types."""
        from trident.dag import get_node_output_types
        from trident.parser import OutputSchema

        project = self._make_project()
        project.prompts["analyze"] = PromptNode(
            id="analyze",
            name="Analyze",
            body="Analyze: {{code}}",
            output=OutputSchema(
                format="json",
                fields={
                    "status": ("string", "Status code"),
                    "count": ("integer", "Item count"),
                    "score": ("number", "Relevance score"),
                    "valid": ("boolean", "Is valid"),
                },
            ),
        )

        types = get_node_output_types(project, "analyze", "prompt")

        self.assertEqual(types["text"], "string")
        self.assertEqual(types["status"], "string")
        self.assertEqual(types["count"], "integer")
        self.assertEqual(types["score"], "number")
        self.assertEqual(types["valid"], "boolean")

    def test_prompt_missing_returns_default(self):
        """Missing prompt returns default text output."""
        from trident.dag import get_node_output_types

        project = self._make_project()
        types = get_node_output_types(project, "missing", "prompt")
        self.assertEqual(types, {"text": "string"})

    def test_tool_output_type_unknown(self):
        """Tool output type is unknown (None)."""
        from trident.dag import get_node_output_types

        project = self._make_project()
        types = get_node_output_types(project, "my_tool", "tool")
        self.assertEqual(types, {"output": None})

    def test_agent_output_types(self):
        """Agent outputs text as string."""
        from trident.dag import get_node_output_types

        project = self._make_project()
        types = get_node_output_types(project, "agent1", "agent")
        self.assertEqual(types, {"text": "string"})

    def test_branch_output_types(self):
        """Branch outputs text and generic output."""
        from trident.dag import get_node_output_types

        project = self._make_project()
        types = get_node_output_types(project, "branch1", "branch")
        self.assertEqual(types, {"output": None, "text": "string"})


class TestGetNodeInputTypes(unittest.TestCase):
    """Tests for get_node_input_types() function."""

    def _make_project(self) -> Project:
        """Create a minimal project for testing."""
        return Project(name="test", root=Path("."))

    def test_prompt_input_types(self):
        """Prompt returns types from input definitions."""
        from trident.dag import get_node_input_types
        from trident.parser import InputField, OutputSchema

        project = self._make_project()
        project.prompts["analyze"] = PromptNode(
            id="analyze",
            name="Analyze",
            body="Analyze: {{code}} with {{count}}",
            inputs={
                "code": InputField(name="code", type="string"),
                "count": InputField(name="count", type="integer"),
            },
            output=OutputSchema(format="text"),
        )

        types = get_node_input_types(project, "analyze", "prompt")

        self.assertEqual(types["code"], "string")
        self.assertEqual(types["count"], "integer")

    def test_prompt_missing_returns_empty(self):
        """Missing prompt returns empty dict."""
        from trident.dag import get_node_input_types

        project = self._make_project()
        types = get_node_input_types(project, "missing", "prompt")
        self.assertEqual(types, {})

    def test_output_node_accepts_any(self):
        """Output node accepts any types."""
        from trident.dag import get_node_input_types

        project = self._make_project()
        types = get_node_input_types(project, "output", "output")
        self.assertEqual(types, {})

    def test_input_node_accepts_any(self):
        """Input node has no inputs."""
        from trident.dag import get_node_input_types

        project = self._make_project()
        types = get_node_input_types(project, "input", "input")
        self.assertEqual(types, {})


class TestTypeValidationIntegration(unittest.TestCase):
    """Integration tests for type validation in edge mappings."""

    def _make_project_with_edge(
        self,
        source_type: str = "string",
        target_type: str = "string",
    ) -> Project:
        """Create a project with one edge for type testing."""
        from trident.parser import InputField, OutputSchema

        project = Project(name="test", root=Path("."))

        # Input with typed field
        project.input_nodes["input"] = InputNode(
            id="input",
            schema={"value": f"{source_type}, Test value"},
        )

        # Prompt expecting typed input
        project.prompts["process"] = PromptNode(
            id="process",
            name="Process",
            body="Process: {{data}}",
            inputs={
                "data": InputField(name="data", type=target_type),
            },
            output=OutputSchema(format="text"),
        )

        # Output node
        project.output_nodes["output"] = OutputNode(id="output")

        # Edge connecting them
        from trident.project import EdgeMapping

        project.edges["e1"] = Edge(
            id="e1",
            from_node="input",
            to_node="process",
            mappings=[EdgeMapping(source_expr="value", target_var="data")],
        )
        project.edges["e2"] = Edge(
            id="e2",
            from_node="process",
            to_node="output",
        )

        project.entrypoints = ["input"]
        return project

    def test_compatible_types_no_warning(self):
        """Compatible types produce no warnings."""
        from trident.dag import validate_edge_mappings

        project = self._make_project_with_edge(
            source_type="string",
            target_type="string",
        )
        dag = build_dag(project)

        result = validate_edge_mappings(project, dag)

        self.assertTrue(result.valid)
        # No type mismatch warnings
        type_warnings = [w for w in result.warnings if "Type mismatch" in w.message]
        self.assertEqual(len(type_warnings), 0)

    def test_integer_to_number_no_warning(self):
        """Integer to number is compatible, no warning."""
        from trident.dag import validate_edge_mappings

        project = self._make_project_with_edge(
            source_type="integer",
            target_type="number",
        )
        dag = build_dag(project)

        result = validate_edge_mappings(project, dag)

        type_warnings = [w for w in result.warnings if "Type mismatch" in w.message]
        self.assertEqual(len(type_warnings), 0)

    def test_incompatible_types_produces_warning(self):
        """Incompatible types produce a warning."""
        from trident.dag import validate_edge_mappings

        project = self._make_project_with_edge(
            source_type="string",
            target_type="number",
        )
        dag = build_dag(project)

        result = validate_edge_mappings(project, dag)

        # Should have a type mismatch warning
        type_warnings = [w for w in result.warnings if "Type mismatch" in w.message]
        self.assertEqual(len(type_warnings), 1)
        self.assertIn("string", type_warnings[0].message)
        self.assertIn("number", type_warnings[0].message)

    def test_strict_mode_turns_warnings_to_errors(self):
        """Strict mode makes type warnings into errors."""
        from trident.dag import validate_edge_mappings

        project = self._make_project_with_edge(
            source_type="string",
            target_type="boolean",
        )
        dag = build_dag(project)

        result = validate_edge_mappings(project, dag, strict=True)

        self.assertFalse(result.valid)
        self.assertTrue(len(result.errors) > 0)
        self.assertIn("Type mismatch", result.errors[0])

    def test_object_to_string_compatible(self):
        """Object output to string input is compatible."""
        from trident.dag import validate_edge_mappings

        project = self._make_project_with_edge(
            source_type="object",
            target_type="string",
        )
        dag = build_dag(project)

        result = validate_edge_mappings(project, dag)

        type_warnings = [w for w in result.warnings if "Type mismatch" in w.message]
        self.assertEqual(len(type_warnings), 0)


if __name__ == "__main__":
    unittest.main()
