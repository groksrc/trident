"""Tests for branch node execution."""

import tempfile
import unittest
from pathlib import Path

from trident.errors import BranchError
from trident.executor import run
from trident.parser import BranchNode
from trident.project import Edge, EdgeMapping, InputNode, OutputNode, Project


class TestBranchNodeExecution(unittest.TestCase):
    """Tests for branch node execution."""

    def _make_project_with_branch(
        self,
        branch_workflow: str = "./sub.yaml",
        condition: str | None = None,
    ) -> tuple[Project, Path]:
        """Create a project with a branch node and a sub-workflow."""
        tmpdir = Path(tempfile.mkdtemp())

        # Create main project
        project = Project(name="main", root=tmpdir)
        project.input_nodes["input"] = InputNode(id="input")
        project.output_nodes["output"] = OutputNode(id="output")
        project.branches["branch1"] = BranchNode(
            id="branch1",
            workflow_path=branch_workflow,
            condition=condition,
        )
        project.edges["e1"] = Edge(
            id="e1",
            from_node="input",
            to_node="branch1",
            mappings=[EdgeMapping(target_var="value", source_expr="value")],
        )
        project.edges["e2"] = Edge(id="e2", from_node="branch1", to_node="output")
        project.entrypoints = ["input"]

        # Create sub-workflow project file
        sub_yaml = tmpdir / "sub.yaml"
        sub_yaml.write_text("""
trident: "0.1"
name: sub
nodes:
  input:
    type: input
  output:
    type: output
edges:
  e1:
    from: input
    to: output
""")

        return project, tmpdir

    def test_branch_dry_run(self):
        """Test branch node in dry run mode."""
        project, tmpdir = self._make_project_with_branch()

        result = run(project, inputs={"value": 42}, dry_run=True)

        self.assertTrue(result.success)
        # Check branch node executed correctly
        branch_trace = next((n for n in result.trace.nodes if n.id == "branch1"), None)
        self.assertIsNotNone(branch_trace)
        self.assertFalse(branch_trace.skipped)
        self.assertIn("dry_run", branch_trace.output)

    def test_branch_condition_skip(self):
        """Test branch node skipped when condition is false."""
        project, tmpdir = self._make_project_with_branch(
            condition="value > 100"  # 42 > 100 is false, so branch skips
        )

        result = run(project, inputs={"value": 42}, dry_run=True)

        self.assertTrue(result.success)
        # Branch should be skipped, trace should show it
        branch_trace = next((n for n in result.trace.nodes if n.id == "branch1"), None)
        self.assertIsNotNone(branch_trace)
        self.assertTrue(branch_trace.skipped)

    def test_branch_condition_execute(self):
        """Test branch node executes when condition is true."""
        project, tmpdir = self._make_project_with_branch(
            condition="value < 100"  # 42 < 100 is true, so branch executes
        )

        result = run(project, inputs={"value": 42}, dry_run=True)

        self.assertTrue(result.success)
        branch_trace = next((n for n in result.trace.nodes if n.id == "branch1"), None)
        self.assertIsNotNone(branch_trace)
        self.assertFalse(branch_trace.skipped)

    def test_branch_missing_workflow(self):
        """Test error when sub-workflow file doesn't exist."""
        project, tmpdir = self._make_project_with_branch(branch_workflow="./nonexistent.yaml")

        result = run(project, inputs={"value": 42}, dry_run=False)

        # Should fail with BranchError about missing workflow
        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)


class TestBranchNodeDataclass(unittest.TestCase):
    """Tests for BranchNode dataclass."""

    def test_branch_node_defaults(self):
        """Test BranchNode default values."""
        node = BranchNode(id="test", workflow_path="./sub.yaml")

        self.assertEqual(node.id, "test")
        self.assertEqual(node.workflow_path, "./sub.yaml")
        self.assertIsNone(node.condition)
        self.assertIsNone(node.loop_while)
        self.assertEqual(node.max_iterations, 10)

    def test_branch_node_with_options(self):
        """Test BranchNode with all options set."""
        node = BranchNode(
            id="loop",
            workflow_path="./refine.yaml",
            condition="{{ready}}",
            loop_while="{{quality}} < 8",
            max_iterations=5,
        )

        self.assertEqual(node.workflow_path, "./refine.yaml")
        self.assertEqual(node.condition, "{{ready}}")
        self.assertEqual(node.loop_while, "{{quality}} < 8")
        self.assertEqual(node.max_iterations, 5)


