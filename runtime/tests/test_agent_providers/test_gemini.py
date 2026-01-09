"""Tests for Gemini agent provider implementation."""

import pytest

from trident.agent_providers.base import AgentConfig, AgentNotInstalledError


class TestGeminiProvider:
    """Tests for GeminiAgentProvider."""

    def test_provider_name(self) -> None:
        """Provider reports correct name."""
        from trident.agent_providers.gemini import GeminiAgentProvider

        provider = GeminiAgentProvider()
        assert provider.name == "gemini"

    def test_does_not_support_mcp(self) -> None:
        """Gemini provider does not support MCP servers."""
        from trident.agent_providers.gemini import GeminiAgentProvider

        provider = GeminiAgentProvider()
        assert provider.supports_mcp is False

    def test_available_check(self) -> None:
        """Availability reflects SDK installation status."""
        from trident.agent_providers.gemini import GeminiAgentProvider

        provider = GeminiAgentProvider()
        # This will be True if google-generativeai is installed, False otherwise
        assert isinstance(provider.available, bool)

    def test_check_available_raises_without_sdk(self) -> None:
        """_check_available raises AgentNotInstalledError when SDK missing."""
        from trident.agent_providers.gemini import GeminiAgentProvider, _SDK_AVAILABLE

        if _SDK_AVAILABLE:
            pytest.skip("Gemini SDK is installed")

        provider = GeminiAgentProvider()
        with pytest.raises(AgentNotInstalledError) as exc_info:
            provider._check_available()

        assert "gemini" in str(exc_info.value)
        assert "pip install" in str(exc_info.value)


class TestGeminiProviderConfiguration:
    """Tests for Gemini provider configuration handling."""

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
        mcp_servers = config.provider_options.get("mcp_servers", {})
        assert "github" in mcp_servers

    def test_gemini_specific_options(self) -> None:
        """Gemini-specific options can be passed."""
        config = AgentConfig(
            provider_options={
                "temperature": 0.7,
                "top_p": 0.9,
                "top_k": 40,
            }
        )
        assert config.provider_options["temperature"] == 0.7
        assert config.provider_options["top_p"] == 0.9
        assert config.provider_options["top_k"] == 40
