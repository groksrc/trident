"""Agent node execution via Claude CLI.

This module provides an alternative to the Claude Agent SDK by using the
Claude CLI (`claude -p`) for agent execution. This uses your existing
Claude subscription instead of API tokens, reducing operational costs.

Known limitations:
- MCP servers use global ~/.claude/settings.json config, not per-agent
- No streaming access to intermediate tool uses/results
- Session resumption is more basic than SDK

Usage in manifest:
    nodes:
      my_agent:
        type: agent
        execution_mode: cli  # Use CLI instead of SDK
        prompt: prompts/my_agent.prompt
        allowed_tools:
          - Read
          - Edit
          - Bash
"""

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any

from .errors import TridentError
from .parser import AgentNode
from .template import render


@dataclass
class CLIAgentResult:
    """Result from CLI-based agent execution.

    Compatible with the SDK's AgentResult for seamless switching.

    Attributes:
        output: The parsed output from the agent
        session_id: Session ID for resuming later (if available)
        num_turns: Number of turns (not available in CLI mode, always 0)
        cost_usd: Total cost in USD (from CLI JSON output)
        tokens: Token usage dictionary with input/output counts
    """

    output: dict[str, Any]
    session_id: str | None = None
    num_turns: int = 0
    cost_usd: float | None = None
    tokens: dict[str, int] = field(default_factory=dict)


class CLIAgentError(TridentError):
    """Error during CLI-based agent execution."""

    pass


def _build_json_schema(output_schema) -> dict[str, Any]:
    """Build JSON Schema for Claude CLI --json-schema flag.

    Args:
        output_schema: OutputSchema from prompt frontmatter

    Returns:
        JSON Schema dict for structured output
    """
    # Build properties dict from output fields
    properties = {}
    required = []

    if output_schema.fields:
        # Use defined fields
        for field_name, (field_type, field_desc) in output_schema.fields.items():
            # Map Trident types to JSON Schema types
            type_map = {
                "str": "string",
                "string": "string",
                "int": "integer",
                "integer": "integer",
                "float": "number",
                "number": "number",
                "bool": "boolean",
                "boolean": "boolean",
                "list": "array",
                "array": "array",
                "dict": "object",
                "object": "object",
            }
            json_type = type_map.get(field_type.lower(), "string")

            properties[field_name] = {
                "type": json_type,
                "description": field_desc,
            }
            required.append(field_name)
    else:
        # No fields defined - create permissive schema that accepts any object
        # This allows the agent to structure its own output
        return {
            "type": "object",
            "description": "JSON response from agent",
        }

    schema = {
        "type": "object",
        "properties": properties,
        "required": required,
    }

    return schema


def _build_mcp_config(mcp_servers: dict) -> dict[str, Any]:
    """Build MCP config dict for Claude CLI --mcp-config flag.

    Args:
        mcp_servers: Dict of server name to MCPServerConfig objects

    Returns:
        Dict in the format expected by Claude CLI's --mcp-config
    """
    config: dict[str, Any] = {"mcpServers": {}}

    for server_name, server_config in mcp_servers.items():
        # Expand environment variables in server env
        server_env = {}
        for key, value in server_config.env.items():
            if value.startswith("${") and value.endswith("}"):
                env_var = value[2:-1]
                server_env[key] = os.environ.get(env_var, "")
            else:
                server_env[key] = value

        server_dict: dict[str, Any] = {
            "command": server_config.command,
            "args": server_config.args,
        }
        if server_env:
            server_dict["env"] = server_env

        config["mcpServers"][server_name] = server_dict

    return config


def check_cli_available() -> str:
    """Check if Claude CLI is available and return the path.

    Returns:
        Path to the claude CLI executable

    Raises:
        CLIAgentError: If CLI is not installed or not in PATH
    """
    claude_path = shutil.which("claude")
    if not claude_path:
        raise CLIAgentError(
            "Claude CLI not found. Install with: npm install -g @anthropic-ai/claude-code\n"
            "Or use execution_mode: sdk in your manifest to use the Agent SDK instead."
        )
    return claude_path


