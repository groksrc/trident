"""Tests for agent provider registry."""

import pytest

from trident.agent_providers.base import (
    AgentConfig,
    AgentProvider,
    AgentProviderRegistry,
    AgentResult,
    MessageCallback,
)


class MockProvider(AgentProvider):
    """Mock provider for testing registry behavior."""

    def __init__(self, name: str = "mock", available: bool = True) -> None:
        self._name = name
        self._available = available

    @property
    def name(self) -> str:
        return self._name

    @property
    def available(self) -> bool:
        return self._available

    async def execute(
        self,
        prompt: str,
        config: AgentConfig,
        on_message: MessageCallback | None = None,
    ) -> AgentResult:
        return AgentResult(output={"text": f"Response from {self._name}"})


class TestAgentProviderRegistry:
    """Tests for AgentProviderRegistry."""

    def test_register_provider(self) -> None:
        """Provider registration works."""
        registry = AgentProviderRegistry()
        provider = MockProvider("test-provider")
        registry.register(provider)

        result = registry.get("test-provider")
        assert result is not None
        assert result.name == "test-provider"

    def test_register_multiple_providers(self) -> None:
        """Multiple providers can be registered."""
        registry = AgentProviderRegistry()
        registry.register(MockProvider("provider-a"))
        registry.register(MockProvider("provider-b"))
        registry.register(MockProvider("provider-c", available=False))

        assert registry.get("provider-a") is not None
        assert registry.get("provider-b") is not None
        assert registry.get("provider-c") is not None

    def test_get_unknown_provider(self) -> None:
        """Getting unknown provider returns None."""
        registry = AgentProviderRegistry()
        result = registry.get("nonexistent")
        assert result is None

    def test_list_registered(self) -> None:
        """List all registered provider names."""
        registry = AgentProviderRegistry()
        registry.register(MockProvider("alpha"))
        registry.register(MockProvider("beta", available=False))

        registered = registry.list_registered()
        assert "alpha" in registered
        assert "beta" in registered
        assert len(registered) == 2

    def test_list_available(self) -> None:
        """Only lists providers with available SDKs."""
        registry = AgentProviderRegistry()
        registry.register(MockProvider("available-1", available=True))
        registry.register(MockProvider("available-2", available=True))
        registry.register(MockProvider("unavailable", available=False))

        available = registry.list_available()
        assert "available-1" in available
        assert "available-2" in available
        assert "unavailable" not in available
        assert len(available) == 2

    def test_overwrite_provider(self) -> None:
        """Registering same name overwrites previous provider."""
        registry = AgentProviderRegistry()

        provider_v1 = MockProvider("test", available=False)
        provider_v2 = MockProvider("test", available=True)

        registry.register(provider_v1)
        assert registry.get("test") is not None
        assert registry.get("test").available is False

        registry.register(provider_v2)
        assert registry.get("test") is not None
        assert registry.get("test").available is True


class TestGlobalRegistry:
    """Tests for the global registry instance."""

    def test_get_registry_returns_instance(self) -> None:
        """get_registry returns a registry instance."""
        from trident.agent_providers import get_registry

        registry = get_registry()
        assert isinstance(registry, AgentProviderRegistry)

    def test_default_providers_registered(self) -> None:
        """Default providers are registered on import."""
        from trident.agent_providers import get_registry

        registry = get_registry()
        registered = registry.list_registered()

        # All three providers should be registered
        assert "claude" in registered
        assert "openai" in registered
        assert "gemini" in registered

    def test_get_claude_provider(self) -> None:
        """Claude provider can be retrieved."""
        from trident.agent_providers import get_registry

        registry = get_registry()
        claude = registry.get("claude")
        assert claude is not None
        assert claude.name == "claude"
