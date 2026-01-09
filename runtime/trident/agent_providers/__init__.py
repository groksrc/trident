"""Agent providers package.

This package provides the multi-provider agent execution layer for Trident.
Each provider implements the AgentProvider protocol to execute agents via
their respective SDKs.

Supported providers:
    - claude: Claude Agent SDK (default)
    - openai: OpenAI Agents API
    - gemini: Google Gemini

Usage:
    from trident.agent_providers import get_registry, AgentConfig

    registry = get_registry()
    provider = registry.get("claude")

    if provider and provider.available:
        result = await provider.execute(prompt, config)
"""

from .base import (
    AgentConfig,
    AgentMessage,
    AgentProvider,
    AgentProviderError,
    AgentProviderRegistry,
    AgentResult,
    AgentAuthError,
    AgentNotInstalledError,
    AgentOutputError,
    AgentRateLimitError,
    AgentTimeoutError,
    MessageCallback,
    get_registry,
)

__all__ = [
    # Core types
    "AgentConfig",
    "AgentMessage",
    "AgentProvider",
    "AgentProviderRegistry",
    "AgentResult",
    "MessageCallback",
    # Errors
    "AgentProviderError",
    "AgentAuthError",
    "AgentNotInstalledError",
    "AgentOutputError",
    "AgentRateLimitError",
    "AgentTimeoutError",
    # Registry
    "get_registry",
]
