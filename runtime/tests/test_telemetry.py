"""Tests for telemetry system."""

import json
import unittest
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from trident.telemetry import (
    EventType,
    TelemetryConfig,
    TelemetryEmitter,
    TelemetryEvent,
    TelemetryLevel,
)


class TestTelemetryEvent(unittest.TestCase):
    """Tests for TelemetryEvent structure."""

    def test_event_creation(self):
        """TelemetryEvent can be created with required fields."""
        event = TelemetryEvent(
            event_type=EventType.WORKFLOW_STARTED,
            run_id="test-run-123",
            level=TelemetryLevel.INFO,
            data={"name": "test-workflow"},
        )

        self.assertEqual(event.event_type, EventType.WORKFLOW_STARTED)
        self.assertEqual(event.run_id, "test-run-123")
        self.assertEqual(event.level, TelemetryLevel.INFO)
        self.assertEqual(event.data["name"], "test-workflow")
        self.assertIsNotNone(event.timestamp)

    def test_event_with_node_id(self):
        """TelemetryEvent can include node_id for node-specific events."""
        event = TelemetryEvent(
            event_type=EventType.NODE_STARTED,
            run_id="test-run-123",
            node_id="input_node",
            level=TelemetryLevel.INFO,
            data={"type": "input"},
        )

        self.assertEqual(event.node_id, "input_node")

    def test_event_to_dict(self):
        """TelemetryEvent can be serialized to dict."""
        event = TelemetryEvent(
            event_type=EventType.WORKFLOW_COMPLETED,
            run_id="test-run-123",
            level=TelemetryLevel.INFO,
            data={"duration_ms": 1500},
        )

        event_dict = event.to_dict()

        self.assertEqual(event_dict["event"], "workflow_completed")
        self.assertEqual(event_dict["run_id"], "test-run-123")
        self.assertEqual(event_dict["level"], "INFO")
        self.assertEqual(event_dict["data"]["duration_ms"], 1500)
        self.assertIn("timestamp", event_dict)


class TestTelemetryConfig(unittest.TestCase):
    """Tests for TelemetryConfig."""

    def test_default_config(self):
        """TelemetryConfig has sensible defaults."""
        config = TelemetryConfig()

        self.assertFalse(config.enabled)
        self.assertEqual(config.format, "jsonl")
        self.assertIsNone(config.file_path)
        self.assertTrue(config.stdout)

    def test_config_with_file(self):
        """TelemetryConfig can be configured to write to file."""
        config = TelemetryConfig(
            enabled=True,
            file_path="/tmp/telemetry.log",
            stdout=False,
        )

        self.assertTrue(config.enabled)
        self.assertEqual(config.file_path, "/tmp/telemetry.log")
        self.assertFalse(config.stdout)


