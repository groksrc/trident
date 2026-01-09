"""Tests for agent provider base abstractions."""

import pytest

from trident.agent_providers.base import (
    AgentConfig,
    AgentMessage,
    AgentNotInstalledError,
    AgentProviderError,
    AgentResult,
)


class TestAgentConfig:
    """Tests for AgentConfig dataclass."""

    def test_defaults(self) -> None:
        """AgentConfig has sensible defaults."""
        config = AgentConfig()
        assert config.max_turns == 50
        assert config.cwd is None
        assert config.allowed_tools == []
        assert config.output_format is None
        assert config.resume_session is None
        assert config.model is None
        assert config.provider_options == {}

    def test_custom_values(self) -> None:
        """AgentConfig accepts custom values."""
        config = AgentConfig(
            max_turns=10,
            cwd="/tmp/test",
            allowed_tools=["Read", "Write"],
            model="claude-3-5-sonnet-latest",
            provider_options={"permission_mode": "bypassPermissions"},
        )
        assert config.max_turns == 10
        assert config.cwd == "/tmp/test"
        assert config.allowed_tools == ["Read", "Write"]
        assert config.model == "claude-3-5-sonnet-latest"
        assert config.provider_options["permission_mode"] == "bypassPermissions"


class TestAgentResult:
    """Tests for AgentResult dataclass."""

    def test_required_fields(self) -> None:
        """AgentResult requires output field."""
        result = AgentResult(output={"text": "Hello"})
        assert result.output == {"text": "Hello"}
        assert result.tokens == {}
        assert result.cost_usd is None
        assert result.session_id is None
        assert result.num_turns == 0

    def test_all_fields(self) -> None:
        """AgentResult accepts all optional fields."""
        result = AgentResult(
            output={"result": "success"},
            tokens={"input": 100, "output": 50},
            cost_usd=0.015,
            session_id="session-abc",
            num_turns=3,
        )
        assert result.output == {"result": "success"}
        assert result.tokens["input"] == 100
        assert result.tokens["output"] == 50
        assert result.cost_usd == 0.015
        assert result.session_id == "session-abc"
        assert result.num_turns == 3


class TestAgentMessage:
    """Tests for AgentMessage dataclass."""

    def test_message_creation(self) -> None:
        """AgentMessage stores type and content."""
        msg = AgentMessage(type="assistant", content="Hello, world!")
        assert msg.type == "assistant"
        assert msg.content == "Hello, world!"

    def test_message_types(self) -> None:
        """AgentMessage supports various types."""
        types = ["assistant", "tool_use", "tool_result", "result"]
        for msg_type in types:
            msg = AgentMessage(type=msg_type, content={"data": "test"})
            assert msg.type == msg_type


class TestAgentProviderErrors:
    """Tests for agent provider error classes."""

    def test_provider_error(self) -> None:
        """AgentProviderError is a base exception."""
        error = AgentProviderError("Something went wrong")
        assert str(error) == "Something went wrong"
        assert isinstance(error, Exception)

    def test_not_installed_error(self) -> None:
        """AgentNotInstalledError provides install instructions."""
        error = AgentNotInstalledError(
            provider="openai",
            install_cmd="pip install trident[agents-openai]",
        )
        assert "openai" in str(error)
        assert "pip install trident[agents-openai]" in str(error)
        assert isinstance(error, AgentProviderError)

    def test_not_installed_error_stores_fields(self) -> None:
        """AgentNotInstalledError stores provider and install_cmd."""
        error = AgentNotInstalledError(
            provider="gemini",
            install_cmd="pip install google-generativeai",
        )
        assert error.provider == "gemini"
        assert error.install_cmd == "pip install google-generativeai"
        assert "gemini" in str(error)