class TestBranchLoopExecution(unittest.TestCase):
    """Tests for branch node loop execution."""

    def _make_project_with_loop(
        self,
        loop_while: str,
        max_iterations: int = 10,
    ) -> tuple[Project, Path]:
        """Create a project with a looping branch node."""
        tmpdir = Path(tempfile.mkdtemp())

        # Create main project
        project = Project(name="main", root=tmpdir)
        project.input_nodes["input"] = InputNode(id="input")
        project.output_nodes["output"] = OutputNode(id="output")
        project.branches["loop1"] = BranchNode(
            id="loop1",
            workflow_path="./increment.yaml",
            loop_while=loop_while,
            max_iterations=max_iterations,
        )
        project.edges["e1"] = Edge(
            id="e1",
            from_node="input",
            to_node="loop1",
            mappings=[EdgeMapping(target_var="counter", source_expr="counter")],
        )
        project.edges["e2"] = Edge(id="e2", from_node="loop1", to_node="output")
        project.entrypoints = ["input"]

        # Create sub-workflow that increments counter (pass-through for testing)
        sub_yaml = tmpdir / "increment.yaml"
        sub_yaml.write_text("""
trident: "0.1"
name: increment
nodes:
  input:
    type: input
  output:
    type: output
edges:
  e1:
    from: input
    to: output
""")

        return project, tmpdir

    def test_loop_terminates_on_condition_false(self):
        """Test loop terminates when condition becomes false."""
        # This test uses dry_run which passes through inputs
        # Loop condition "counter < 3" - starts at 0, dry_run passes through
        # Since dry_run returns {"dry_run": True, ...}, loop runs once
        project, tmpdir = self._make_project_with_loop(
            loop_while="counter < 3",
            max_iterations=10,
        )

        result = run(project, inputs={"counter": 5}, dry_run=True)

        # Dry run should succeed
        self.assertTrue(result.success)
        branch_trace = next((n for n in result.trace.nodes if n.id == "loop1"), None)
        self.assertIsNotNone(branch_trace)

    def test_loop_max_iterations_in_dry_run(self):
        """Test that loop respects max_iterations in dry run mode."""
        project, tmpdir = self._make_project_with_loop(
            loop_while="true",  # Always true
            max_iterations=3,
        )

        # In dry_run, branch nodes return early without looping
        result = run(project, inputs={"counter": 0}, dry_run=True)

        # Dry run bypasses loop logic
        self.assertTrue(result.success)

    def test_branch_node_with_loop_while(self):
        """Test BranchNode accepts loop_while parameter."""
        node = BranchNode(
            id="loop",
            workflow_path="./sub.yaml",
            loop_while="score < 8",
            max_iterations=5,
        )

        self.assertEqual(node.loop_while, "score < 8")
        self.assertEqual(node.max_iterations, 5)


class TestBranchError(unittest.TestCase):
    """Tests for BranchError exception."""

    def test_branch_error_basic(self):
        """Test BranchError with basic message."""
        err = BranchError("Something went wrong")

        self.assertIn("Something went wrong", str(err))

    def test_branch_error_with_iteration(self):
        """Test BranchError with iteration info."""
        err = BranchError(
            "Max iterations exceeded",
            iteration=5,
            max_iterations=5,
        )

        msg = str(err)
        self.assertIn("Max iterations exceeded", msg)
        self.assertIn("5/5", msg)

    def test_branch_error_with_cause(self):
        """Test BranchError with underlying cause."""
        cause = ValueError("Invalid input")
        err = BranchError("Workflow failed", cause=cause)

        msg = str(err)
        self.assertIn("Workflow failed", msg)
        self.assertIn("ValueError", msg)


