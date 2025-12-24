"""File operation tools for the dev team."""

# Base path for file operations (configurable via environment)
import json as json_module
import os
import re
import shutil
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


def check_python_syntax(path: str, workspace: Path | None = None) -> dict[str, Any]:
    """Check if a Python file has valid syntax.

    Args:
        path: Path relative to workspace
        workspace: Optional workspace override (for sandbox validation)

    Returns:
        {"valid": bool, "error": str | None}
    """
    ws = workspace or WORKSPACE
    full_path = ws / path
    if not full_path.exists():
        return {"valid": False, "error": f"File not found: {path}"}

    try:
        result = subprocess.run(
            ["python", "-m", "py_compile", str(full_path)],
            cwd=ws,
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


def _apply_patches_to_workspace(
    patches: list[dict], workspace: Path
) -> dict[str, Any]:
    """Apply patches to a specific workspace directory.

    Args:
        patches: List of {path, diff} objects
        workspace: Target workspace directory

    Returns:
        {"success": bool, "files_patched": list[str], "errors": list[str]}
    """
    files_patched = []
    errors = []

    for patch in patches:
        if not isinstance(patch, dict):
            continue

        path = patch.get("path", "")
        diff = patch.get("diff", "")

        if not path or not diff:
            continue

        # Write diff to temp file and apply with patch command
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".patch", delete=False
            ) as f:
                f.write(diff)
                patch_file = f.name

            # Try to apply the patch
            result = subprocess.run(
                ["patch", "-p1", "--forward", "-i", patch_file],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=30,
            )

            os.unlink(patch_file)

            if result.returncode == 0:
                files_patched.append(path)
                # Validate Python syntax for .py files
                if path.endswith(".py"):
                    syntax_result = check_python_syntax(path, workspace)
                    if not syntax_result.get("valid"):
                        errors.append(
                            f"{path}: Syntax error after patching: {syntax_result.get('error')}"
                        )
            else:
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


def _run_lint_in_workspace(workspace: Path, fix: bool = True) -> dict[str, Any]:
    """Run ruff linter in a specific workspace.

    Args:
        workspace: Target workspace directory
        fix: If True, auto-fix fixable issues

    Returns:
        {"passed": bool, "output": str, "fixed": int, "remaining": int}
    """
    results = {"passed": True, "output": "", "fixed": 0, "remaining": 0}

    try:
        check_cmd = ["ruff", "check", "."]
        if fix:
            check_cmd.append("--fix")

        result = subprocess.run(
            check_cmd,
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=60,
        )

        check_output = result.stdout + result.stderr
        results["output"] = check_output

        if "Fixed" in check_output:
            match = re.search(r"Fixed (\d+)", check_output)
            if match:
                results["fixed"] = int(match.group(1))

        # Run format
        format_result = subprocess.run(
            ["ruff", "format", "."],
            cwd=workspace,
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
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=60,
        )

        if final_check.returncode != 0:
            results["passed"] = False
            results["output"] += (
                "\n\nRemaining issues:\n" + final_check.stdout + final_check.stderr
            )
            remaining_lines = [
                line
                for line in final_check.stdout.split("\n")
                if line.strip() and ":" in line
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


def _run_typecheck_in_workspace(workspace: Path) -> dict[str, Any]:
    """Run pyright type checker in a specific workspace.

    Args:
        workspace: Target workspace directory

    Returns:
        {"passed": bool, "output": str, "errors": int}
    """
    try:
        result = subprocess.run(
            ["pyright", "."],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=120,
        )

        output = result.stdout + result.stderr
        passed = result.returncode == 0

        errors = 0
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
            "passed": True,
            "output": "pyright not found. Install with: pip install pyright",
            "errors": 0,
        }
    except subprocess.TimeoutExpired:
        return {"passed": False, "output": "Type check timed out", "errors": 0}
    except Exception as e:
        return {"passed": False, "output": str(e), "errors": 0}


def _run_tests_in_workspace(
    workspace: Path, test_path: str = "tests/"
) -> dict[str, Any]:
    """Run tests in a specific workspace.

    Args:
        workspace: Target workspace directory
        test_path: Path to tests relative to workspace

    Returns:
        {"passed": bool, "output": str, "num_passed": int, "num_failed": int}
    """
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", test_path, "-v"],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=120,
        )

        output = result.stdout + result.stderr
        passed = result.returncode == 0

        # Parse test counts - pytest format
        num_passed = len(re.findall(r" PASSED", output))
        num_failed = len(re.findall(r" FAILED", output)) + len(
            re.findall(r" ERROR", output)
        )

        return {
            "passed": passed,
            "output": output[-3000:],
            "num_passed": num_passed,
            "num_failed": num_failed,
        }
    except subprocess.TimeoutExpired:
        return {
            "passed": False,
            "output": "Tests timed out",
            "num_passed": 0,
            "num_failed": 0,
        }
    except Exception as e:
        return {"passed": False, "output": str(e), "num_passed": 0, "num_failed": 0}


