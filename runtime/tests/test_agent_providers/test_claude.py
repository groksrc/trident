"""Tests for Claude agent provider implementation."""

import pytest

from trident.agent_providers.base import AgentConfig, AgentNotInstalledError


def _claude_available() -> bool:
    """Check if Claude SDK is available."""
    try:
        from trident.agent_providers.claude import _SDK_AVAILABLE

        return _SDK_AVAILABLE
    except ImportError:
        return False


class TestClaudeProvider:
    """Tests for ClaudeAgentProvider."""

    def test_provider_name(self) -> None:
        """Provider reports correct name."""
        from trident.agent_providers.claude import ClaudeAgentProvider

        provider = ClaudeAgentProvider()
        assert provider.name == "claude"

    def test_supports_mcp(self) -> None:
        """Claude provider supports MCP servers."""
        from trident.agent_providers.claude import ClaudeAgentProvider

        provider = ClaudeAgentProvider()
        assert provider.supports_mcp is True

    def test_available_check(self) -> None:
        """Availability reflects SDK installation status."""
        from trident.agent_providers.claude import ClaudeAgentProvider

        provider = ClaudeAgentProvider()
        # This will be True if claude-agent-sdk is installed, False otherwise
        assert isinstance(provider.available, bool)

    @pytest.mark.skipif(
        not _claude_available(),
        reason="Claude SDK not installed",
    )
    def test_check_available_succeeds_with_sdk(self) -> None:
        """_check_available passes when SDK is installed."""
        from trident.agent_providers.claude import ClaudeAgentProvider

        provider = ClaudeAgentProvider()
        # Should not raise
        provider._check_available()

    def test_check_available_raises_without_sdk(self) -> None:
        """_check_available raises AgentNotInstalledError when SDK missing."""
        from trident.agent_providers.claude import ClaudeAgentProvider, _SDK_AVAILABLE

        if _SDK_AVAILABLE:
            pytest.skip("Claude SDK is installed")

        provider = ClaudeAgentProvider()
        with pytest.raises(AgentNotInstalledError) as exc_info:
            provider._check_available()

        assert "claude" in str(exc_info.value)
        assert "pip install" in str(exc_info.value)


class TestClaudeProviderConfiguration:
    """Tests for Claude provider configuration handling."""

    def test_permission_mode_from_options(self) -> None:
        """Permission mode is extracted from provider_options."""
        config = AgentConfig(
            provider_options={"permission_mode": "bypassPermissions"}
        )
        assert config.provider_options.get("permission_mode") == "bypassPermissions"

    def test_mcp_servers_in_options(self) -> None:
        """MCP servers can be passed via provider_options."""
        config = AgentConfig(
            provider_options={
                "mcp_servers": {
                    "github": {
                        "command": "npx",
                        "args": ["@modelcontextprotocol/server-github"],
                        "env": {},
                    }
                }
            }
        )
        mcp_servers = config.provider_options.get("mcp_servers", {})
        assert "github" in mcp_servers
        assert mcp_servers["github"]["command"] == "npx"