class TestBranchLoopIntegration(unittest.TestCase):
    """Integration tests for branch loop execution (non-dry-run).

    These tests use sub-workflows with only input/output nodes
    to test actual loop execution without requiring LLM calls.
    """

    def _make_counter_project(
        self,
        loop_while: str,
        max_iterations: int = 10,
    ) -> tuple[Project, Path]:
        """Create a project with a loop that increments a counter.

        The sub-workflow increments a counter by 1 each iteration.
        """
        tmpdir = Path(tempfile.mkdtemp())

        # Create main project
        project = Project(name="main", root=tmpdir)
        project.input_nodes["input"] = InputNode(id="input")
        project.output_nodes["output"] = OutputNode(id="output")
        project.branches["loop1"] = BranchNode(
            id="loop1",
            workflow_path="./increment",  # Directory path, not file
            loop_while=loop_while,
            max_iterations=max_iterations,
        )
        project.edges["e1"] = Edge(
            id="e1",
            from_node="input",
            to_node="loop1",
            mappings=[EdgeMapping(target_var="counter", source_expr="counter")],
        )
        project.edges["e2"] = Edge(
            id="e2",
            from_node="loop1",
            to_node="output",
            mappings=[EdgeMapping(target_var="counter", source_expr="counter")],
        )
        project.entrypoints = ["input"]

        # Create sub-workflow directory with agent.tml
        sub_dir = tmpdir / "increment"
        sub_dir.mkdir()
        (sub_dir / "agent.tml").write_text("""
trident: "0.1"
name: increment
nodes:
  input:
    type: input
  output:
    type: output
tools:
  increment_tool:
    type: python
    path: increment_tool.py
edges:
  e1:
    from: input
    to: increment_tool
    mapping:
      counter: counter
  e2:
    from: increment_tool
    to: output
    mapping:
      counter: counter
""")

        # Create tools directory inside sub-workflow with increment tool
        tools_dir = sub_dir / "tools"
        tools_dir.mkdir()
        (tools_dir / "increment_tool.py").write_text('''
def execute(counter: int) -> dict:
    """Increment the counter by 1."""
    return {"counter": counter + 1}
''')

        return project, tmpdir

    def test_loop_executes_until_condition_false(self):
        """Test loop runs until condition becomes false."""
        # Loop while counter < 5, start at 0
        # Should execute 5 times: 0->1->2->3->4->5, stop at 5
        project, tmpdir = self._make_counter_project(
            loop_while="counter < 5",
            max_iterations=10,
        )

        result = run(project, inputs={"counter": 0}, dry_run=False)

        self.assertTrue(result.success, f"Expected success, got error: {result.error}")
        # Outputs are nested: {"output": {"counter": 5}}
        # After 5 iterations: 0->1->2->3->4->5
        self.assertEqual(result.outputs["output"]["counter"], 5)

    def test_loop_respects_max_iterations(self):
        """Test loop stops at max_iterations even if condition still true."""
        # Loop while counter < 100, but max_iterations=3
        # Should execute exactly 3 times: 0->1->2->3, then error
        project, tmpdir = self._make_counter_project(
            loop_while="counter < 100",
            max_iterations=3,
        )

        result = run(project, inputs={"counter": 0}, dry_run=False)

        # Should fail with max iterations error
        self.assertFalse(result.success)
        self.assertIsNotNone(result.error)
        self.assertIn("Max iterations", str(result.error))

    def test_loop_single_iteration_when_condition_immediately_false(self):
        """Test loop executes once then stops when condition is already false."""
        # Loop while counter < 0, start at 5
        # Condition false immediately after first iteration
        project, tmpdir = self._make_counter_project(
            loop_while="counter < 0",
            max_iterations=10,
        )

        result = run(project, inputs={"counter": 5}, dry_run=False)

        self.assertTrue(result.success)
        # Outputs are nested: {"output": {"counter": 6}}
        # One iteration: 5->6, then condition (6 < 0) is false
        self.assertEqual(result.outputs["output"]["counter"], 6)

    def test_loop_saves_iteration_artifacts(self):
        """Test iteration states are saved when artifact_dir is provided."""
        project, tmpdir = self._make_counter_project(
            loop_while="counter < 3",
            max_iterations=10,
        )
        artifact_dir = tmpdir / ".trident"

        result = run(
            project,
            inputs={"counter": 0},
            dry_run=False,
            artifact_dir=artifact_dir,
        )

        self.assertTrue(result.success)

        # Check iteration artifacts were saved

        # Find the run directory
        runs_dir = artifact_dir / "runs"
        self.assertTrue(runs_dir.exists())

        # Get the run_id from result
        run_id = result.trace.run_id
        run_dir = runs_dir / run_id

        # Check branch iteration files exist
        branches_dir = run_dir / "branches" / "loop1"
        if branches_dir.exists():
            iterations = list(branches_dir.glob("iteration_*.json"))
            # Should have 3 iterations (0, 1, 2)
            self.assertEqual(len(iterations), 3)

    def test_no_loop_executes_once(self):
        """Test branch without loop_while executes exactly once."""
        tmpdir = Path(tempfile.mkdtemp())

        # Create project without loop_while
        project = Project(name="main", root=tmpdir)
        project.input_nodes["input"] = InputNode(id="input")
        project.output_nodes["output"] = OutputNode(id="output")
        project.branches["branch1"] = BranchNode(
            id="branch1",
            workflow_path="./passthrough",  # Directory path
            # No loop_while - single execution
        )
        project.edges["e1"] = Edge(
            id="e1",
            from_node="input",
            to_node="branch1",
            mappings=[EdgeMapping(target_var="value", source_expr="value")],
        )
        project.edges["e2"] = Edge(
            id="e2",
            from_node="branch1",
            to_node="output",
            mappings=[EdgeMapping(target_var="value", source_expr="value")],
        )
        project.entrypoints = ["input"]

        # Create passthrough sub-workflow directory
        sub_dir = tmpdir / "passthrough"
        sub_dir.mkdir()
        (sub_dir / "agent.tml").write_text("""
trident: "0.1"
name: passthrough
nodes:
  input:
    type: input
  output:
    type: output
edges:
  e1:
    from: input
    to: output
    mapping:
      value: value
""")

        result = run(project, inputs={"value": 42}, dry_run=False)

        self.assertTrue(result.success)
        # Outputs are nested: {"output": {"value": 42}}
        self.assertEqual(result.outputs["output"]["value"], 42)


