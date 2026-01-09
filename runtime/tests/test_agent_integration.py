"""Integration tests for agent provider dispatch."""

from pathlib import Path

import pytest


class TestProviderDispatch:
    """Tests for provider selection and dispatch in project loading."""

    def test_default_provider_is_claude(self, tmp_path: Path) -> None:
        """No provider field defaults to Claude."""
        from trident.project import load_project

        # Create manifest without provider field
        manifest = """
trident: "0.1"
name: test-default-provider

nodes:
  input:
    type: input

  agent:
    type: agent
    prompt: prompts/agent.prompt

edges:
  e1:
    from: input
    to: agent
"""
        (tmp_path / "agent.tml").write_text(manifest)
        (tmp_path / "prompts").mkdir()
        (tmp_path / "prompts" / "agent.prompt").write_text(_minimal_prompt())

        project = load_project(tmp_path)
        agent = project.agents["agent"]

        # Provider should be None (defaults to Claude at runtime)
        assert agent.provider is None

    def test_explicit_claude_provider(self, tmp_path: Path) -> None:
        """Explicit provider: claude is parsed correctly."""
        from trident.project import load_project

        manifest = """
trident: "0.1"
name: test-claude-provider

nodes:
  agent:
    type: agent
    provider: claude
    prompt: prompts/agent.prompt
"""
        (tmp_path / "agent.tml").write_text(manifest)
        (tmp_path / "prompts").mkdir()
        (tmp_path / "prompts" / "agent.prompt").write_text(_minimal_prompt())

        project = load_project(tmp_path)
        agent = project.agents["agent"]
        assert agent.provider == "claude"

    def test_openai_provider(self, tmp_path: Path) -> None:
        """provider: openai is parsed correctly."""
        from trident.project import load_project

        manifest = """
trident: "0.1"
name: test-openai-provider

nodes:
  agent:
    type: agent
    provider: openai
    model: gpt-4o
    prompt: prompts/agent.prompt
"""
        (tmp_path / "agent.tml").write_text(manifest)
        (tmp_path / "prompts").mkdir()
        (tmp_path / "prompts" / "agent.prompt").write_text(_minimal_prompt())

        project = load_project(tmp_path)
        agent = project.agents["agent"]
        assert agent.provider == "openai"
        assert agent.model == "gpt-4o"

    def test_gemini_provider(self, tmp_path: Path) -> None:
        """provider: gemini is parsed correctly."""
        from trident.project import load_project

        manifest = """
trident: "0.1"
name: test-gemini-provider

nodes:
  agent:
    type: agent
    provider: gemini
    model: gemini-pro
    prompt: prompts/agent.prompt
"""
        (tmp_path / "agent.tml").write_text(manifest)
        (tmp_path / "prompts").mkdir()
        (tmp_path / "prompts" / "agent.prompt").write_text(_minimal_prompt())

        project = load_project(tmp_path)
        agent = project.agents["agent"]
        assert agent.provider == "gemini"
        assert agent.model == "gemini-pro"


class TestProviderOptions:
    """Tests for provider_options parsing."""

    def test_provider_options_parsed(self, tmp_path: Path) -> None:
        """provider_options are parsed correctly."""
        from trident.project import load_project

        manifest = """
trident: "0.1"
name: test-provider-options

nodes:
  agent:
    type: agent
    provider: openai
    prompt: prompts/agent.prompt
    provider_options:
      temperature: 0.7
      top_p: 0.95
"""
        (tmp_path / "agent.tml").write_text(manifest)
        (tmp_path / "prompts").mkdir()
        (tmp_path / "prompts" / "agent.prompt").write_text(_minimal_prompt())

        project = load_project(tmp_path)
        agent = project.agents["agent"]
        assert agent.provider_options["temperature"] == 0.7
        assert agent.provider_options["top_p"] == 0.95

    def test_permission_mode_in_provider_options(self, tmp_path: Path) -> None:
        """permission_mode can be set via provider_options."""
        from trident.project import load_project

        manifest = """
trident: "0.1"
name: test-permission-mode

nodes:
  agent:
    type: agent
    provider: claude
    prompt: prompts/agent.prompt
    provider_options:
      permission_mode: bypassPermissions
"""
        (tmp_path / "agent.tml").write_text(manifest)
        (tmp_path / "prompts").mkdir()
        (tmp_path / "prompts" / "agent.prompt").write_text(_minimal_prompt())

        project = load_project(tmp_path)
        agent = project.agents["agent"]
        assert agent.provider_options["permission_mode"] == "bypassPermissions"


class TestBackwardCompatibility:
    """Tests for backward compatibility with legacy syntax."""

    def test_legacy_permission_mode(self, tmp_path: Path) -> None:
        """Top-level permission_mode still works (deprecated)."""
        from trident.project import load_project

        manifest = """
trident: "0.1"
name: test-legacy-permission

nodes:
  agent:
    type: agent
    prompt: prompts/agent.prompt
    permission_mode: acceptEdits
"""
        (tmp_path / "agent.tml").write_text(manifest)
        (tmp_path / "prompts").mkdir()
        (tmp_path / "prompts" / "agent.prompt").write_text(_minimal_prompt())

        project = load_project(tmp_path)
        agent = project.agents["agent"]

        # Legacy field should be preserved
        assert agent.permission_mode == "acceptEdits"
        # And also moved to provider_options
        assert agent.provider_options.get("permission_mode") == "acceptEdits"

    def test_mcp_servers_still_work(self, tmp_path: Path) -> None:
        """MCP servers configuration still works."""
        from trident.project import load_project

        manifest = """
trident: "0.1"
name: test-mcp-servers

nodes:
  agent:
    type: agent
    prompt: prompts/agent.prompt
    mcp_servers:
      github:
        command: npx
        args:
          - "@modelcontextprotocol/server-github"
"""
        (tmp_path / "agent.tml").write_text(manifest)
        (tmp_path / "prompts").mkdir()
        (tmp_path / "prompts" / "agent.prompt").write_text(_minimal_prompt())

        project = load_project(tmp_path)
        agent = project.agents["agent"]

        assert "github" in agent.mcp_servers
        assert agent.mcp_servers["github"].command == "npx"


class TestRegistryIntegration:
    """Tests for registry behavior at runtime."""

    def test_invalid_provider_lookup(self) -> None:
        """Unknown provider returns None from registry."""
        from trident.agent_providers import get_registry

        registry = get_registry()
        result = registry.get("nonexistent-provider")
        assert result is None

    def test_all_providers_have_correct_interface(self) -> None:
        """All registered providers implement the protocol."""
        from trident.agent_providers import get_registry
        from trident.agent_providers.base import AgentProvider

        registry = get_registry()
        for name in registry.list_registered():
            provider = registry.get(name)
            assert provider is not None
            # Check protocol requirements
            assert hasattr(provider, "name")
            assert hasattr(provider, "available")
            assert hasattr(provider, "execute")
            assert hasattr(provider, "supports_mcp")


def _minimal_prompt() -> str:
    """Return a minimal valid prompt file."""
    return """---
id: agent
name: Test Agent
---
Test prompt: {{ task }}
"""
