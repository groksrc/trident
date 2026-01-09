"""Base abstractions for agent providers.

This module defines the AgentProvider protocol that all agent providers
must implement, along with common configuration and result types.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentConfig:
    """Common configuration for all agent providers.

    Provider-specific options should be passed via provider_options dict.

    Attributes:
        max_turns: Maximum number of agent iterations
        cwd: Working directory for agent execution
        allowed_tools: List of tools the agent can use
        output_format: JSON schema for structured outputs (optional)
        resume_session: Session ID to resume from (optional)
        model: Model identifier (optional, uses provider default)
        provider_options: Provider-specific configuration dict
    """

    max_turns: int = 50
    cwd: str | None = None
    allowed_tools: list[str] = field(default_factory=list)
    output_format: dict[str, Any] | None = None
    resume_session: str | None = None
    model: str | None = None
    provider_options: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentMessage:
    """Normalized agent message for streaming callbacks.

    All providers normalize their messages to this format before
    calling the on_message callback.

    Attributes:
        type: Message type - "assistant", "tool_use", "tool_result", "result"
        content: Message content (type depends on message type)
    """

    type: str
    content: Any


@dataclass
class AgentResult:
    """Result from agent execution with usage metrics.

    All providers return this standardized result format.

    Attributes:
        output: The parsed output from the agent (dict)
        session_id: Session ID for resuming later (optional)
        num_turns: Number of turns in the agent execution
        cost_usd: Total cost in USD (None if not available)
        tokens: Token usage dictionary with input/output counts
        max_turns_reached: True if execution stopped due to turn limit
    """

    output: dict[str, Any]
    session_id: str | None = None
    num_turns: int = 0
    cost_usd: float | None = None
    tokens: dict[str, int] = field(default_factory=dict)
    max_turns_reached: bool = False


# Type alias for message callbacks
MessageCallback = Callable[[AgentMessage], None]


class AgentProviderError(Exception):
    """Base error for agent provider issues."""

    pass


class AgentNotInstalledError(AgentProviderError):
    """Provider SDK is not installed."""

    def __init__(self, provider: str, install_cmd: str):
        self.provider = provider
        self.install_cmd = install_cmd
        super().__init__(
            f"Provider '{provider}' not installed. Install with: {install_cmd}"
        )


class AgentAuthError(AgentProviderError):
    """Authentication failed for the provider."""

    def __init__(self, provider: str, env_var: str | None = None):
        self.provider = provider
        self.env_var = env_var
        msg = f"Authentication failed for provider '{provider}'"
        if env_var:
            msg += f". Ensure {env_var} is set."
        super().__init__(msg)


class AgentRateLimitError(AgentProviderError):
    """Rate limit exceeded."""

    def __init__(self, provider: str, retry_after: float | None = None):
        self.provider = provider
        self.retry_after = retry_after
        msg = f"Rate limit exceeded for provider '{provider}'"
        if retry_after:
            msg += f". Retry after {retry_after} seconds."
        super().__init__(msg)


class AgentTimeoutError(AgentProviderError):
    """Agent execution timed out."""

    pass


class AgentOutputError(AgentProviderError):
    """Agent output validation failed."""

    pass


class AgentProvider(ABC):
    """Abstract base class for agent providers.

    Each provider implementation handles the specifics of executing
    agents via their respective SDKs while conforming to this interface.

    Subclasses must implement:
        - name: Provider identifier (e.g., "claude", "openai")
        - available: Property checking if SDK is installed
        - execute: Async execution method
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier (e.g., 'claude', 'openai', 'gemini')."""
        ...

    @property
    @abstractmethod
    def available(self) -> bool:
        """Check if this provider's SDK is installed and usable."""
        ...

    @property
    def supports_mcp(self) -> bool:
        """Whether this provider supports MCP servers.

        Override in subclasses that support MCP.
        """
        return False

    @abstractmethod
    async def execute(
        self,
        prompt: str,
        config: AgentConfig,
        on_message: MessageCallback | None = None,
    ) -> AgentResult:
        """Execute an agent with the given prompt and configuration.

        Args:
            prompt: The rendered prompt text for the agent
            config: Common and provider-specific configuration
            on_message: Optional callback for streaming messages

        Returns:
            AgentResult with output and usage metrics

        Raises:
            AgentNotInstalledError: If SDK is not installed
            AgentAuthError: If authentication fails
            AgentRateLimitError: If rate limited
            AgentTimeoutError: If execution times out
            AgentOutputError: If output validation fails
            AgentProviderError: For other provider-specific errors
        """
        ...


class AgentProviderRegistry:
    """Registry for agent providers.

    Maintains a collection of available providers and handles
    provider lookup by name.
    """

    def __init__(self) -> None:
        self._providers: dict[str, AgentProvider] = {}
        self._default: str = "claude"

    def register(self, provider: AgentProvider) -> None:
        """Register a provider.

        Args:
            provider: The provider instance to register
        """
        self._providers[provider.name] = provider

    def get(self, name: str) -> AgentProvider | None:
        """Get a provider by name.

        Args:
            name: Provider identifier

        Returns:
            Provider instance or None if not found
        """
        return self._providers.get(name)

    def get_default(self) -> AgentProvider | None:
        """Get the default provider.

        Returns:
            Default provider instance or None if not registered
        """
        return self._providers.get(self._default)

    def set_default(self, name: str) -> None:
        """Set the default provider name.

        Args:
            name: Provider identifier to use as default
        """
        self._default = name

    def list_registered(self) -> list[str]:
        """List all registered provider names.

        Returns:
            List of provider names
        """
        return list(self._providers.keys())

    def list_available(self) -> list[str]:
        """List providers that are installed and available.

        Returns:
            List of available provider names
        """
        return [name for name, p in self._providers.items() if p.available]


# Global registry instance
_registry: AgentProviderRegistry | None = None


def get_registry() -> AgentProviderRegistry:
    """Get the global agent provider registry.

    Initializes the registry on first call and registers
    all known providers.

    Returns:
        The global AgentProviderRegistry instance
    """
    global _registry
    if _registry is None:
        _registry = AgentProviderRegistry()
        _register_default_providers(_registry)
    return _registry


def _register_default_providers(registry: AgentProviderRegistry) -> None:
    """Register all default providers.

    Called once when the registry is first initialized.
    """
    # Import providers here to avoid circular imports
    # Each provider module handles its own SDK availability check
    try:
        from .claude import ClaudeAgentProvider

        registry.register(ClaudeAgentProvider())
    except ImportError:
        pass

    try:
        from .openai import OpenAIAgentProvider

        registry.register(OpenAIAgentProvider())
    except ImportError:
        pass

    try:
        from .gemini import GeminiAgentProvider

        registry.register(GeminiAgentProvider())
    except ImportError:
        pass
