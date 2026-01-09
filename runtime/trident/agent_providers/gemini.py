"""Google Gemini agent provider implementation.

This module implements the AgentProvider protocol for Google's Gemini APIs,
enabling multi-turn agent execution with tool calling.

Requires: pip install trident[agents-gemini]

Note: This is a stub implementation. Full implementation pending Gemini
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
    import google.generativeai as genai

    _SDK_AVAILABLE = True
except ImportError:
    _SDK_AVAILABLE = False
    genai = None  # type: ignore


class GeminiAgentProvider(AgentProvider):
    """Agent provider using Google Gemini APIs.

    This provider executes agents via Google's Generative AI APIs, supporting:
    - Multi-turn execution with tool calling
    - Function calling
    - Structured JSON outputs

    Gemini-specific options (via provider_options):
        temperature: float (0-2)
        top_p: float (0-1)
        top_k: int

    Note: MCP servers may have limited support with Gemini.

    Example:
        provider = GeminiAgentProvider()
        if provider.available:
            result = await provider.execute(prompt, config)
    """

    @property
    def name(self) -> str:
        return "gemini"

    @property
    def available(self) -> bool:
        return _SDK_AVAILABLE

    @property
    def supports_mcp(self) -> bool:
        # Gemini may support MCP in the future
        return False

    def _check_available(self) -> None:
        """Raise error if SDK not installed."""
        if not self.available:
            raise AgentNotInstalledError(
                provider="gemini",
                install_cmd="pip install trident[agents-gemini]",
            )

    async def execute(
        self,
        prompt: str,
        config: AgentConfig,
        on_message: MessageCallback | None = None,
    ) -> AgentResult:
        """Execute an agent via Gemini APIs.

        Args:
            prompt: The rendered prompt text for the agent
            config: Common and provider-specific configuration
            on_message: Optional callback for streaming messages

        Returns:
            AgentResult with output and usage metrics

        Raises:
            AgentNotInstalledError: If Gemini SDK is not installed
            AgentProviderError: If execution fails
        """
        self._check_available()

        # Warn if MCP servers configured (not supported)
        mcp_servers = config.provider_options.get("mcp_servers", {})
        if mcp_servers:
            logger.warning(
                "MCP servers configured but not supported by Gemini provider. "
                "MCP servers will be ignored."
            )

        # TODO: Implement Gemini agent execution
        # This will involve:
        # 1. Building content parts from prompt
        # 2. Setting up tool definitions from allowed_tools
        # 3. Running the agent loop with function calling
        # 4. Parsing structured outputs

        raise AgentProviderError(
            "Gemini agent provider not yet fully implemented. "
            "Use provider: claude for now."
        )

    def _build_tools(self, config: AgentConfig) -> list[dict[str, Any]]:
        """Build Gemini tool definitions from allowed_tools.

        Args:
            config: Agent configuration

        Returns:
            List of Gemini tool definitions
        """
        # TODO: Map Trident tool names to Gemini function declarations
        return []
