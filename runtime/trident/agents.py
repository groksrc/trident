"""Agent node execution (backward-compatible facade).

This module provides backward-compatible functions for executing agent nodes.
It delegates to the agent_providers package for actual execution.

For new code, prefer using the agent_providers module directly:

    from trident.agent_providers import get_registry, AgentConfig

    registry = get_registry()
    provider = registry.get("claude")
    result = await provider.execute(prompt, config)

Requires: pip install trident[agents]
"""

import os
from collections.abc import Callable
from typing import Any

from .errors import TridentError
from .parser import AgentNode
from .template import render

# Re-export AgentResult from agent_providers for backward compatibility
from .agent_providers import (
    AgentConfig,
    AgentMessage,
    AgentResult,
    AgentProviderError,
    get_registry,
)

# Type alias for legacy message callbacks
# Legacy callback receives: (message_type: str, content: Any) -> None
MessageCallback = Callable[[str, Any], None]


class AgentExecutionError(TridentError):
    """Error during agent execution.

    This error is raised for backward compatibility.
    New code should catch AgentProviderError instead.
    """

    pass


def check_sdk_available() -> None:
    """Check if an agent SDK is available.

    Raises:
        TridentError: If no agent SDK is installed
    """
    registry = get_registry()
    available = registry.list_available()
    if not available:
        raise TridentError(
            "No agent SDK installed. "
            "Install with: pip install trident[agents-claude]"
        )


async def execute_agent_async(
    agent_node: AgentNode,
    inputs: dict[str, Any],
    project_root: str,
    resume_session: str | None = None,
    on_message: MessageCallback | None = None,
) -> AgentResult:
    """Execute an agent node asynchronously.

    This function provides backward compatibility. It delegates to
    the appropriate provider based on agent_node.provider.

    Args:
        agent_node: The agent node configuration
        inputs: Input data from upstream nodes
        project_root: Project root directory
        resume_session: Optional session ID to resume
        on_message: Optional callback for logging/validation.
            Called with (message_type, content) for each SDK message.
            Types: "assistant", "tool_use", "tool_result", "result"

    Returns:
        AgentResult with output and usage metrics

    Raises:
        AgentExecutionError: If agent execution fails
    """
    # Get the prompt template body
    if not agent_node.prompt_node:
        raise AgentExecutionError(f"Agent {agent_node.id} has no prompt loaded")

    # Render the prompt with inputs
    rendered_prompt = render(agent_node.prompt_node.body, inputs)

    # Determine working directory
    cwd = agent_node.cwd
    if not cwd:
        cwd = os.environ.get("TRIDENT_WORKSPACE", project_root)

    # Build output format for structured outputs (if JSON schema defined)
    output_format: dict[str, Any] | None = None
    output_schema = agent_node.prompt_node.output
    if output_schema.format == "json" and output_schema.fields:
        json_schema = _build_json_schema(output_schema.fields)
        output_format = {
            "type": "json_schema",
            "schema": json_schema,
        }

    # Build provider options
    # Include MCP servers and permission_mode for Claude compatibility
    provider_options: dict[str, Any] = {}

    # Handle permission_mode (Claude-specific)
    if hasattr(agent_node, "permission_mode") and agent_node.permission_mode:
        provider_options["permission_mode"] = agent_node.permission_mode

    # Handle provider_options from agent_node if available
    if hasattr(agent_node, "provider_options") and agent_node.provider_options:
        provider_options.update(agent_node.provider_options)

    # Handle MCP servers
    if agent_node.mcp_servers:
        # Convert MCPServerConfig objects to dicts
        mcp_servers_dict = {}
        for server_name, server_config in agent_node.mcp_servers.items():
            mcp_servers_dict[server_name] = {
                "command": server_config.command,
                "args": server_config.args,
                "env": server_config.env,
            }
        provider_options["mcp_servers"] = mcp_servers_dict

    # Build agent config
    config = AgentConfig(
        max_turns=agent_node.max_turns,
        cwd=cwd,
        allowed_tools=agent_node.allowed_tools or [],
        output_format=output_format,
        resume_session=resume_session,
        model=getattr(agent_node, "model", None),
        provider_options=provider_options,
    )

    # Get provider
    provider_name = getattr(agent_node, "provider", None) or "claude"
    registry = get_registry()
    provider = registry.get(provider_name)

    if not provider:
        available = registry.list_registered()
        raise AgentExecutionError(
            f"Unknown agent provider '{provider_name}'. "
            f"Available providers: {', '.join(available) or 'none'}"
        )

    if not provider.available:
        raise AgentExecutionError(
            f"Agent provider '{provider_name}' not installed. "
            f"Install with: pip install trident[agents-{provider_name}]"
        )

    # Adapt message callback to new format
    adapted_callback = None
    if on_message:

        def adapted_callback(msg: AgentMessage) -> None:
            on_message(msg.type, msg.content)

    # Execute via provider
    try:
        result = await provider.execute(
            prompt=rendered_prompt,
            config=config,
            on_message=adapted_callback,
        )
    except AgentProviderError as e:
        raise AgentExecutionError(
            f"Agent '{agent_node.id}' execution failed: {e}"
        ) from e

    return result


