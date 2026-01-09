"""Claude Agent SDK provider implementation.

This module implements the AgentProvider protocol for Claude Agent SDK,
enabling multi-turn agent execution with tool access and MCP servers.

Requires: pip install trident[agents-claude]
"""

import json
import logging
import os
from typing import Any

from .base import (
    AgentConfig,
    AgentMessage,
    AgentNotInstalledError,
    AgentOutputError,
    AgentProvider,
    AgentProviderError,
    AgentResult,
    MessageCallback,
)

logger = logging.getLogger(__name__)

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

    _SDK_AVAILABLE = True
except ImportError:
    _SDK_AVAILABLE = False
    # Define placeholders for type hints
    AssistantMessage = None  # type: ignore
    ClaudeAgentOptions = None  # type: ignore
    ResultMessage = None  # type: ignore
    TextBlock = None  # type: ignore
    ToolResultBlock = None  # type: ignore
    ToolUseBlock = None  # type: ignore
    query = None  # type: ignore
    anyio = None  # type: ignore


class ClaudeAgentProvider(AgentProvider):
    """Agent provider using Claude Agent SDK.

    This provider executes agents via the Claude Agent SDK, supporting:
    - Multi-turn autonomous execution
    - Tool use and MCP servers
    - Structured JSON outputs
    - Session resume

    Claude-specific options (via provider_options):
        permission_mode: "default", "acceptEdits", "plan", "bypassPermissions"
        mcp_servers: dict of MCP server configurations

    Example:
        provider = ClaudeAgentProvider()
        if provider.available:
            result = await provider.execute(prompt, config)
    """

    @property
    def name(self) -> str:
        return "claude"

    @property
    def available(self) -> bool:
        return _SDK_AVAILABLE

    @property
    def supports_mcp(self) -> bool:
        return True

    def _check_available(self) -> None:
        """Raise error if SDK not installed."""
        if not self.available:
            raise AgentNotInstalledError(
                provider="claude",
                install_cmd="pip install trident[agents-claude]",
            )

    async def execute(
        self,
        prompt: str,
        config: AgentConfig,
        on_message: MessageCallback | None = None,
    ) -> AgentResult:
        """Execute an agent via Claude Agent SDK.

        Args:
            prompt: The rendered prompt text for the agent
            config: Common and provider-specific configuration
            on_message: Optional callback for streaming messages

        Returns:
            AgentResult with output and usage metrics

        Raises:
            AgentNotInstalledError: If Claude SDK is not installed
            AgentProviderError: If execution fails
        """
        self._check_available()

        # Build MCP server config from provider_options
        mcp_servers = self._build_mcp_servers(config)

        # Determine working directory
        cwd = config.cwd or os.environ.get("TRIDENT_WORKSPACE", os.getcwd())

        # Get Claude-specific permission mode
        permission_mode = config.provider_options.get("permission_mode", "acceptEdits")

        # Build SDK options
        options = ClaudeAgentOptions(
            allowed_tools=config.allowed_tools or [],
            mcp_servers=mcp_servers,
            cwd=cwd,
            max_turns=config.max_turns,
            permission_mode=permission_mode,  # type: ignore[arg-type]
            resume=config.resume_session,
            output_format=config.output_format,  # type: ignore[arg-type]
            model=config.model,
        )

        # Execute agent and collect response
        last_assistant_text = ""
        result_message: Any = None
        max_turns_reached = False

        try:
            async for message in query(prompt=prompt, options=options):
                if isinstance(message, AssistantMessage):
                    last_assistant_text, tool_uses, tool_results = (
                        self._process_assistant_message(message)
                    )

                    # Send normalized messages via callback
                    if on_message and last_assistant_text:
                        on_message(AgentMessage("assistant", last_assistant_text))

                    if on_message:
                        for tool_use in tool_uses:
                            on_message(AgentMessage("tool_use", tool_use))
                        for tool_result in tool_results:
                            on_message(AgentMessage("tool_result", tool_result))

                elif isinstance(message, ResultMessage):
                    result_message = message
                    if on_message:
                        on_message(
                            AgentMessage(
                                "result",
                                {
                                    "num_turns": message.num_turns,
                                    "cost_usd": message.total_cost_usd,
                                },
                            )
                        )
        except Exception as e:
            raise AgentProviderError(f"Claude agent execution failed: {e}") from e

        # Check for structured output errors
        if (
            result_message
            and hasattr(result_message, "subtype")
            and result_message.subtype == "error_max_structured_output_retries"
        ):
            raise AgentOutputError(
                "Agent could not produce valid structured output "
                "matching the schema after multiple retries"
            )

        # Check if max turns was reached
        if result_message and hasattr(result_message, "subtype"):
            if result_message.subtype == "error_max_turns":
                max_turns_reached = True

        # Parse output
        output = self._parse_output(result_message, last_assistant_text, config)

        # Build usage metrics
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
            max_turns_reached=max_turns_reached,
        )

    def _build_mcp_servers(self, config: AgentConfig) -> dict[str, Any]:
        """Build MCP server configuration from provider_options.

        Args:
            config: Agent configuration with provider_options

        Returns:
            MCP servers dict formatted for Claude SDK
        """
        mcp_servers_config = config.provider_options.get("mcp_servers", {})
        mcp_servers: dict[str, Any] = {}

        for server_name, server_config in mcp_servers_config.items():
            if isinstance(server_config, dict):
                # Expand environment variables in server env
                server_env = {}
                for key, value in server_config.get("env", {}).items():
                    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                        env_var = value[2:-1]
                        server_env[key] = os.environ.get(env_var, "")
                    else:
                        server_env[key] = value

                server_dict: dict[str, Any] = {
                    "command": server_config.get("command", ""),
                    "args": server_config.get("args", []),
                }
                if server_env:
                    server_dict["env"] = server_env
                mcp_servers[server_name] = server_dict

        return mcp_servers

    def _process_assistant_message(
        self, message: Any
    ) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
        """Process an AssistantMessage and extract content.

        Args:
            message: Claude SDK AssistantMessage

        Returns:
            Tuple of (text_content, tool_uses, tool_results)
        """
        text_parts: list[str] = []
        tool_uses: list[dict[str, Any]] = []
        tool_results: list[dict[str, Any]] = []

        for block in message.content:
            if isinstance(block, TextBlock):
                text_parts.append(block.text)
            elif isinstance(block, ToolUseBlock):
                tool_uses.append({"name": block.name, "input": block.input})
            elif isinstance(block, ToolResultBlock):
                tool_results.append(
                    {"tool_use_id": block.tool_use_id, "content": block.content}
                )

        return "\n".join(text_parts), tool_uses, tool_results

    def _parse_output(
        self,
        result_message: Any,
        last_assistant_text: str,
        config: AgentConfig,
    ) -> dict[str, Any]:
        """Parse agent output from result message or text.

        Args:
            result_message: Claude SDK ResultMessage (may be None)
            last_assistant_text: Last text response from agent
            config: Agent configuration with output_format

        Returns:
            Parsed output dict

        Raises:
            AgentOutputError: If output parsing fails
        """
        # Check for structured output first (API-level validation)
        if result_message and hasattr(result_message, "structured_output"):
            structured_output = result_message.structured_output
            if structured_output is not None:
                return structured_output

        # Fallback to text parsing
        if not last_assistant_text.strip():
            raise AgentOutputError("Agent returned empty response")

        # If JSON output expected, parse it
        if config.output_format and config.output_format.get("type") == "json_schema":
            try:
                return _parse_json_response(last_assistant_text)
            except json.JSONDecodeError as e:
                raise AgentOutputError(
                    f"Agent returned invalid JSON. Response preview: {last_assistant_text[:200]!r}"
                ) from e

        # Default: return as text
        return {"text": last_assistant_text}

    def execute_sync(
        self,
        prompt: str,
        config: AgentConfig,
        on_message: MessageCallback | None = None,
    ) -> AgentResult:
        """Execute agent synchronously (wrapper for async).

        Args:
            prompt: The rendered prompt text for the agent
            config: Common and provider-specific configuration
            on_message: Optional callback for streaming messages

        Returns:
            AgentResult with output and usage metrics
        """
        self._check_available()
        return anyio.run(self.execute, prompt, config, on_message)


def _parse_json_response(text: str) -> dict[str, Any]:
    """Parse JSON from agent response, handling markdown code blocks.

    Attempts to extract JSON in order of preference:
    1. Direct JSON parse (response is pure JSON)
    2. ```json code block
    3. ``` code block (assumes JSON content)
    4. Embedded JSON object in prose

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