def execute_agent_via_cli(
    agent_node: AgentNode,
    inputs: dict[str, Any],
    project_root: str,
    resume_session: str | None = None,
) -> CLIAgentResult:
    """Execute an agent node using the Claude CLI.

    This provides a cost-effective alternative to the Agent SDK by using
    your existing Claude subscription via the CLI.

    Args:
        agent_node: The agent node configuration
        inputs: Input data from upstream nodes
        project_root: Project root directory
        resume_session: Optional session ID to resume (from previous run)

    Returns:
        CLIAgentResult with output and usage metrics

    Raises:
        CLIAgentError: If CLI execution fails
    """
    claude_path = check_cli_available()

    # Get the prompt template body
    if not agent_node.prompt_node:
        raise CLIAgentError(f"Agent {agent_node.id} has no prompt loaded")

    # Render the prompt with inputs
    rendered_prompt = render(agent_node.prompt_node.body, inputs)

    # Build CLI command
    cmd = [
        claude_path,
        "-p",  # Print mode (non-interactive)
        rendered_prompt,
        "--output-format",
        "json",
    ]

    # Add JSON schema for structured outputs
    output_schema = agent_node.prompt_node.output
    if output_schema.format == "json":
        json_schema = _build_json_schema(output_schema)
        import sys
        print(f"DEBUG: Generated JSON schema for {agent_node.id}: {json.dumps(json_schema)}", file=sys.stderr)
        cmd.extend(["--json-schema", json.dumps(json_schema)])

    # Add max turns limit
    if agent_node.max_turns:
        cmd.extend(["--max-turns", str(agent_node.max_turns)])

    # Add permission mode
    if agent_node.permission_mode:
        # Map Trident permission modes to CLI modes
        # SDK modes: "acceptEdits", "bypassPermissions", "default"
        # CLI modes: "default", "plan", "bypassPermissions"
        mode_map = {
            "acceptEdits": "default",  # Accept file edits
            "bypassPermissions": "bypassPermissions",
            "default": "default",
            "plan": "plan",
        }
        cli_mode = mode_map.get(agent_node.permission_mode, "default")
        cmd.extend(["--permission-mode", cli_mode])

    # Add allowed tools
    if agent_node.allowed_tools:
        # CLI uses comma-separated tool names
        tools_str = ",".join(agent_node.allowed_tools)
        cmd.extend(["--allowedTools", tools_str])

    # Add session resume if provided
    if resume_session:
        cmd.extend(["--resume", resume_session])

    # Determine working directory
    cwd = agent_node.cwd or project_root

    # Add MCP servers via --mcp-config flag
    if agent_node.mcp_servers:
        mcp_config = _build_mcp_config(agent_node.mcp_servers)
        if mcp_config:
            cmd.extend(["--mcp-config", json.dumps(mcp_config)])

    # Build environment without ANTHROPIC_API_KEY so CLI uses subscription auth
    # instead of pay-per-token API mode
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}

    # Debug: print command being run
    import sys

    print(f"DEBUG: Running CLI command in cwd={cwd}", file=sys.stderr)
    print(
        f"DEBUG: Command: {' '.join(cmd[:5])}... (prompt length: {len(cmd[2]) if len(cmd) > 2 else 0})",
        file=sys.stderr,
    )

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=1200,  # 20 minute timeout for complex tasks
            env=env,
        )
    except subprocess.TimeoutExpired as e:
        raise CLIAgentError(f"Agent '{agent_node.id}' timed out after 10 minutes") from e
    except Exception as e:
        raise CLIAgentError(f"Failed to execute Claude CLI: {e}") from e

    # Debug: print full CLI output
    import sys
    print(f"DEBUG CLI stdout length: {len(result.stdout)}", file=sys.stderr)
    print(f"DEBUG CLI stderr: {result.stderr[:500] if result.stderr else 'empty'}", file=sys.stderr)
    print(f"DEBUG CLI stdout: {result.stdout[:1000]}", file=sys.stderr)

    # Check for CLI errors
    if result.returncode != 0:
        error_msg = result.stderr.strip() if result.stderr else "Unknown error"
        raise CLIAgentError(
            f"Agent '{agent_node.id}' CLI execution failed (exit {result.returncode}): {error_msg}"
        )

    # Parse JSON output
    try:
        cli_output = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise CLIAgentError(
            f"Agent '{agent_node.id}' returned invalid JSON. "
            f"Output preview: {result.stdout[:500]!r}"
        ) from e

    # Debug: print CLI output
    print(
        f"DEBUG CLI output for {agent_node.id}: is_error={cli_output.get('is_error')}, result_len={len(cli_output.get('result', ''))}",
        file=sys.stderr,
    )
    if cli_output.get("is_error"):
        print(f"DEBUG CLI error result: {cli_output.get('result', '')[:500]}", file=sys.stderr)

    # Check for CLI-level errors
    if cli_output.get("is_error"):
        error_result = cli_output.get("result", "Unknown CLI error")
        raise CLIAgentError(f"Agent '{agent_node.id}' CLI reported error: {error_result}")

    # Extract result from CLI output format
    # CLI JSON format: {result: string, session_id: string, usage: {...}, total_cost_usd: float}
    # When using --json-schema: {result: "", structured_output: {...}, ...}

    # Build tokens dict from usage
    tokens: dict[str, int] = {}
    if "usage" in cli_output:
        usage = cli_output["usage"]
        if isinstance(usage, dict):
            # CLI uses input_tokens/output_tokens naming
            if "input_tokens" in usage:
                tokens["input"] = usage["input_tokens"]
            elif "input" in usage:
                tokens["input"] = usage["input"]
            if "output_tokens" in usage:
                tokens["output"] = usage["output_tokens"]
            elif "output" in usage:
                tokens["output"] = usage["output"]

    # Parse output based on expected format
    output_schema = agent_node.prompt_node.output
    if output_schema.format == "json":
        # Check for structured_output field (when using --json-schema)
        if "structured_output" in cli_output:
            output = cli_output["structured_output"]
        else:
            # Fallback to parsing result field (old behavior)
            response_text = cli_output.get("result", "")
            try:
                parsed = _parse_json_response(response_text)
            except json.JSONDecodeError as e:
                raise CLIAgentError(
                    f"Agent '{agent_node.id}' returned invalid JSON in response. "
                    f"Response preview: {response_text[:200]!r}"
                ) from e
            output = parsed
    else:
        response_text = cli_output.get("result", "")
        output = {"text": response_text}

    return CLIAgentResult(
        output=output,
        session_id=cli_output.get("session_id"),
        num_turns=cli_output.get("num_turns", 0),
        cost_usd=cli_output.get("total_cost_usd"),
        tokens=tokens,
    )


