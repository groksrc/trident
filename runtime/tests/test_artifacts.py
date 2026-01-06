"""Tests for artifact management."""

import json
import tempfile
import unittest
from pathlib import Path

from trident.artifacts import (
    ArtifactConfig,
    ArtifactManager,
    BranchIterationState,
    RunEntry,
    RunManifest,
    RunMetadata,
    find_latest_run,
    get_artifact_manager,
)
from trident.executor import Checkpoint, CheckpointNodeData, ExecutionTrace, NodeTrace


class TestRunManifest(unittest.TestCase):
    """Tests for RunManifest class."""

    def test_load_nonexistent_returns_empty(self):
        """Loading nonexistent manifest returns empty manifest."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = RunManifest.load(Path(tmpdir) / "manifest.json")
            self.assertEqual(manifest.runs, [])

    def test_save_and_load_roundtrip(self):
        """Manifest can be saved and loaded correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "manifest.json"

            manifest = RunManifest()
            manifest.add_run(
                RunEntry(
                    run_id="test-run-1",
                    project_name="test-project",
                    entrypoint="input",
                    status="completed",
                    started_at="2024-01-01T00:00:00Z",
                    ended_at="2024-01-01T00:01:00Z",
                    success=True,
                )
            )
            manifest.save(manifest_path)

            loaded = RunManifest.load(manifest_path)
            self.assertEqual(len(loaded.runs), 1)
            self.assertEqual(loaded.runs[0].run_id, "test-run-1")
            self.assertTrue(loaded.runs[0].success)

    def test_get_latest(self):
        """get_latest returns most recent run."""
        manifest = RunManifest()
        manifest.add_run(
            RunEntry(
                run_id="run-1",
                project_name="test",
                entrypoint=None,
                status="completed",
                started_at="2024-01-01T00:00:00Z",
            )
        )
        manifest.add_run(
            RunEntry(
                run_id="run-2",
                project_name="test",
                entrypoint=None,
                status="completed",
                started_at="2024-01-02T00:00:00Z",
            )
        )

        latest = manifest.get_latest()
        self.assertIsNotNone(latest)
        self.assertEqual(latest.run_id, "run-2")

    def test_get_run_by_id(self):
        """get_run returns specific run by ID."""
        manifest = RunManifest()
        manifest.add_run(
            RunEntry(
                run_id="run-1",
                project_name="test",
                entrypoint=None,
                status="completed",
                started_at="2024-01-01T00:00:00Z",
            )
        )

        found = manifest.get_run("run-1")
        self.assertIsNotNone(found)
        self.assertEqual(found.run_id, "run-1")

        not_found = manifest.get_run("nonexistent")
        self.assertIsNone(not_found)

    def test_update_run(self):
        """update_run modifies existing entry."""
        manifest = RunManifest()
        manifest.add_run(
            RunEntry(
                run_id="run-1",
                project_name="test",
                entrypoint=None,
                status="running",
                started_at="2024-01-01T00:00:00Z",
            )
        )

        manifest.update_run("run-1", status="completed", success=True)

        run = manifest.get_run("run-1")
        self.assertEqual(run.status, "completed")
        self.assertTrue(run.success)