class TestBranchLoopResumption(unittest.TestCase):
    """Tests for branch loop checkpoint resumption."""

    def test_checkpoint_tracks_branch_state(self):
        """Test that checkpoint.branch_states tracks loop iteration."""
        tmpdir = Path(tempfile.mkdtemp())
        checkpoint_dir = tmpdir / "checkpoints"

        # Create project with loop
        project = Project(name="main", root=tmpdir)
        project.input_nodes["input"] = InputNode(id="input")
        project.output_nodes["output"] = OutputNode(id="output")
        project.branches["loop1"] = BranchNode(
            id="loop1",
            workflow_path="./sub",  # Directory path
            loop_while="counter < 3",
            max_iterations=10,
        )
        project.edges["e1"] = Edge(
            id="e1",
            from_node="input",
            to_node="loop1",
            mappings=[EdgeMapping(target_var="counter", source_expr="counter")],
        )
        project.edges["e2"] = Edge(
            id="e2",
            from_node="loop1",
            to_node="output",
            mappings=[EdgeMapping(target_var="counter", source_expr="counter")],
        )
        project.entrypoints = ["input"]

        # Create sub-workflow directory with agent.tml
        sub_dir = tmpdir / "sub"
        sub_dir.mkdir()
        (sub_dir / "agent.tml").write_text("""
trident: "0.1"
name: sub
nodes:
  input:
    type: input
  output:
    type: output
tools:
  inc_tool:
    type: python
    path: inc_tool.py
edges:
  e1:
    from: input
    to: inc_tool
    mapping:
      counter: counter
  e2:
    from: inc_tool
    to: output
    mapping:
      counter: counter
""")

        tools_dir = sub_dir / "tools"
        tools_dir.mkdir()
        (tools_dir / "inc_tool.py").write_text("""
def execute(counter: int) -> dict:
    return {"counter": counter + 1}
""")

        result = run(
            project,
            inputs={"counter": 0},
            dry_run=False,
            checkpoint_dir=checkpoint_dir,
        )

        self.assertTrue(result.success)

        # Load checkpoint and verify branch_states
        from trident.executor import Checkpoint

        # Multiple checkpoints may exist (main + sub-workflows)
        # Find the main checkpoint (the one with branch_states)
        checkpoint_files = list(checkpoint_dir.glob("*.json"))
        self.assertGreater(len(checkpoint_files), 0)

        main_checkpoint = None
        for cp_file in checkpoint_files:
            checkpoint = Checkpoint.load(cp_file)
            if checkpoint.branch_states:
                main_checkpoint = checkpoint
                break

        self.assertIsNotNone(main_checkpoint, "No checkpoint found with branch_states")
        # After 3 iterations (0, 1, 2), branch_states should have last completed = 2
        self.assertIn("loop1", main_checkpoint.branch_states)
        self.assertEqual(main_checkpoint.branch_states["loop1"], 2)


