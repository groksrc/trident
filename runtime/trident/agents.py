"""Agent node execution via Claude Agent SDK (SPEC-3).

This module provides async execution of agent nodes using the Claude Agent SDK.
Agents have access to tools and MCP servers for autonomous multi-turn execution.

Requires: pip install trident[agents]
"""

import json
import os
from typing import Any

from .errors import TridentError
from .parser import AgentNode
from .template import render

# Check for SDK availability
try:
    import anyio
    from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, TextBlock, query

    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False


class AgentExecutionError(TridentError):
    """Error during agent execution."""

    pass


def check_sdk_available() -> None:
    """Check if Claude Agent SDK is available.

    Raises:
        TridentError: If SDK is not installed
    """
    if not SDK_AVAILABLE:
        raise TridentError(
            "Claude Agent SDK not installed. "
            "Install with: pip install trident[agents]"
        )


async def execute_agent_async(
    agent_node: AgentNode,
    inputs: dict[str, Any],
    project_root: str,
) -> dict[str, Any]:
    """Execute an agent node asynchronously.

    Args:
        agent_node: The agent node configuration
        inputs: Input data from upstream nodes
        project_root: Project root directory

    Returns:
        Agent output as dictionary

    Raises:
        AgentExecutionError: If agent execution fails
    """
    check_sdk_available()

    # Get the prompt template body
    if not agent_node.prompt_node:
        raise AgentExecutionError(f"Agent {agent_node.id} has no prompt loaded")

    # Render the prompt with inputs
    rendered_prompt = render(agent_node.prompt_node.body, inputs)

    # Build MCP server config for SDK
    mcp_servers: dict[str, Any] = {}
    for server_name, server_config in agent_node.mcp_servers.items():
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
        mcp_servers[server_name] = server_dict

    # Determine working directory
    cwd = agent_node.cwd
    if not cwd:
        cwd = os.environ.get("TRIDENT_WORKSPACE", project_root)

    # Build SDK options
    options = ClaudeAgentOptions(
        allowed_tools=agent_node.allowed_tools or None,
        mcp_servers=mcp_servers if mcp_servers else None,
        cwd=cwd,
        max_turns=agent_node.max_turns,
        permission_mode=agent_node.permission_mode,
    )

    # Execute agent and collect response
    # We keep the last AssistantMessage's text content (the final response)
    last_assistant_text = ""
    try:
        async for message in query(prompt=rendered_prompt, options=options):
            if isinstance(message, AssistantMessage):
                # Collect all text blocks from this message
                message_text_parts = []
                for block in message.content:
                    if isinstance(block, TextBlock):
                        message_text_parts.append(block.text)
                if message_text_parts:
                    last_assistant_text = "\n".join(message_text_parts)
    except Exception as e:
        raise AgentExecutionError(
            f"Agent '{agent_node.id}' execution failed: {e}"
        ) from e

    # Handle empty response
    if not last_assistant_text.strip():
        raise AgentExecutionError(
            f"Agent '{agent_node.id}' returned empty response"
        )

    response_text = last_assistant_text

    # Parse output based on expected format
    output_schema = agent_node.prompt_node.output
    if output_schema.format == "json":
        try:
            parsed = _parse_json_response(response_text)
        except json.JSONDecodeError as e:
            raise AgentExecutionError(
                f"Agent '{agent_node.id}' returned invalid JSON. "
                f"Response preview: {response_text[:200]!r}"
            ) from e

        # Validate against schema if defined
        if output_schema.fields:
            _validate_agent_output(parsed, output_schema.fields, agent_node.id)

        return parsed
    else:
        return {"text": response_text}


def _validate_agent_output(
    data: dict[str, Any],
    schema: dict[str, tuple[str, str]],
    agent_id: str,
) -> None:
    """Validate agent output against expected schema.

    Args:
        data: Parsed output data
        schema: Expected fields as {name: (type, description)}
        agent_id: Agent ID for error messages

    Raises:
        AgentExecutionError: If validation fails
    """
    for field_name, (field_type, _desc) in schema.items():
        if field_name not in data:
            raise AgentExecutionError(
                f"Agent '{agent_id}' output missing required field: '{field_name}'"
            )

        value = data[field_name]
        expected_types = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        expected = expected_types.get(field_type)
        if expected and not isinstance(value, expected):
            raise AgentExecutionError(
                f"Agent '{agent_id}' output field '{field_name}' "
                f"expected {field_type}, got {type(value).__name__}"
            )


def _parse_json_response(text: str) -> dict[str, Any]:
    """Parse JSON from agent response, handling markdown code blocks.

    Attempts to extract JSON in order of preference:
    1. Direct JSON parse (response is pure JSON)
    2. ```json code block
    3. ``` code block (assumes JSON content)

    Args:
        text: Response text that may contain JSON

    Returns:
        Parsed JSON as dictionary

    Raises:
        json.JSONDecodeError: If no valid JSON found
    """
    text = text.strip()

    # Try direct parse first (cleanest case)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
        # Handle array or primitive - wrap in dict
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
                pass  # Fall through to next attempt

    # Try to extract from plain ``` code block
    if "```" in text:
        start = text.find("```") + 3
        # Skip language identifier if present (e.g., ```javascript)
        newline = text.find("\n", start)
        if newline > start and newline - start < 20:  # Reasonable language id length
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

    raise json.JSONDecodeError(
        "No valid JSON found in response. Expected raw JSON or markdown code block.",
        text,
        0,
    )


def execute_agent(
    agent_node: AgentNode,
    inputs: dict[str, Any],
    project_root: str,
) -> dict[str, Any]:
    """Execute an agent node synchronously (wrapper for async).

    Args:
        agent_node: The agent node configuration
        inputs: Input data from upstream nodes
        project_root: Project root directory

    Returns:
        Agent output as dictionary
    """
    check_sdk_available()
    return anyio.run(execute_agent_async, agent_node, inputs, project_root)