class TestArtifactManager(unittest.TestCase):
    """Tests for ArtifactManager class."""

    def test_save_and_load_checkpoint(self):
        """ArtifactManager saves and loads checkpoints."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = ArtifactConfig(base_dir=Path(tmpdir))
            manager = ArtifactManager(config, "test-run")

            checkpoint = Checkpoint(
                run_id="test-run",
                project_name="test-project",
                started_at="2024-01-01T00:00:00Z",
                updated_at="2024-01-01T00:00:00Z",
                status="completed",
                inputs={"text": "hello"},
            )
            checkpoint.completed_nodes["node1"] = CheckpointNodeData(
                outputs={"result": "world"},
                completed_at="2024-01-01T00:00:01Z",
            )

            manager.save_checkpoint(checkpoint)
            loaded = manager.load_checkpoint()

            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.run_id, "test-run")
            self.assertEqual(loaded.inputs, {"text": "hello"})
            self.assertIn("node1", loaded.completed_nodes)

    def test_save_trace(self):
        """ArtifactManager saves execution trace."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = ArtifactConfig(base_dir=Path(tmpdir))
            manager = ArtifactManager(config, "test-run")

            trace = ExecutionTrace(
                run_id="test-run",
                start_time="2024-01-01T00:00:00Z",
                end_time="2024-01-01T00:01:00Z",
            )
            trace.nodes.append(
                NodeTrace(
                    id="node1",
                    start_time="2024-01-01T00:00:00Z",
                    end_time="2024-01-01T00:00:30Z",
                    output={"result": "test"},
                )
            )

            path = manager.save_trace(trace)
            self.assertTrue(path.exists())

            data = json.loads(path.read_text())
            self.assertEqual(data["run_id"], "test-run")
            self.assertEqual(len(data["nodes"]), 1)

    def test_save_outputs(self):
        """ArtifactManager saves outputs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = ArtifactConfig(base_dir=Path(tmpdir))
            manager = ArtifactManager(config, "test-run")

            outputs = {"result": "success", "data": [1, 2, 3]}
            path = manager.save_outputs(outputs)

            self.assertTrue(path.exists())
            data = json.loads(path.read_text())
            self.assertEqual(data["result"], "success")

    def test_save_metadata(self):
        """ArtifactManager saves run metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = ArtifactConfig(base_dir=Path(tmpdir))
            manager = ArtifactManager(config, "test-run")

            metadata = RunMetadata(
                run_id="test-run",
                project_name="test-project",
                project_root="/path/to/project",
                entrypoint="input",
                inputs={"text": "hello"},
                started_at="2024-01-01T00:00:00Z",
            )

            path = manager.save_metadata(metadata)
            self.assertTrue(path.exists())

    def test_register_and_update_run(self):
        """ArtifactManager registers and updates runs in manifest."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = ArtifactConfig(base_dir=Path(tmpdir))
            manager = ArtifactManager(config, "test-run")

            manager.register_run("test-project", "input")
            manager.update_run_status("completed", success=True)

            manifest = RunManifest.load(manager.manifest_path)
            run = manifest.get_run("test-run")

            self.assertIsNotNone(run)
            self.assertEqual(run.status, "completed")
            self.assertTrue(run.success)


class TestBranchIterationState(unittest.TestCase):
    """Tests for BranchIterationState class."""

    def test_save_and_load_iteration(self):
        """BranchIterationState saves and loads correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "iteration_0.json"

            state = BranchIterationState(
                branch_id="loop1",
                iteration=0,
                inputs={"value": 10},
                outputs={"value": 20},
                started_at="2024-01-01T00:00:00Z",
                ended_at="2024-01-01T00:00:01Z",
            )
            state.save(path)

            loaded = BranchIterationState.load(path)
            self.assertEqual(loaded.branch_id, "loop1")
            self.assertEqual(loaded.iteration, 0)
            self.assertEqual(loaded.inputs["value"], 10)
            self.assertEqual(loaded.outputs["value"], 20)

    def test_artifact_manager_branch_iterations(self):
        """ArtifactManager handles branch iteration state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = ArtifactConfig(base_dir=Path(tmpdir))
            manager = ArtifactManager(config, "test-run")

            # Save multiple iterations
            for i in range(3):
                state = BranchIterationState(
                    branch_id="loop1",
                    iteration=i,
                    inputs={"value": i * 10},
                    outputs={"value": (i + 1) * 10},
                    started_at=f"2024-01-01T00:0{i}:00Z",
                    ended_at=f"2024-01-01T00:0{i}:01Z",
                )
                manager.save_branch_iteration("loop1", state)

            # Load all iterations
            iterations = manager.load_branch_iterations("loop1")
            self.assertEqual(len(iterations), 3)

            # Get latest
            latest = manager.get_latest_iteration("loop1")
            self.assertIsNotNone(latest)
            self.assertEqual(latest.iteration, 2)


class TestFindLatestRun(unittest.TestCase):
    """Tests for find_latest_run function."""

    def test_find_latest_run_exists(self):
        """find_latest_run returns latest when runs exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            manifest_path = project_root / ".trident" / "runs" / "manifest.json"

            manifest = RunManifest()
            manifest.add_run(
                RunEntry(
                    run_id="run-1",
                    project_name="test",
                    entrypoint=None,
                    status="completed",
                    started_at="2024-01-01T00:00:00Z",
                )
            )
            manifest.add_run(
                RunEntry(
                    run_id="run-2",
                    project_name="test",
                    entrypoint=None,
                    status="completed",
                    started_at="2024-01-02T00:00:00Z",
                )
            )
            manifest.save(manifest_path)

            latest = find_latest_run(project_root)
            self.assertEqual(latest, "run-2")

    def test_find_latest_run_no_runs(self):
        """find_latest_run returns None when no runs exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            latest = find_latest_run(Path(tmpdir))
            self.assertIsNone(latest)


class TestGetArtifactManager(unittest.TestCase):
    """Tests for get_artifact_manager function."""

    def test_default_artifact_dir(self):
        """get_artifact_manager uses project_root/.trident by default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            manager = get_artifact_manager(project_root, "test-run")

            self.assertEqual(manager.config.base_dir, project_root / ".trident")

    def test_custom_artifact_dir(self):
        """get_artifact_manager uses custom artifact_dir when provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            custom_dir = Path(tmpdir) / "custom_artifacts"
            manager = get_artifact_manager(project_root, "test-run", custom_dir)

            self.assertEqual(manager.config.base_dir, custom_dir)


if __name__ == "__main__":
    unittest.main()
