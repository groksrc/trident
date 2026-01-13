"""Tests for project loading."""

import os
import tempfile
import unittest
from pathlib import Path

from trident.project import ParseError, ValidationError, _load_dotenv, load_project


class TestProjectLoading(unittest.TestCase):
    def test_load_minimal_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Create agent.tml
            (root / "agent.tml").write_text("""
trident: "0.1"
name: test-project
""")

            # Create prompts dir with a prompt
            (root / "prompts").mkdir()
            (root / "prompts" / "hello.prompt").write_text("""---
id: hello
---
Hello!
""")

            project = load_project(root)
            self.assertEqual(project.name, "test-project")
            self.assertIn("hello", project.prompts)

    def test_load_with_edges(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            (root / "agent.tml").write_text("""
trident: "0.1"
name: test
edges:
  e1:
    from: input
    to: process
    mapping:
      data: text
""")

            (root / "prompts").mkdir()
            (root / "prompts" / "process.prompt").write_text("""---
id: process
---
Process {{data}}
""")

            project = load_project(root)
            self.assertIn("e1", project.edges)
            self.assertEqual(project.edges["e1"].from_node, "input")
            self.assertEqual(project.edges["e1"].to_node, "process")

    def test_missing_manifest_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir, self.assertRaises(ParseError):
            load_project(tmpdir)

    def test_missing_required_field_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "agent.tml").write_text("""
name: no-version
""")
            with self.assertRaises(ValidationError):
                load_project(root)

    def test_load_agent_node(self):
        """Test loading a project with agent nodes (SPEC-3)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            (root / "agent.tml").write_text("""
trident: "0.2"
name: test-agents
nodes:
  tester:
    type: agent
    prompt: prompts/tester.prompt
    allowed_tools:
      - Read
      - Glob
    mcp_servers:
      playwright:
        command: npx
        args:
          - "@playwright/mcp@latest"
    max_turns: 25
""")

            (root / "prompts").mkdir()
            (root / "prompts" / "tester.prompt").write_text("""---
id: tester
output:
  format: json
  schema:
    status:
      type: string
      description: Test status
    passed:
      type: array
      description: Passed tests
---
Test the app at {{app_url}}.
""")

            project = load_project(root)
            self.assertEqual(project.name, "test-agents")
            self.assertIn("tester", project.agents)

            agent = project.agents["tester"]
            self.assertEqual(agent.id, "tester")
            self.assertEqual(agent.allowed_tools, ["Read", "Glob"])
            self.assertEqual(agent.max_turns, 25)
            self.assertIn("playwright", agent.mcp_servers)
            self.assertEqual(agent.mcp_servers["playwright"].command, "npx")
            self.assertEqual(agent.mcp_servers["playwright"].args, ["@playwright/mcp@latest"])


class TestDotenvLoading(unittest.TestCase):
    """Tests for .env file loading."""

    def setUp(self):
        """Track env vars we set so we can clean up."""
        self._env_vars_set: list[str] = []

    def tearDown(self):
        """Clean up any env vars we set."""
        for key in self._env_vars_set:
            os.environ.pop(key, None)

    def _track_env(self, key: str) -> None:
        """Track an env var for cleanup."""
        self._env_vars_set.append(key)

    def test_load_dotenv_basic(self):
        """Loads KEY=VALUE pairs into os.environ."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text("TEST_DOTENV_KEY=test_value\n")

            self._track_env("TEST_DOTENV_KEY")
            _load_dotenv(env_file)

            self.assertEqual(os.environ.get("TEST_DOTENV_KEY"), "test_value")

    def test_load_dotenv_with_double_quotes(self):
        """Strips double quotes from values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text('TEST_QUOTED="value with spaces"\n')

            self._track_env("TEST_QUOTED")
            _load_dotenv(env_file)

            self.assertEqual(os.environ.get("TEST_QUOTED"), "value with spaces")

    def test_load_dotenv_with_single_quotes(self):
        """Strips single quotes from values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text("TEST_SINGLE='quoted value'\n")

            self._track_env("TEST_SINGLE")
            _load_dotenv(env_file)

            self.assertEqual(os.environ.get("TEST_SINGLE"), "quoted value")

    def test_load_dotenv_skips_comments(self):
        """Ignores # comment lines."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text("# This is a comment\nTEST_COMMENT=value\n# Another comment\n")

            self._track_env("TEST_COMMENT")
            _load_dotenv(env_file)

            self.assertEqual(os.environ.get("TEST_COMMENT"), "value")

    def test_load_dotenv_skips_empty_lines(self):
        """Handles blank lines gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text("\n\nTEST_EMPTY=value\n\n")

            self._track_env("TEST_EMPTY")
            _load_dotenv(env_file)

            self.assertEqual(os.environ.get("TEST_EMPTY"), "value")

    def test_load_dotenv_no_override(self):
        """Doesn't override existing env vars."""
        # Set the var first
        os.environ["TEST_EXISTING"] = "original"
        self._track_env("TEST_EXISTING")

        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text("TEST_EXISTING=new_value\n")

            _load_dotenv(env_file)

            # Should still be original
            self.assertEqual(os.environ.get("TEST_EXISTING"), "original")

    def test_load_dotenv_missing_file(self):
        """No error when .env doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            # Don't create the file
            _load_dotenv(env_file)  # Should not raise

    def test_load_dotenv_skips_malformed_lines(self):
        """Skips lines without = sign."""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text("MALFORMED\nTEST_VALID=works\n")

            self._track_env("TEST_VALID")
            _load_dotenv(env_file)

            self.assertEqual(os.environ.get("TEST_VALID"), "works")
            self.assertIsNone(os.environ.get("MALFORMED"))

    def test_load_project_with_dotenv(self):
        """Integration: project loads .env values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Create .env
            (root / ".env").write_text("TEST_PROJECT_ENV=loaded_from_dotenv\n")
            self._track_env("TEST_PROJECT_ENV")

            # Create minimal manifest
            (root / "agent.tml").write_text("""
trident: "0.1"
name: test-with-env
""")
            (root / "prompts").mkdir()

            project = load_project(root)

            self.assertEqual(project.name, "test-with-env")
            self.assertEqual(os.environ.get("TEST_PROJECT_ENV"), "loaded_from_dotenv")


if __name__ == "__main__":
    unittest.main()
