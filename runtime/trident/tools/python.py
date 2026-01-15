"""Python tool execution."""

import importlib.util
import inspect
import sys
from pathlib import Path
from typing import Any

from ..errors import ToolError
from ..project import ToolDef


def get_tool_parameters(project_root: Path, tool_def: ToolDef) -> set[str] | None:
    """Introspect a Python tool function to get its parameter names.

    Args:
        project_root: Project root directory
        tool_def: Tool definition

    Returns:
        Set of parameter names, or None if introspection fails
    """
    if tool_def.type != "python":
        return None

    module_path = tool_def.module or tool_def.path
    if not module_path:
        return None

    # Resolve path
    if not module_path.endswith(".py"):
        module_path = f"{module_path}.py"

    # Support relative paths (e.g., ../shared/browser.py)
    if module_path.startswith("../") or module_path.startswith("/"):
        full_path = (project_root / module_path).resolve()
    else:
        full_path = project_root / "tools" / module_path
    if not full_path.exists():
        return None

    try:
        # Load module
        spec = importlib.util.spec_from_file_location(
            module_path.replace(".py", "").replace("/", "."),
            full_path,
        )
        if spec is None or spec.loader is None:
            return None

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Get function
        function_name = tool_def.function or "execute"
        func = getattr(module, function_name, None)
        if func is None or not callable(func):
            return None

        # Introspect signature
        sig = inspect.signature(func)
        params = set()
        for name, param in sig.parameters.items():
            # Skip *args and **kwargs
            if param.kind in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            ):
                continue
            params.add(name)

        return params

    except Exception:
        # Introspection failed - return None to indicate unknown
        return None


class PythonToolRunner:
    """Executes Python callable tools."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self._loaded_modules: dict[str, Any] = {}

    def _load_module(self, module_path: str) -> Any:
        """Load a Python module from the tools directory."""
        if module_path in self._loaded_modules:
            return self._loaded_modules[module_path]

        # Resolve path
        if not module_path.endswith(".py"):
            module_path = f"{module_path}.py"

        # Support relative paths (e.g., ../shared/browser.py)
        if module_path.startswith("../") or module_path.startswith("/"):
            full_path = (self.project_root / module_path).resolve()
        else:
            # Default: look in project tools/ directory
            full_path = self.project_root / "tools" / module_path
        if not full_path.exists():
            raise ToolError(f"Tool module not found: {full_path}")

        try:
            spec = importlib.util.spec_from_file_location(
                module_path.replace(".py", "").replace("/", "."),
                full_path,
            )
            if spec is None or spec.loader is None:
                raise ToolError(f"Cannot load module: {full_path}")

            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)

            self._loaded_modules[module_path] = module
            return module

        except Exception as e:
            raise ToolError(f"Error loading tool module {full_path}: {e}") from e

    def execute(self, tool_def: ToolDef, inputs: dict[str, Any]) -> dict[str, Any]:
        """Execute a Python tool.

        Args:
            tool_def: Tool definition from project
            inputs: Input values from edge mappings

        Returns:
            Dictionary of output values
        """
        if tool_def.type != "python":
            raise ToolError(f"PythonToolRunner cannot execute tool type: {tool_def.type}")

        module_path = tool_def.module or tool_def.path
        if not module_path:
            raise ToolError(f"Tool {tool_def.id} has no module or path specified")

        function_name = tool_def.function or "execute"

        try:
            module = self._load_module(module_path)
            func = getattr(module, function_name, None)
            if func is None:
                raise ToolError(f"Function '{function_name}' not found in {module_path}")
            if not callable(func):
                raise ToolError(f"'{function_name}' in {module_path} is not callable")

            result = func(**inputs)

            # Ensure result is a dict
            if not isinstance(result, dict):
                result = {"output": result}

            return result

        except ToolError:
            raise
        except Exception as e:
            raise ToolError(f"Error executing tool {tool_def.id}: {e}") from e