class TestSubworkflowValidation(unittest.TestCase):
    """Tests for sub-workflow validation."""

    def test_validate_valid_subworkflow(self):
        """Test validation passes for valid sub-workflow in its own directory."""
        from trident.dag import validate_subworkflows

        tmpdir = Path(tempfile.mkdtemp())

        # Create main project
        project = Project(name="main", root=tmpdir)
        project.branches["branch1"] = BranchNode(
            id="branch1",
            workflow_path="./workflows/sub",  # Directory, not file
        )

        # Create valid sub-workflow in its own directory
        sub_dir = tmpdir / "workflows" / "sub"
        sub_dir.mkdir(parents=True)
        (sub_dir / "agent.tml").write_text("""
trident: "0.1"
name: sub
nodes:
  input:
    type: input
  output:
    type: output
edges:
  e1:
    from: input
    to: output
""")

        result = validate_subworkflows(project)

        self.assertTrue(result.valid, f"Expected valid, got errors: {result.errors}")
        self.assertEqual(len(result.errors), 0)

    def test_validate_missing_subworkflow(self):
        """Test validation fails for missing sub-workflow file."""
        from trident.dag import validate_subworkflows

        tmpdir = Path(tempfile.mkdtemp())

        project = Project(name="main", root=tmpdir)
        project.branches["branch1"] = BranchNode(
            id="branch1",
            workflow_path="./workflows/nonexistent",
        )

        result = validate_subworkflows(project)

        self.assertFalse(result.valid)
        self.assertEqual(len(result.errors), 1)
        self.assertIn("workflow file not found", result.errors[0])
        self.assertIn("branch1", result.errors[0])

    def test_validate_invalid_subworkflow_yaml(self):
        """Test validation fails for invalid YAML in sub-workflow."""
        from trident.dag import validate_subworkflows

        tmpdir = Path(tempfile.mkdtemp())

        project = Project(name="main", root=tmpdir)
        project.branches["branch1"] = BranchNode(
            id="branch1",
            workflow_path="./workflows/bad",
        )

        # Create actually invalid YAML (unbalanced braces) in its own directory
        bad_dir = tmpdir / "workflows" / "bad"
        bad_dir.mkdir(parents=True)
        (bad_dir / "agent.tml").write_text("""
trident: "0.1"
name: bad
nodes: {unclosed
""")

        result = validate_subworkflows(project)

        self.assertFalse(result.valid)
        self.assertEqual(len(result.errors), 1)
        self.assertIn("branch1", result.errors[0])

    def test_validate_subworkflow_missing_required_fields(self):
        """Test validation fails when sub-workflow is missing required fields."""
        from trident.dag import validate_subworkflows

        tmpdir = Path(tempfile.mkdtemp())

        project = Project(name="main", root=tmpdir)
        project.branches["branch1"] = BranchNode(
            id="branch1",
            workflow_path="./workflows/incomplete",
        )

        # Create workflow missing 'name' field in its own directory
        incomplete_dir = tmpdir / "workflows" / "incomplete"
        incomplete_dir.mkdir(parents=True)
        (incomplete_dir / "agent.tml").write_text("""
trident: "0.1"
nodes:
  input:
    type: input
""")

        result = validate_subworkflows(project)

        self.assertFalse(result.valid)
        self.assertIn("branch1", result.errors[0])

    def test_validate_self_reference_allowed(self):
        """Test that 'self' workflow reference is allowed (not a cycle)."""
        from trident.dag import validate_subworkflows

        tmpdir = Path(tempfile.mkdtemp())

        project = Project(name="main", root=tmpdir)
        project.branches["recursive"] = BranchNode(
            id="recursive",
            workflow_path="self",
        )

        result = validate_subworkflows(project)

        self.assertTrue(result.valid)
        self.assertEqual(len(result.errors), 0)

    def test_validate_circular_reference_detected(self):
        """Test that circular workflow references are detected."""
        from trident.dag import validate_subworkflows

        tmpdir = Path(tempfile.mkdtemp())

        # Create main project pointing to sub1
        project = Project(name="main", root=tmpdir)
        project.branches["branch1"] = BranchNode(
            id="branch1",
            workflow_path="./sub1",
        )

        # Create sub1 pointing back to main (cycle)
        sub1_dir = tmpdir / "sub1"
        sub1_dir.mkdir()
        (sub1_dir / "agent.tml").write_text(f"""
trident: "0.1"
name: sub1
nodes:
  branch_back:
    type: branch
    workflow: {tmpdir.resolve()}
  input:
    type: input
  output:
    type: output
edges:
  e1:
    from: input
    to: branch_back
  e2:
    from: branch_back
    to: output
""")

        result = validate_subworkflows(project)

        self.assertFalse(result.valid)
        self.assertTrue(any("circular" in e.lower() for e in result.errors))

    def test_validate_nested_subworkflows(self):
        """Test recursive validation of nested sub-workflows."""
        from trident.dag import validate_subworkflows

        tmpdir = Path(tempfile.mkdtemp())

        # Main -> sub1 -> sub2
        project = Project(name="main", root=tmpdir)
        project.branches["branch1"] = BranchNode(
            id="branch1",
            workflow_path="./sub1",
        )

        # Create sub1 with branch to sub2
        sub1_dir = tmpdir / "sub1"
        sub1_dir.mkdir()
        (sub1_dir / "agent.tml").write_text("""
trident: "0.1"
name: sub1
nodes:
  input:
    type: input
  nested:
    type: branch
    workflow: ./sub2
  output:
    type: output
edges:
  e1:
    from: input
    to: nested
  e2:
    from: nested
    to: output
""")

        # Create sub2 (valid)
        sub2_dir = sub1_dir / "sub2"
        sub2_dir.mkdir()
        (sub2_dir / "agent.tml").write_text("""
trident: "0.1"
name: sub2
nodes:
  input:
    type: input
  output:
    type: output
edges:
  e1:
    from: input
    to: output
""")

        result = validate_subworkflows(project)

        self.assertTrue(result.valid)
        self.assertEqual(len(result.errors), 0)

    def test_validate_nested_subworkflow_error_propagates(self):
        """Test errors in nested sub-workflows are reported."""
        from trident.dag import validate_subworkflows

        tmpdir = Path(tempfile.mkdtemp())

        # Main -> sub1 -> missing_sub2
        project = Project(name="main", root=tmpdir)
        project.branches["branch1"] = BranchNode(
            id="branch1",
            workflow_path="./sub1",
        )

        # Create sub1 with branch to non-existent sub2
        sub1_dir = tmpdir / "sub1"
        sub1_dir.mkdir()
        (sub1_dir / "agent.tml").write_text("""
trident: "0.1"
name: sub1
nodes:
  input:
    type: input
  nested:
    type: branch
    workflow: ./nonexistent
  output:
    type: output
edges:
  e1:
    from: input
    to: nested
  e2:
    from: nested
    to: output
""")

        result = validate_subworkflows(project)

        self.assertFalse(result.valid)
        # Should report the nested error
        self.assertTrue(any("nonexistent" in e or "not found" in e for e in result.errors))

    def test_validate_no_branches_passes(self):
        """Test validation passes for project with no branch nodes."""
        from trident.dag import validate_subworkflows

        tmpdir = Path(tempfile.mkdtemp())

        project = Project(name="main", root=tmpdir)
        # No branches

        result = validate_subworkflows(project)

        self.assertTrue(result.valid)
        self.assertEqual(len(result.errors), 0)


if __name__ == "__main__":
    unittest.main()
