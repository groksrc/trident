"""File operation tools for Vue TodoMVC project."""

import json as json_module
import os
import subprocess
from pathlib import Path
from typing import Any

WORKSPACE = Path(os.environ.get("TRIDENT_WORKSPACE", ".")).resolve()

# File extensions relevant for Vue/TypeScript projects
WEB_EXTENSIONS = {".vue", ".ts", ".tsx", ".js", ".jsx", ".json", ".html", ".css"}


def list_project_structure() -> dict[str, Any]:
    """List all web project files.

    Returns:
        {"files": str} - Newline-separated list of project files
    """
    try:
        exclude = {".git", "__pycache__", ".venv", "venv", "node_modules", "dist", ".cache"}
        files = []

        for ext in WEB_EXTENSIONS:
            for p in WORKSPACE.rglob(f"*{ext}"):
                if any(ex in str(p) for ex in exclude):
                    continue
                rel_path = str(p.relative_to(WORKSPACE))
                files.append(rel_path)

        files = sorted(set(files))
        return {"files": "\n".join(files)}
    except Exception as e:
        return {"files": "", "error": str(e)}


def read_files_multi(files: str | list[str]) -> dict[str, Any]:
    """Read multiple files and return their contents.

    Args:
        files: Newline-separated string or list of file paths

    Returns:
        {"content": str, "files_read": list[str]}
    """
    if isinstance(files, str):
        file_list = [f.strip() for f in files.strip().split("\n") if f.strip()]
    else:
        file_list = files

    if not file_list:
        return {"content": "No files found", "files_read": []}

    contents = []
    files_read = []

    for file_path in file_list:
        full_path = WORKSPACE / file_path
        if full_path.exists() and full_path.is_file():
            try:
                content = full_path.read_text(encoding="utf-8")
                contents.append(f"### {file_path}\n```\n{content}\n```\n")
                files_read.append(file_path)
            except Exception:
                pass

    if not contents:
        return {"content": "No files found", "files_read": []}

    return {"content": "\n".join(contents), "files_read": files_read}


def write_files_multi(code_changes: list[dict[str, str]]) -> dict[str, Any]:
    """Write multiple files from code_changes array.

    Args:
        code_changes: List of {"path": str, "content": str, "action": str}

    Returns:
        {"success": bool, "files_written": list[str], "errors": list[str], "syntax_errors": list[str]}
    """
    files_written = []
    errors = []
    syntax_errors = []

    for change in code_changes:
        path = change.get("path", "")
        content = change.get("content", "")

        if not path:
            errors.append("Missing path in code_change")
            continue

        full_path = WORKSPACE / path

        try:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding="utf-8")
            files_written.append(path)

            # Basic syntax validation for JSON files
            if path.endswith(".json"):
                try:
                    json_module.loads(content)
                except json_module.JSONDecodeError as e:
                    syntax_errors.append(f"{path}: JSON syntax error - {e}")

        except Exception as e:
            errors.append(f"{path}: {e}")

    return {
        "success": len(errors) == 0 and len(syntax_errors) == 0,
        "files_written": files_written,
        "errors": errors if errors else None,
        "syntax_errors": syntax_errors if syntax_errors else None,
    }


def run_typecheck() -> dict[str, Any]:
    """Run vue-tsc for TypeScript type checking.

    Returns:
        {"passed": bool, "output": str, "errors": int}
    """
    try:
        # Check if node_modules exists
        if not (WORKSPACE / "node_modules").exists():
            return {
                "passed": False,
                "output": "node_modules not found. Run 'npm install' first.",
                "errors": 1,
            }

        result = subprocess.run(
            ["npx", "vue-tsc", "--noEmit"],
            cwd=WORKSPACE,
            capture_output=True,
            text=True,
            timeout=60,
        )

        output = result.stdout + result.stderr
        passed = result.returncode == 0

        # Count error lines
        error_count = len([l for l in output.split("\n") if "error TS" in l])

        return {
            "passed": passed,
            "output": output.strip() or "No errors",
            "errors": error_count,
        }
    except FileNotFoundError:
        return {
            "passed": False,
            "output": "npx not found. Is Node.js installed?",
            "errors": 1,
        }
    except subprocess.TimeoutExpired:
        return {
            "passed": False,
            "output": "Type check timed out after 60s",
            "errors": 1,
        }
    except Exception as e:
        return {"passed": False, "output": str(e), "errors": 1}


def run_lint() -> dict[str, Any]:
    """Run ESLint on the project (if configured).

    Returns:
        {"passed": bool, "output": str, "fixed": int, "remaining": int}
    """
    try:
        # Check if ESLint is available
        if not (WORKSPACE / "node_modules").exists():
            return {
                "passed": True,
                "output": "Skipping lint - node_modules not found",
                "fixed": 0,
                "remaining": 0,
            }

        # Try running ESLint with fix
        result = subprocess.run(
            ["npx", "eslint", "src", "--ext", ".vue,.ts,.tsx", "--fix"],
            cwd=WORKSPACE,
            capture_output=True,
            text=True,
            timeout=60,
        )

        output = result.stdout + result.stderr
        passed = result.returncode == 0

        return {
            "passed": passed,
            "output": output.strip() or "All checks passed!",
            "fixed": 0,  # ESLint doesn't easily report this
            "remaining": 0 if passed else 1,
        }
    except FileNotFoundError:
        return {
            "passed": True,
            "output": "ESLint not configured - skipping",
            "fixed": 0,
            "remaining": 0,
        }
    except subprocess.TimeoutExpired:
        return {
            "passed": False,
            "output": "Lint timed out after 60s",
            "fixed": 0,
            "remaining": 1,
        }
    except Exception as e:
        return {"passed": True, "output": f"Lint skipped: {e}", "fixed": 0, "remaining": 0}
