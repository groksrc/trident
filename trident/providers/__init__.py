"""Model providers."""

from .base import (
    Provider,
    ProviderRegistry,
    CompletionConfig,
    CompletionResult,
    get_registry,
    register_provider,
)
from .anthropic import AnthropicProvider
from .openai import OpenAIProvider

__all__ = [
    "Provider",
    "ProviderRegistry",
    "CompletionConfig",
    "CompletionResult",
    "get_registry",
    "register_provider",
    "AnthropicProvider",
    "OpenAIProvider",
]


def setup_providers() -> None:
    """Initialize and register built-in providers."""
    register_provider(AnthropicProvider())
    register_provider(OpenAIProvider())
