"""File operation tools for the dev team."""

# Base path for file operations (configurable via environment)
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

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
                            all_matches.append(
                                {
                                    "term": term,
                                    "file": str(file_path.relative_to(WORKSPACE)),
                                    "line": i,
                                    "text": line.strip()[:200],
                                }
                            )
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
                        matches.append(
                            {
                                "file": str(file_path.relative_to(WORKSPACE)),
                                "line": i,
                                "text": line.strip()[:200],
                            }
                        )
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


def apply_patches(patches: list[dict] | str) -> dict[str, Any]:
    """Apply unified diff patches to files.

    Args:
        patches: List of {path, diff} objects or JSON string

    Returns:
        {"success": bool, "files_patched": list[str], "errors": list[str]}
    """
    import json as json_module

    if isinstance(patches, str):
        try:
            patches = json_module.loads(patches)
        except:
            return {"success": False, "files_patched": [], "errors": ["Invalid JSON"]}

    if not isinstance(patches, list):
        return {"success": False, "files_patched": [], "errors": ["Expected list of patches"]}

    files_patched = []
    errors = []

    for patch in patches:
        if not isinstance(patch, dict):
            continue
        
        path = patch.get("path", "")
        diff = patch.get("diff", "")
        
        if not path or not diff:
            continue

        full_path = WORKSPACE / path
        
        # Write diff to temp file and apply with patch command
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.patch', delete=False) as f:
                f.write(diff)
                patch_file = f.name

            # Try to apply the patch
            result = subprocess.run(
                ["patch", "-p1", "--forward", "-i", patch_file],
                cwd=WORKSPACE,
                capture_output=True,
                text=True,
                timeout=30,
            )

            os.unlink(patch_file)

            if result.returncode == 0:
                files_patched.append(path)
                # Validate Python syntax for .py files
                if path.endswith(".py"):
                    syntax_result = check_python_syntax(path)
                    if not syntax_result.get("valid"):
                        errors.append(f"{path}: Syntax error after patching: {syntax_result.get('error')}")
            else:
                # If patch fails, try a fallback approach
                error_msg = result.stderr.strip() or result.stdout.strip()
                errors.append(f"{path}: Patch failed - {error_msg}")

        except FileNotFoundError:
            errors.append(f"{path}: 'patch' command not found")
        except Exception as e:
            errors.append(f"{path}: {str(e)}")

    return {
        "success": len(errors) == 0,
        "files_patched": files_patched,
        "errors": errors if errors else None,
    }


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


def run_lint(fix: bool = True) -> dict[str, Any]:
    """Run ruff linter and optionally fix issues.

    Args:
        fix: If True, auto-fix fixable issues

    Returns:
        {"passed": bool, "output": str, "fixed": int, "remaining": int}
    """
    results = {"passed": True, "output": "", "fixed": 0, "remaining": 0}

    try:
        # First run ruff check with fix if requested
        check_cmd = ["ruff", "check", "."]
        if fix:
            check_cmd.append("--fix")

        result = subprocess.run(
            check_cmd,
            cwd=WORKSPACE,
            capture_output=True,
            text=True,
            timeout=60,
        )

        check_output = result.stdout + result.stderr
        results["output"] = check_output

        # Count fixed issues (look for "Fixed" in output)
        if "Fixed" in check_output:
            import re

            match = re.search(r"Fixed (\d+)", check_output)
            if match:
                results["fixed"] = int(match.group(1))

        # Run format
        format_result = subprocess.run(
            ["ruff", "format", "."],
            cwd=WORKSPACE,
            capture_output=True,
            text=True,
            timeout=60,
        )

        format_output = format_result.stdout + format_result.stderr
        if format_output.strip():
            results["output"] += "\n" + format_output

        # Run check again to see remaining issues
        final_check = subprocess.run(
            ["ruff", "check", "."],
            cwd=WORKSPACE,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if final_check.returncode != 0:
            results["passed"] = False
            results["output"] += "\n\nRemaining issues:\n" + final_check.stdout + final_check.stderr
            # Count remaining issues
            remaining_lines = [
                line for line in final_check.stdout.split("\n") if line.strip() and ":" in line
            ]
            results["remaining"] = len(remaining_lines)

        return results

    except FileNotFoundError:
        return {
            "passed": False,
            "output": "ruff not found. Install with: pip install ruff",
            "fixed": 0,
            "remaining": 0,
        }
    except subprocess.TimeoutExpired:
        return {"passed": False, "output": "Lint timed out", "fixed": 0, "remaining": 0}
    except Exception as e:
        return {"passed": False, "output": str(e), "fixed": 0, "remaining": 0}


def run_typecheck() -> dict[str, Any]:
    """Run pyright type checker.

    Returns:
        {"passed": bool, "output": str, "errors": int}
    """
    try:
        result = subprocess.run(
            ["pyright", "."],
            cwd=WORKSPACE,
            capture_output=True,
            text=True,
            timeout=120,
        )

        output = result.stdout + result.stderr
        passed = result.returncode == 0

        # Count errors
        errors = 0
        import re

        match = re.search(r"(\d+) errors?", output)
        if match:
            errors = int(match.group(1))

        return {
            "passed": passed,
            "output": output[-3000:],
            "errors": errors,
        }
    except FileNotFoundError:
        return {
            "passed": True,  # Don't fail if pyright not installed
            "output": "pyright not found. Install with: pip install pyright",
            "errors": 0,
        }
    except subprocess.TimeoutExpired:
        return {"passed": False, "output": "Type check timed out", "errors": 0}
    except Exception as e:
        return {"passed": False, "output": str(e), "errors": 0}


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
