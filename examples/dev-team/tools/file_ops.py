"""File operation tools for the dev team."""

import subprocess
from pathlib import Path
from typing import Any


# Base path for file operations (configurable via environment)
import os
WORKSPACE = Path(os.environ.get("TRIDENT_WORKSPACE", ".")).resolve()


def read_file(path: str) -> dict[str, Any]:
    """Read a file's contents.

    Args:
        path: Path relative to workspace

    Returns:
        {"content": str, "exists": bool}
    """
    full_path = WORKSPACE / path
    if not full_path.exists():
        return {"content": "", "exists": False, "error": f"File not found: {path}"}

    if not full_path.is_file():
        return {"content": "", "exists": False, "error": f"Not a file: {path}"}

    try:
        content = full_path.read_text(encoding="utf-8")
        return {"content": content, "exists": True}
    except Exception as e:
        return {"content": "", "exists": False, "error": str(e)}


def write_file(path: str, content: str) -> dict[str, Any]:
    """Write content to a file.

    Args:
        path: Path relative to workspace
        content: Content to write

    Returns:
        {"success": bool, "path": str}
    """
    full_path = WORKSPACE / path

    try:
        # Create parent directories if needed
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        return {"success": True, "path": str(path)}
    except Exception as e:
        return {"success": False, "path": str(path), "error": str(e)}


def list_files(pattern: str = "**/*.py") -> dict[str, Any]:
    """List files matching a glob pattern.

    Args:
        pattern: Glob pattern relative to workspace

    Returns:
        {"files": list[str]}
    """
    try:
        files = sorted(str(p.relative_to(WORKSPACE)) for p in WORKSPACE.glob(pattern))
        return {"files": files}
    except Exception as e:
        return {"files": [], "error": str(e)}


def list_project_structure() -> dict[str, Any]:
    """List all Python files in the project with their structure.

    Returns:
        {"files": str} - Formatted list of project files
    """
    try:
        # Get Python files, excluding common non-source directories
        exclude = {".git", "__pycache__", ".venv", "venv", "node_modules", ".eggs", "*.egg-info"}
        files = []

        for p in WORKSPACE.rglob("*.py"):
            # Skip excluded directories
            if any(ex in str(p) for ex in exclude):
                continue
            rel_path = str(p.relative_to(WORKSPACE))
            files.append(rel_path)

        # Also include .prompt files
        for p in WORKSPACE.rglob("*.prompt"):
            if any(ex in str(p) for ex in exclude):
                continue
            rel_path = str(p.relative_to(WORKSPACE))
            files.append(rel_path)

        # Sort and format
        files.sort()
        formatted = "\n".join(files)
        return {"files": formatted}
    except Exception as e:
        return {"files": "", "error": str(e)}


def search_multiple(terms: list[str] | str, file_pattern: str = "**/*.py") -> dict[str, Any]:
    """Search for multiple terms in files.

    Args:
        terms: List of search terms or comma-separated string
        file_pattern: Glob pattern for files to search

    Returns:
        {"matches": list[{"term": str, "file": str, "line": int, "text": str}]}
    """
    if isinstance(terms, str):
        terms = [t.strip() for t in terms.split(",") if t.strip()]

    all_matches = []
    seen = set()  # Avoid duplicate file/line combos

    for term in terms[:10]:  # Limit to 10 terms
        for file_path in WORKSPACE.glob(file_pattern):
            if not file_path.is_file():
                continue
            try:
                content = file_path.read_text(encoding="utf-8")
                for i, line in enumerate(content.split("\n"), 1):
                    if term.lower() in line.lower():
                        key = (str(file_path), i)
                        if key not in seen:
                            seen.add(key)
                            all_matches.append({
                                "term": term,
                                "file": str(file_path.relative_to(WORKSPACE)),
                                "line": i,
                                "text": line.strip()[:200],
                            })
            except:
                continue

    # Sort by file, then line
    all_matches.sort(key=lambda x: (x["file"], x["line"]))
    return {"matches": all_matches[:100]}


