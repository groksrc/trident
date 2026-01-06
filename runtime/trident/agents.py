"""Agent node execution via Claude Agent SDK (SPEC-3).

This module provides async execution of agent nodes using the Claude Agent SDK.
Agents have access to tools and MCP servers for autonomous multi-turn execution.

Requires: pip install trident[agents]
"""

import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .errors import TridentError
from .parser import AgentNode
from .template import render

# Type alias for message callbacks
# Callback receives: (message_type: str, content: Any) -> None
MessageCallback = Callable[[str, Any], None]

# Check for SDK availability
try:
    import anyio
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        ResultMessage,
        TextBlock,
        ToolResultBlock,
        ToolUseBlock,
        query,
    )

    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False


@dataclass
class AgentResult:
    """Result from agent execution with usage metrics.

    Attributes:
        output: The parsed output from the agent
        session_id: Session ID for resuming later
        num_turns: Number of turns in the agent execution
        cost_usd: Total cost in USD (None if not available)
        tokens: Token usage dictionary with input/output counts
    """

    output: dict[str, Any]
    session_id: str | None = None
    num_turns: int = 0
    cost_usd: float | None = None
    tokens: dict[str, int] = field(default_factory=dict)


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
    resume_session: str | None = None,
    on_message: MessageCallback | None = None,
) -> AgentResult:
    """Execute an agent node asynchronously.

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

    # Build output format for structured outputs (if JSON schema defined)
    output_format: dict[str, Any] | None = None
    output_schema = agent_node.prompt_node.output
    if output_schema.format == "json" and output_schema.fields:
        json_schema = _build_json_schema(output_schema.fields)
        output_format = {
            "type": "json_schema",
            "schema": json_schema,
        }

    # Build SDK options
    options = ClaudeAgentOptions(
        allowed_tools=agent_node.allowed_tools or [],
        mcp_servers=mcp_servers if mcp_servers else {},
        cwd=cwd,
        max_turns=agent_node.max_turns,
        permission_mode=agent_node.permission_mode,  # type: ignore[arg-type]
        resume=resume_session,
        output_format=output_format,  # type: ignore[arg-type]
    )

    # Execute agent and collect response
    # We keep the last AssistantMessage's text content (the final response)
    last_assistant_text = ""
    result_message: ResultMessage | None = None
    try:
        async for message in query(prompt=rendered_prompt, options=options):
            if isinstance(message, AssistantMessage):
                # Collect all text blocks from this message
                message_text_parts: list[str] = []
                tool_uses: list[dict[str, Any]] = []
                tool_results: list[dict[str, Any]] = []
                for block in message.content:  # type: ignore[union-attr]
                    if isinstance(block, TextBlock):
                        message_text_parts.append(block.text)  # type: ignore[union-attr]
                    elif isinstance(block, ToolUseBlock):
                        tool_uses.append(
                            {"name": block.name, "input": block.input}  # type: ignore[union-attr]
                        )
                    elif isinstance(block, ToolResultBlock):
                        tool_results.append(
                            {
                                "tool_use_id": block.tool_use_id,  # type: ignore[union-attr]
                                "content": block.content,  # type: ignore[union-attr]
                            }
                        )

                if message_text_parts:
                    last_assistant_text = "\n".join(message_text_parts)
                    if on_message:
                        on_message("assistant", last_assistant_text)

                # Call callback for tool uses
                if on_message and tool_uses:
                    for tool_use in tool_uses:
                        on_message("tool_use", tool_use)

                # Call callback for tool results
                if on_message and tool_results:
                    for tool_result in tool_results:
                        on_message("tool_result", tool_result)

            elif isinstance(message, ResultMessage):
                result_message = message
                if on_message:
                    on_message(
                        "result",
                        {
                            "num_turns": message.num_turns,  # type: ignore[union-attr]
                            "cost_usd": message.total_cost_usd,  # type: ignore[union-attr]
                        },
                    )
    except Exception as e:
        raise AgentExecutionError(
            f"Agent '{agent_node.id}' execution failed: {e}"
        ) from e

    # Check for structured output first (API-level validation)
    structured_output: dict[str, Any] | None = None
    if result_message and hasattr(result_message, "structured_output"):
        structured_output = result_message.structured_output  # type: ignore[union-attr]

    # Handle structured output errors
    if (
        result_message
        and hasattr(result_message, "subtype")
        and result_message.subtype == "error_max_structured_output_retries"  # type: ignore[union-attr]
    ):
        raise AgentExecutionError(
            f"Agent '{agent_node.id}' could not produce valid structured output "
            f"matching the schema after multiple retries"
        )

    # Use structured output if available (preferred - API validated)
    if structured_output is not None:
        output = structured_output
    else:
        # Fallback to text parsing (for backwards compatibility or text output)
        if not last_assistant_text.strip():
            raise AgentExecutionError(
                f"Agent '{agent_node.id}' returned empty response"
            )

        response_text = last_assistant_text

        # Parse output based on expected format
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

            output = parsed
        else:
            output = {"text": response_text}

    # Build result with usage metrics
    tokens: dict[str, int] = {}
    if result_message and result_message.usage:
        usage = result_message.usage
        if "input" in usage:
            tokens["input"] = usage["input"]
        if "output" in usage:
            tokens["output"] = usage["output"]

    return AgentResult(
        output=output,
        session_id=result_message.session_id if result_message else None,
        num_turns=result_message.num_turns if result_message else 0,
        cost_usd=result_message.total_cost_usd if result_message else None,
        tokens=tokens,
    )


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

    # Try to find JSON object embedded in prose (e.g., "Here's the output: {...}")
    brace_start = text.find("{")
    if brace_start >= 0:
        # Find matching closing brace
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
    check_sdk_available()
    return anyio.run(
        execute_agent_async, agent_node, inputs, project_root, resume_session, on_message
    )