class TestTelemetryEmitter(unittest.TestCase):
    """Tests for TelemetryEmitter."""

    def test_emitter_disabled_by_default(self):
        """TelemetryEmitter does nothing when disabled."""
        output = StringIO()
        config = TelemetryConfig(enabled=False)

        with TelemetryEmitter(config, output_stream=output) as emitter:
            emitter.emit(
                EventType.WORKFLOW_STARTED,
                run_id="test-run",
                data={"name": "test"},
            )

        # Should emit nothing when disabled
        self.assertEqual(output.getvalue(), "")

    def test_emitter_json_lines_format(self):
        """TelemetryEmitter outputs JSON Lines format."""
        output = StringIO()
        config = TelemetryConfig(enabled=True, format="jsonl")

        with TelemetryEmitter(config, output_stream=output) as emitter:
            emitter.emit(
                EventType.WORKFLOW_STARTED,
                run_id="test-run-123",
                data={"name": "my-workflow"},
            )

        lines = output.getvalue().strip().split("\n")
        self.assertEqual(len(lines), 1)

        event_data = json.loads(lines[0])
        self.assertEqual(event_data["event"], "workflow_started")
        self.assertEqual(event_data["run_id"], "test-run-123")
        self.assertEqual(event_data["data"]["name"], "my-workflow")

    def test_emitter_multiple_events(self):
        """TelemetryEmitter can emit multiple events."""
        output = StringIO()
        config = TelemetryConfig(enabled=True, format="jsonl")

        with TelemetryEmitter(config, output_stream=output) as emitter:
            emitter.emit(
                EventType.WORKFLOW_STARTED,
                run_id="test-run",
                data={"name": "test"},
            )
            emitter.emit(
                EventType.NODE_STARTED,
                run_id="test-run",
                node_id="input",
                data={"type": "input"},
            )
            emitter.emit(
                EventType.WORKFLOW_COMPLETED,
                run_id="test-run",
                data={"duration_ms": 1000},
            )

        lines = output.getvalue().strip().split("\n")
        self.assertEqual(len(lines), 3)

        # Verify each event
        event1 = json.loads(lines[0])
        self.assertEqual(event1["event"], "workflow_started")

        event2 = json.loads(lines[1])
        self.assertEqual(event2["event"], "node_started")
        self.assertEqual(event2["node_id"], "input")

        event3 = json.loads(lines[2])
        self.assertEqual(event3["event"], "workflow_completed")

    def test_emitter_writes_to_file(self):
        """TelemetryEmitter can write to a file."""
        with TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "telemetry.log"
            config = TelemetryConfig(
                enabled=True,
                format="jsonl",
                file_path=str(log_file),
                stdout=False,
            )

            with TelemetryEmitter(config) as emitter:
                emitter.emit(
                    EventType.WORKFLOW_STARTED,
                    run_id="test-run",
                    data={"name": "test"},
                )

            # Verify file was created and contains the event
            self.assertTrue(log_file.exists())
            content = log_file.read_text()
            event_data = json.loads(content.strip())
            self.assertEqual(event_data["event"], "workflow_started")

    def test_emitter_human_readable_format(self):
        """TelemetryEmitter supports human-readable format."""
        output = StringIO()
        config = TelemetryConfig(enabled=True, format="human")

        with TelemetryEmitter(config, output_stream=output) as emitter:
            emitter.emit(
                EventType.WORKFLOW_STARTED,
                run_id="test-run-123",
                data={"name": "my-workflow"},
            )

        output_text = output.getvalue()
        self.assertIn("WORKFLOW_STARTED", output_text)
        self.assertIn("test-run-123", output_text)
        self.assertIn("my-workflow", output_text)

    def test_emitter_context_manager_flushes(self):
        """TelemetryEmitter flushes on context exit."""
        output = StringIO()
        config = TelemetryConfig(enabled=True, format="jsonl")

        with TelemetryEmitter(config, output_stream=output) as emitter:
            emitter.emit(
                EventType.WORKFLOW_STARTED,
                run_id="test-run",
                data={"name": "test"},
            )
            # Before exit, output should already be available
            # (we're not buffering in this simple implementation)

        # After exit, ensure everything is flushed
        self.assertGreater(len(output.getvalue()), 0)


class TestEventTypes(unittest.TestCase):
    """Tests for EventType enum."""

    def test_lifecycle_events_defined(self):
        """Lifecycle event types are defined."""
        self.assertIsNotNone(EventType.WORKFLOW_STARTED)
        self.assertIsNotNone(EventType.WORKFLOW_COMPLETED)
        self.assertIsNotNone(EventType.WORKFLOW_FAILED)

    def test_node_events_defined(self):
        """Node event types are defined."""
        self.assertIsNotNone(EventType.NODE_STARTED)
        self.assertIsNotNone(EventType.NODE_COMPLETED)
        self.assertIsNotNone(EventType.NODE_FAILED)
        self.assertIsNotNone(EventType.NODE_SKIPPED)

    def test_event_type_string_conversion(self):
        """EventType converts to snake_case string."""
        self.assertEqual(EventType.WORKFLOW_STARTED.to_string(), "workflow_started")
        self.assertEqual(EventType.NODE_COMPLETED.to_string(), "node_completed")


class TestTelemetryLevel(unittest.TestCase):
    """Tests for TelemetryLevel enum."""

    def test_levels_defined(self):
        """Telemetry levels are defined."""
        self.assertIsNotNone(TelemetryLevel.DEBUG)
        self.assertIsNotNone(TelemetryLevel.INFO)
        self.assertIsNotNone(TelemetryLevel.WARNING)
        self.assertIsNotNone(TelemetryLevel.ERROR)


if __name__ == "__main__":
    unittest.main()
