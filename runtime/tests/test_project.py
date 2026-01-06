"""Tests for project loading."""

import tempfile
import unittest
from pathlib import Path

from trident.project import ParseError, ValidationError, load_project


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
    status: string, Test status
    passed: array, Passed tests
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


if __name__ == "__main__":
    unittest.main()
