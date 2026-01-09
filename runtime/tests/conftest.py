"""Shared test fixtures and mocks for Trident tests."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


@dataclass
class MockClaudeMessage:
    """Mock Claude SDK message for testing."""

    text: str = ""
    num_turns: int = 1
    cost_usd: float = 0.01
    session_id: str = "test-session-123"
    input_tokens: int = 100
    output_tokens: int = 50


@pytest.fixture
def mock_claude_sdk(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Mock claude_agent_sdk for unit tests.

    Returns a mock that can be configured for specific test scenarios.
    """
    mock_query = AsyncMock()
    mock_query.return_value = iter(
        [
            MagicMock(
                type="assistant",
                text="Test response from Claude",
            ),
            MagicMock(
                type="result",
                text="Final output",
                num_turns=1,
                cost_usd=0.01,
                session_id="test-session-123",
                input_tokens=100,
                output_tokens=50,
            ),
        ]
    )

    # Try to patch if the module exists
    try:
        monkeypatch.setattr(
            "trident.agent_providers.claude.query", mock_query, raising=False
        )
    except Exception:
        pass

    return mock_query


@pytest.fixture
def mock_openai_client(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Mock OpenAI client for unit tests."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content="Test response from OpenAI"))
    ]
    mock_client.chat.completions.create.return_value = mock_response

    try:
        monkeypatch.setattr(
            "trident.agent_providers.openai.openai.OpenAI",
            lambda: mock_client,
            raising=False,
        )
    except Exception:
        pass

    return mock_client


@pytest.fixture
def mock_gemini_client(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Mock Gemini client for unit tests."""
    mock_model = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "Test response from Gemini"
    mock_model.generate_content.return_value = mock_response

    try:
        monkeypatch.setattr(
            "trident.agent_providers.gemini.genai.GenerativeModel",
            lambda model: mock_model,
            raising=False,
        )
    except Exception:
        pass

    return mock_model


@pytest.fixture
def temp_project_dir(tmp_path: Path) -> Path:
    """Create a temporary project directory with basic structure."""
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    return tmp_path


@pytest.fixture
def sample_manifest() -> str:
    """Return a sample manifest YAML for testing."""
    return """
trident: "0.1"
name: test-project
description: Test project for agent providers

defaults:
  model: claude-3-5-sonnet-latest

nodes:
  input:
    type: input

  agent:
    type: agent
    prompt: prompts/agent.prompt
    max_turns: 10
    allowed_tools:
      - Read
      - Write

  output:
    type: output

edges:
  e1:
    from: input
    to: agent
    mapping:
      task: task

  e2:
    from: agent
    to: output
    mapping:
      result: output.result
"""


@pytest.fixture
def sample_prompt() -> str:
    """Return a sample prompt file content for testing."""
    return """---
id: agent
name: Test Agent
description: A test agent prompt

input:
  task:
    type: string
    description: The task to perform

output:
  format: json
  schema:
    result: string, The result of the task
---
You are a helpful assistant. Complete the following task:

{{ task }}

Return your result as JSON with a "result" field.
"""


@pytest.fixture
def project_with_agent(temp_project_dir: Path, sample_manifest: str, sample_prompt: str) -> Path:
    """Create a complete test project with an agent node."""
    # Write manifest
    manifest_path = temp_project_dir / "agent.tml"
    manifest_path.write_text(sample_manifest)

    # Write prompt
    prompts_dir = temp_project_dir / "prompts"
    prompts_dir.mkdir(exist_ok=True)
    prompt_path = prompts_dir / "agent.prompt"
    prompt_path.write_text(sample_prompt)

    return temp_project_dir


@pytest.fixture
def sample_agent_config() -> dict[str, Any]:
    """Return sample AgentConfig parameters for testing."""
    return {
        "max_turns": 50,
        "cwd": "/tmp/test",
        "allowed_tools": ["Read", "Write", "Glob"],
        "output_format": None,
        "resume_session": None,
        "model": None,
        "provider_options": {},
    }
