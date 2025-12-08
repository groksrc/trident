"""Provider protocol and registry."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class CompletionConfig:
    """Configuration for a completion request."""

    model: str
    temperature: float | None = None
    max_tokens: int | None = None
    output_format: str = "text"  # "text" or "json"
    output_schema: dict[str, tuple[str, str]] | None = None  # field -> (type, desc)


@dataclass
class CompletionResult:
    """Result from a completion request."""

    content: str
    input_tokens: int = 0
    output_tokens: int = 0


@runtime_checkable
class Provider(Protocol):
    """Protocol for model providers."""

    name: str

    def complete(self, prompt: str, config: CompletionConfig) -> CompletionResult:
        """Execute a completion request."""
        ...


class ProviderRegistry:
    """Registry for model providers."""

    def __init__(self):
        self._providers: dict[str, Provider] = {}

    def register(self, provider: Provider) -> None:
        """Register a provider."""
        self._providers[provider.name] = provider

    def get(self, name: str) -> Provider | None:
        """Get a provider by name."""
        return self._providers.get(name)

    def get_for_model(self, model_id: str) -> tuple[Provider, str] | None:
        """Get provider and model name from model identifier.

        Args:
            model_id: Model identifier (e.g., "anthropic/claude-sonnet-4-20250514")

        Returns:
            Tuple of (provider, model_name) or None if not found
        """
        if "/" not in model_id:
            return None
        provider_name, model_name = model_id.split("/", 1)
        provider = self.get(provider_name)
        if provider:
            return provider, model_name
        return None


# Global registry
_registry = ProviderRegistry()


def get_registry() -> ProviderRegistry:
    """Get the global provider registry."""
    return _registry


def register_provider(provider: Provider) -> None:
    """Register a provider globally."""
    _registry.register(provider)