def _parse_json_response(text: str) -> dict[str, Any]:
    """Parse JSON from agent response, handling markdown code blocks.

    This mirrors the logic in agents.py for consistency.

    Args:
        text: Response text that may contain JSON

    Returns:
        Parsed JSON as dictionary

    Raises:
        json.JSONDecodeError: If no valid JSON found
    """
    text = text.strip()

    # Try direct parse first
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
        return {"result": parsed}
    except json.JSONDecodeError:
        pass

    # Try to extract from ```json code block
    if "```json" in text:
        start = text.find("```json") + 7
        end = text.find("```", start)
        if end > start:
            try:
                parsed = json.loads(text[start:end].strip())
                if isinstance(parsed, dict):
                    return parsed
                return {"result": parsed}
            except json.JSONDecodeError:
                pass

    # Try to extract from plain ``` code block
    if "```" in text:
        start = text.find("```") + 3
        newline = text.find("\n", start)
        if newline > start and newline - start < 20:
            start = newline + 1
        end = text.find("```", start)
        if end > start:
            try:
                parsed = json.loads(text[start:end].strip())
                if isinstance(parsed, dict):
                    return parsed
                return {"result": parsed}
            except json.JSONDecodeError:
                pass

    # Try to find JSON object embedded in prose
    brace_start = text.find("{")
    if brace_start >= 0:
        depth = 0
        in_string = False
        escape_next = False
        for i, char in enumerate(text[brace_start:], brace_start):
            if escape_next:
                escape_next = False
                continue
            if char == "\\":
                escape_next = True
                continue
            if char == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    try:
                        parsed = json.loads(text[brace_start : i + 1])
                        if isinstance(parsed, dict):
                            return parsed
                        return {"result": parsed}
                    except json.JSONDecodeError:
                        pass
                    break

    raise json.JSONDecodeError(
        "No valid JSON found in response. Expected raw JSON or markdown code block.",
        text,
        0,
    )