def validate_patches(patches: list[dict] | str) -> dict[str, Any]:
    """Validate patches in a sandbox before applying to the real workspace.

    Creates a temporary copy of the workspace, applies patches, runs lint/typecheck/tests,
    and reports results WITHOUT modifying the actual workspace.

    Args:
        patches: List of {path, diff} objects or JSON string

    Returns:
        {
            "valid": bool,              # True if all checks pass
            "patch_result": {...},      # Result of applying patches
            "lint_result": {...},       # Result of linting
            "typecheck_result": {...},  # Result of type checking
            "test_result": {...},       # Result of running tests
            "summary": str,             # Human-readable summary
            "errors": list[str],        # All errors encountered
        }
    """
    if isinstance(patches, str):
        try:
            patches = json_module.loads(patches)
        except:
            return {
                "valid": False,
                "patch_result": None,
                "lint_result": None,
                "typecheck_result": None,
                "test_result": None,
                "summary": "Invalid JSON in patches",
                "errors": ["Invalid JSON"],
            }

    if not isinstance(patches, list):
        return {
            "valid": False,
            "patch_result": None,
            "lint_result": None,
            "typecheck_result": None,
            "test_result": None,
            "summary": "Expected list of patches",
            "errors": ["Expected list of patches"],
        }

    all_errors: list[str] = []
    sandbox_dir = None

    try:
        # Create a temporary copy of the workspace
        sandbox_dir = Path(tempfile.mkdtemp(prefix="trident_sandbox_"))

        # Copy workspace to sandbox (excluding .git, .venv, __pycache__, node_modules)
        def ignore_patterns(directory: str, files: list[str]) -> list[str]:
            return [
                f
                for f in files
                if f in {".git", ".venv", "venv", "__pycache__", "node_modules", ".eggs"}
            ]

        shutil.copytree(WORKSPACE, sandbox_dir / "workspace", ignore=ignore_patterns, dirs_exist_ok=True)
        sandbox_workspace = sandbox_dir / "workspace"

        # Step 1: Apply patches in sandbox
        patch_result = _apply_patches_to_workspace(patches, sandbox_workspace)
        if not patch_result["success"]:
            all_errors.extend(patch_result.get("errors") or [])

        # Step 2: Run lint (with auto-fix in sandbox)
        lint_result = _run_lint_in_workspace(sandbox_workspace, fix=True)
        if not lint_result["passed"]:
            all_errors.append(f"Lint failed: {lint_result.get('remaining', 0)} issues remaining")

        # Step 3: Run typecheck
        typecheck_result = _run_typecheck_in_workspace(sandbox_workspace)
        if not typecheck_result["passed"]:
            all_errors.append(f"Typecheck failed: {typecheck_result.get('errors', 0)} errors")

        # Step 4: Run tests
        test_result = _run_tests_in_workspace(sandbox_workspace)
        if not test_result["passed"]:
            all_errors.append(
                f"Tests failed: {test_result.get('num_failed', 0)} failures"
            )

        # Build summary
        valid = (
            patch_result["success"]
            and lint_result["passed"]
            and typecheck_result["passed"]
            and test_result["passed"]
        )

        if valid:
            summary = (
                f"✅ All checks passed. "
                f"Patches applied to {len(patch_result.get('files_patched', []))} files. "
                f"Lint: {lint_result.get('fixed', 0)} auto-fixed. "
                f"Types: OK. "
                f"Tests: {test_result.get('num_passed', 0)} passed."
            )
        else:
            summary = f"❌ Validation failed: {'; '.join(all_errors)}"

        return {
            "valid": valid,
            "patch_result": patch_result,
            "lint_result": lint_result,
            "typecheck_result": typecheck_result,
            "test_result": test_result,
            "summary": summary,
            "errors": all_errors if all_errors else None,
        }

    except Exception as e:
        return {
            "valid": False,
            "patch_result": None,
            "lint_result": None,
            "typecheck_result": None,
            "test_result": None,
            "summary": f"Sandbox validation error: {str(e)}",
            "errors": [str(e)],
        }

    finally:
        # Clean up sandbox
        if sandbox_dir and sandbox_dir.exists():
            shutil.rmtree(sandbox_dir, ignore_errors=True)


