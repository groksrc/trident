"""Tests for tool introspection and execution."""

import tempfile
import unittest
from pathlib import Path

from trident.project import ToolDef
from trident.tools.python import get_tool_parameters


class TestToolIntrospection(unittest.TestCase):
    """Tests for tool function introspection."""

    def setUp(self):
        """Create a temporary project with tool modules."""
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = Path(self.temp_dir)
        self.tools_dir = self.project_root / "tools"
        self.tools_dir.mkdir()

    def tearDown(self):
        """Clean up temporary directory."""
        import shutil

        shutil.rmtree(self.temp_dir)

    def _write_tool(self, filename: str, content: str) -> None:
        """Write a tool module to the temp tools directory."""
        (self.tools_dir / filename).write_text(content)

    def test_introspect_simple_function(self):
        """Introspects a simple function with named parameters."""
        self._write_tool(
            "simple.py",
            """
def process(name: str, count: int) -> dict:
    return {"result": f"{name} x {count}"}
""",
        )

        tool_def = ToolDef(
            id="simple",
            type="python",
            module="simple",
            function="process",
        )

        params = get_tool_parameters(self.project_root, tool_def)
        self.assertEqual(params, {"name", "count"})

    def test_introspect_function_with_defaults(self):
        """Introspects a function with default parameter values."""
        self._write_tool(
            "defaults.py",
            """
def fetch(query: str, limit: int = 10, offset: int = 0) -> dict:
    return {"items": []}
""",
        )

        tool_def = ToolDef(
            id="defaults",
            type="python",
            module="defaults",
            function="fetch",
        )

        params = get_tool_parameters(self.project_root, tool_def)
        self.assertEqual(params, {"query", "limit", "offset"})

    def test_introspect_function_with_kwargs(self):
        """Introspects a function with **kwargs - should skip var keyword."""
        self._write_tool(
            "kwargs.py",
            """
def flexible(required: str, **kwargs) -> dict:
    return {"data": required}
""",
        )

        tool_def = ToolDef(
            id="kwargs",
            type="python",
            module="kwargs",
            function="flexible",
        )

        params = get_tool_parameters(self.project_root, tool_def)
        # Should only include 'required', not kwargs
        self.assertEqual(params, {"required"})

    def test_introspect_function_with_args(self):
        """Introspects a function with *args - should skip var positional."""
        self._write_tool(
            "args.py",
            """
def variadic(first: str, *args) -> dict:
    return {"first": first, "rest": args}
""",
        )

        tool_def = ToolDef(
            id="args",
            type="python",
            module="args",
            function="variadic",
        )

        params = get_tool_parameters(self.project_root, tool_def)
        # Should only include 'first', not args
        self.assertEqual(params, {"first"})

    def test_introspect_default_execute_function(self):
        """Introspects the default 'execute' function when no function specified."""
        self._write_tool(
            "default_fn.py",
            """
def execute(input_data: str) -> dict:
    return {"output": input_data}
""",
        )

        tool_def = ToolDef(
            id="default_fn",
            type="python",
            module="default_fn",
            # No function specified - should default to 'execute'
        )

        params = get_tool_parameters(self.project_root, tool_def)
        self.assertEqual(params, {"input_data"})

    def test_introspect_missing_module_returns_none(self):
        """Returns None when module file doesn't exist."""
        tool_def = ToolDef(
            id="missing",
            type="python",
            module="nonexistent",
            function="process",
        )

        params = get_tool_parameters(self.project_root, tool_def)
        self.assertIsNone(params)

    def test_introspect_missing_function_returns_none(self):
        """Returns None when function doesn't exist in module."""
        self._write_tool(
            "no_func.py",
            """
def other_function():
    pass
""",
        )

        tool_def = ToolDef(
            id="no_func",
            type="python",
            module="no_func",
            function="nonexistent",
        )

        params = get_tool_parameters(self.project_root, tool_def)
        self.assertIsNone(params)

    def test_introspect_non_python_tool_returns_none(self):
        """Returns None for non-Python tools."""
        tool_def = ToolDef(
            id="shell_tool",
            type="shell",
            path="script.sh",
        )

        params = get_tool_parameters(self.project_root, tool_def)
        self.assertIsNone(params)

    def test_introspect_no_parameters(self):
        """Introspects a function with no parameters."""
        self._write_tool(
            "no_params.py",
            """
def get_timestamp() -> dict:
    import time
    return {"timestamp": time.time()}
""",
        )

        tool_def = ToolDef(
            id="no_params",
            type="python",
            module="no_params",
            function="get_timestamp",
        )

        params = get_tool_parameters(self.project_root, tool_def)
        self.assertEqual(params, set())


if __name__ == "__main__":
    unittest.main()