def execute_agent(
    agent_node: AgentNode,
    inputs: dict[str, Any],
    project_root: str,
    resume_session: str | None = None,
    on_message: MessageCallback | None = None,
) -> AgentResult:
    """Execute an agent node synchronously (wrapper for async).

    Args:
        agent_node: The agent node configuration
        inputs: Input data from upstream nodes
        project_root: Project root directory
        resume_session: Optional session ID to resume
        on_message: Optional callback for logging/validation

    Returns:
        AgentResult with output and usage metrics
    """
    import anyio

    return anyio.run(
        execute_agent_async, agent_node, inputs, project_root, resume_session, on_message
    )


def _build_json_schema(fields: dict[str, tuple[str, str]]) -> dict[str, Any]:
    """Build JSON Schema from output field definitions.

    Args:
        fields: Dictionary of {field_name: (type, description)}

    Returns:
        JSON Schema dictionary suitable for structured outputs
    """
    type_mapping = {
        "string": {"type": "string"},
        "number": {"type": "number"},
        "integer": {"type": "integer"},
        "boolean": {"type": "boolean"},
        "array": {"type": "array"},
        "object": {"type": "object"},
    }

    properties: dict[str, Any] = {}
    for field_name, (field_type, description) in fields.items():
        prop = type_mapping.get(field_type, {"type": "string"}).copy()
        if description:
            prop["description"] = description
        properties[field_name] = prop

    return {
        "type": "object",
        "properties": properties,
        "required": list(fields.keys()),
        "additionalProperties": False,
    }


def _parse_json_response(text: str) -> dict[str, Any]:
    """Parse JSON from agent response text.

    Handles:
    - Direct JSON strings
    - JSON in ```json code blocks
    - JSON in plain ``` code blocks
    - Top-level arrays (wrapped in {"result": [...]})

    Args:
        text: The response text to parse

    Returns:
        Parsed JSON as dictionary

    Raises:
        json.JSONDecodeError: If no valid JSON found
    """
    import json
    import re

    # Try extracting from code blocks first
    code_block_pattern = r"```(?:json|javascript|js)?\s*\n?(.*?)\n?```"
    match = re.search(code_block_pattern, text, re.DOTALL)

    if match:
        json_str = match.group(1).strip()
    else:
        # Try the whole text as JSON
        json_str = text.strip()

    # Parse the JSON
    result = json.loads(json_str)

    # Wrap arrays in a dict
    if isinstance(result, list):
        return {"result": result}

    return result


def _validate_agent_output(
    output: dict[str, Any],
    schema: dict[str, tuple[str, str]],
    agent_id: str,
) -> None:
    """Validate agent output against schema.

    Args:
        output: The agent output dictionary
        schema: Schema mapping {field_name: (type, description)}
        agent_id: Agent ID for error messages

    Raises:
        AgentExecutionError: If validation fails
    """
    type_mapping = {
        "string": str,
        "number": (int, float),
        "integer": int,
        "boolean": bool,
        "array": list,
        "object": dict,
    }

    for field_name, (field_type, _desc) in schema.items():
        if field_name not in output:
            raise AgentExecutionError(
                f"Agent '{agent_id}' output missing required field: {field_name}"
            )

        value = output[field_name]
        expected = type_mapping.get(field_type)

        if expected and not isinstance(value, expected):
            raise AgentExecutionError(
                f"Agent '{agent_id}' output field '{field_name}' "
                f"expected {field_type}, got {type(value).__name__}"
            )
