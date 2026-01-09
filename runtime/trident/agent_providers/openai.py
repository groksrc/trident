"""OpenAI Agents provider implementation.

This module implements the AgentProvider protocol for OpenAI's agent APIs,
enabling multi-turn agent execution with tool calling.

Requires: pip install trident[agents-openai]

Note: This is a stub implementation. Full implementation pending OpenAI
agent API details.
"""

import logging
from typing import Any

from .base import (
    AgentConfig,
    AgentMessage,
    AgentNotInstalledError,
    AgentProvider,
    AgentProviderError,
    AgentResult,
    MessageCallback,
)

logger = logging.getLogger(__name__)

# Check for SDK availability
try:
    import openai

    _SDK_AVAILABLE = True
except ImportError:
    _SDK_AVAILABLE = False
    openai = None  # type: ignore


class OpenAIAgentProvider(AgentProvider):
    """Agent provider using OpenAI APIs.

    This provider executes agents via OpenAI's APIs, supporting:
    - Multi-turn execution with tool calling
    - Function calling
    - Structured JSON outputs

    OpenAI-specific options (via provider_options):
        temperature: float (0-2)
        top_p: float (0-1)
        seed: int for deterministic outputs

    Note: MCP servers are not supported by OpenAI.

    Example:
        provider = OpenAIAgentProvider()
        if provider.available:
            result = await provider.execute(prompt, config)
    """

    @property
    def name(self) -> str:
        return "openai"

    @property
    def available(self) -> bool:
        return _SDK_AVAILABLE

    @property
    def supports_mcp(self) -> bool:
        # OpenAI does not support MCP servers
        return False

    def _check_available(self) -> None:
        """Raise error if SDK not installed."""
        if not self.available:
            raise AgentNotInstalledError(
                provider="openai",
                install_cmd="pip install trident[agents-openai]",
            )

    async def execute(
        self,
        prompt: str,
        config: AgentConfig,
        on_message: MessageCallback | None = None,
    ) -> AgentResult:
        """Execute an agent via OpenAI APIs.

        Args:
            prompt: The rendered prompt text for the agent
            config: Common and provider-specific configuration
            on_message: Optional callback for streaming messages

        Returns:
            AgentResult with output and usage metrics

        Raises:
            AgentNotInstalledError: If OpenAI SDK is not installed
            AgentProviderError: If execution fails
        """
        self._check_available()

        # Warn if MCP servers configured (not supported)
        mcp_servers = config.provider_options.get("mcp_servers", {})
        if mcp_servers:
            logger.warning(
                "MCP servers configured but not supported by OpenAI provider. "
                "MCP servers will be ignored."
            )

        # TODO: Implement OpenAI agent execution
        # This will involve:
        # 1. Building messages from prompt
        # 2. Setting up tool definitions from allowed_tools
        # 3. Running the agent loop with tool calling
        # 4. Parsing structured outputs

        raise AgentProviderError(
            "OpenAI agent provider not yet fully implemented. "
            "Use provider: claude for now."
        )

    def _build_tools(self, config: AgentConfig) -> list[dict[str, Any]]:
        """Build OpenAI tool definitions from allowed_tools.

        Args:
            config: Agent configuration

        Returns:
            List of OpenAI tool definitions
        """
        # TODO: Map Trident tool names to OpenAI function definitions
        return []