def search_files(pattern: str, file_pattern: str = "**/*.py") -> dict[str, Any]:
    """Search for a pattern in files.

    Args:
        pattern: Text pattern to search for
        file_pattern: Glob pattern for files to search

    Returns:
        {"matches": list[{"file": str, "line": int, "text": str}]}
    """
    matches = []
    try:
        for file_path in WORKSPACE.glob(file_pattern):
            if not file_path.is_file():
                continue
            try:
                content = file_path.read_text(encoding="utf-8")
                for i, line in enumerate(content.split("\n"), 1):
                    if pattern in line:
                        matches.append({
                            "file": str(file_path.relative_to(WORKSPACE)),
                            "line": i,
                            "text": line.strip()[:200],
                        })
            except:
                continue
        return {"matches": matches[:50]}  # Limit results
    except Exception as e:
        return {"matches": [], "error": str(e)}


def read_files_multi(files: list[str] | str) -> dict[str, Any]:
    """Read multiple files and concatenate their contents.

    Args:
        files: List of file paths or comma-separated string

    Returns:
        {"content": str, "files_read": list[str]}
    """
    if isinstance(files, str):
        files = [f.strip() for f in files.split(",") if f.strip()]

    contents = []
    files_read = []

    for path in files[:10]:  # Limit to 10 files
        result = read_file(path)
        if result.get("exists"):
            contents.append(f"### {path}\n```\n{result['content']}\n```\n")
            files_read.append(path)

    return {
        "content": "\n".join(contents) if contents else "No files found",
        "files_read": files_read,
    }


def check_python_syntax(path: str) -> dict[str, Any]:
    """Check if a Python file has valid syntax.

    Args:
        path: Path relative to workspace

    Returns:
        {"valid": bool, "error": str | None}
    """
    full_path = WORKSPACE / path
    if not full_path.exists():
        return {"valid": False, "error": f"File not found: {path}"}

    try:
        result = subprocess.run(
            ["python", "-m", "py_compile", str(full_path)],
            cwd=WORKSPACE,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return {"valid": True, "error": None}
        else:
            return {"valid": False, "error": result.stderr.strip()}
    except Exception as e:
        return {"valid": False, "error": str(e)}


def write_files_multi(code_changes: list[dict] | str) -> dict[str, Any]:
    """Write multiple files from code changes and validate Python syntax.

    Args:
        code_changes: List of {path, content, action} or JSON string

    Returns:
        {"success": bool, "files_written": list[str], "syntax_errors": list[str]}
    """
    import json as json_module

    if isinstance(code_changes, str):
        try:
            code_changes = json_module.loads(code_changes)
        except:
            return {"success": False, "files_written": [], "error": "Invalid JSON"}

    if not isinstance(code_changes, list):
        return {"success": False, "files_written": [], "error": "Expected list of changes"}

    files_written = []
    errors = []
    syntax_errors = []

    for change in code_changes:
        if not isinstance(change, dict):
            continue
        path = change.get("path", "")
        content = change.get("content", "")
        if path and content:
            result = write_file(path, content)
            if result.get("success"):
                files_written.append(path)
                # Validate Python syntax for .py files
                if path.endswith(".py"):
                    syntax_result = check_python_syntax(path)
                    if not syntax_result.get("valid"):
                        syntax_errors.append(f"{path}: {syntax_result.get('error')}")
            else:
                errors.append(f"{path}: {result.get('error', 'unknown error')}")

    return {
        "success": len(errors) == 0 and len(syntax_errors) == 0,
        "files_written": files_written,
        "errors": errors if errors else None,
        "syntax_errors": syntax_errors if syntax_errors else None,
    }


def run_tests(test_path: str = "tests/") -> dict[str, Any]:
    """Run tests and return results.

    Args:
        test_path: Path to tests relative to workspace

    Returns:
        {"passed": bool, "output": str, "num_passed": int, "num_failed": int}
    """
    try:
        result = subprocess.run(
            ["python", "-m", "unittest", "discover", test_path, "-v"],
            cwd=WORKSPACE,
            capture_output=True,
            text=True,
            timeout=120,
        )

        output = result.stdout + result.stderr
        passed = result.returncode == 0

        # Parse test counts from output
        num_passed = output.count(" ... ok")
        num_failed = output.count(" ... FAIL") + output.count(" ... ERROR")

        return {
            "passed": passed,
            "output": output[-3000:],  # Last 3000 chars
            "num_passed": num_passed,
            "num_failed": num_failed,
        }
    except subprocess.TimeoutExpired:
        return {"passed": False, "output": "Tests timed out", "num_passed": 0, "num_failed": 0}
    except Exception as e:
        return {"passed": False, "output": str(e), "num_passed": 0, "num_failed": 0}
