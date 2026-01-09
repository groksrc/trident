"""Tests for OpenAI agent provider implementation."""

import pytest

from trident.agent_providers.base import AgentConfig, AgentNotInstalledError


class TestOpenAIProvider:
    """Tests for OpenAIAgentProvider."""

    def test_provider_name(self) -> None:
        """Provider reports correct name."""
        from trident.agent_providers.openai import OpenAIAgentProvider

        provider = OpenAIAgentProvider()
        assert provider.name == "openai"

    def test_does_not_support_mcp(self) -> None:
        """OpenAI provider does not support MCP servers."""
        from trident.agent_providers.openai import OpenAIAgentProvider

        provider = OpenAIAgentProvider()
        assert provider.supports_mcp is False

    def test_available_check(self) -> None:
        """Availability reflects SDK installation status."""
        from trident.agent_providers.openai import OpenAIAgentProvider

        provider = OpenAIAgentProvider()
        # This will be True if openai is installed, False otherwise
        assert isinstance(provider.available, bool)

    def test_check_available_raises_without_sdk(self) -> None:
        """_check_available raises AgentNotInstalledError when SDK missing."""
        from trident.agent_providers.openai import OpenAIAgentProvider, _SDK_AVAILABLE

        if _SDK_AVAILABLE:
            pytest.skip("OpenAI SDK is installed")

        provider = OpenAIAgentProvider()
        with pytest.raises(AgentNotInstalledError) as exc_info:
            provider._check_available()

        assert "openai" in str(exc_info.value)
        assert "pip install" in str(exc_info.value)


class TestOpenAIProviderConfiguration:
    """Tests for OpenAI provider configuration handling."""

    def test_mcp_servers_warning(self) -> None:
        """MCP servers in config should not cause errors (just warnings)."""
        config = AgentConfig(
            provider_options={
                "mcp_servers": {
                    "github": {
                        "command": "npx",
                        "args": ["@modelcontextprotocol/server-github"],
                    }
                }
            }
        )
        # Config should be valid even with MCP servers
        # Provider will log warning but not fail on config validation
        mcp_servers = config.provider_options.get("mcp_servers", {})
        assert "github" in mcp_servers

    def test_openai_specific_options(self) -> None:
        """OpenAI-specific options can be passed."""
        config = AgentConfig(
            provider_options={
                "temperature": 0.7,
                "top_p": 0.95,
                "seed": 42,
            }
        )
        assert config.provider_options["temperature"] == 0.7
        assert config.provider_options["top_p"] == 0.95
        assert config.provider_options["seed"] == 42