def apply_patches(patches: list[dict] | str) -> dict[str, Any]:
    """Apply unified diff patches to files.

    Args:
        patches: List of {path, diff} objects or JSON string

    Returns:
        {"success": bool, "files_patched": list[str], "errors": list[str]}
    """
    if isinstance(patches, str):
        try:
            patches = json_module.loads(patches)
        except:
            return {"success": False, "files_patched": [], "errors": ["Invalid JSON"]}

    if not isinstance(patches, list):
        return {
            "success": False,
            "files_patched": [],
            "errors": ["Expected list of patches"],
        }

    return _apply_patches_to_workspace(patches, WORKSPACE)


def write_files_multi(code_changes: list[dict] | str) -> dict[str, Any]:
    """Write multiple files from code changes and validate Python syntax.

    Args:
        code_changes: List of {path, content, action} or JSON string

    Returns:
        {"success": bool, "files_written": list[str], "syntax_errors": list[str]}
    """
    if isinstance(code_changes, str):
        try:
            code_changes = json_module.loads(code_changes)
        except:
            return {"success": False, "files_written": [], "error": "Invalid JSON"}

    if not isinstance(code_changes, list):
        return {
            "success": False,
            "files_written": [],
            "error": "Expected list of changes",
        }

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
    return _run_lint_in_workspace(WORKSPACE, fix)


def run_typecheck() -> dict[str, Any]:
    """Run pyright type checker.

    Returns:
        {"passed": bool, "output": str, "errors": int}
    """
    return _run_typecheck_in_workspace(WORKSPACE)


def run_tests(test_path: str = "tests/") -> dict[str, Any]:
    """Run tests and return results.

    Args:
        test_path: Path to tests relative to workspace

    Returns:
        {"passed": bool, "output": str, "num_passed": int, "num_failed": int}
    """
    return _run_tests_in_workspace(WORKSPACE, test_path)


def validation_gate(
    patches: list[dict] | str,
    validation_result: dict[str, Any] | None,
    review_approved: bool = True,
    review_severity: str = "none",
) -> dict[str, Any]:
    """Pure function to decide whether to apply patches based on validation results.

    This is a deterministic gate - no LLM needed. The decision is:
    - If validation passed AND review approved (or minor issues only) -> proceed
    - Otherwise -> don't proceed, return errors

    Args:
        patches: The patches that were validated
        validation_result: Result from validate_patches tool
        review_approved: Whether code review approved
        review_severity: Severity of review issues (none/minor/major/critical)

    Returns:
        {
            "proceed": bool,
            "patches_to_apply": list[dict] | None,
            "status": str,  # "success" | "validation_failed" | "review_blocked"
            "summary": str,
            "errors": list[str] | None,
            "lint_output": str | None,
            "typecheck_output": str | None,
            "test_output": str | None,
        }
    """
    if isinstance(patches, str):
        try:
            patches = json_module.loads(patches)
        except:
            return {
                "proceed": False,
                "patches_to_apply": None,
                "status": "validation_failed",
                "summary": "Invalid patches JSON",
                "errors": ["Invalid patches JSON"],
                "lint_output": None,
                "typecheck_output": None,
                "test_output": None,
            }

    # Handle None validation_result (e.g., dry-run mode)
    if validation_result is None:
        validation_result = {"valid": False, "summary": "No validation result (dry-run?)"}

    # Check review status - block on major/critical issues
    review_dominated = review_severity in ("major", "critical")
    if not review_approved and review_dominated:
        return {
            "proceed": False,
            "patches_to_apply": None,
            "status": "review_blocked",
            "summary": f"Code review blocked: {review_severity} issues found",
            "errors": [f"Code review has {review_severity} issues that must be addressed"],
            "lint_output": None,
            "typecheck_output": None,
            "test_output": None,
        }

    # Check validation result
    validation_passed = validation_result.get("valid", False)

    if validation_passed:
        return {
            "proceed": True,
            "patches_to_apply": patches,
            "status": "success",
            "summary": validation_result.get("summary", "Validation passed"),
            "errors": None,
            "lint_output": None,
            "typecheck_output": None,
            "test_output": None,
        }

    # Validation failed - collect detailed error info
    errors = validation_result.get("errors") or []
    
    lint_result = validation_result.get("lint_result") or {}
    typecheck_result = validation_result.get("typecheck_result") or {}
    test_result = validation_result.get("test_result") or {}

    return {
        "proceed": False,
        "patches_to_apply": None,
        "status": "validation_failed",
        "summary": validation_result.get("summary", "Validation failed"),
        "errors": errors,
        "lint_output": lint_result.get("output") if not lint_result.get("passed") else None,
        "typecheck_output": typecheck_result.get("output") if not typecheck_result.get("passed") else None,
        "test_output": test_result.get("output") if not test_result.get("passed") else None,
    }
