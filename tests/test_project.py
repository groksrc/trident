"""Tests for project loading."""

import tempfile
import unittest
from pathlib import Path
from trident.project import load_project, ParseError, ValidationError


class TestProjectLoading(unittest.TestCase):
    def test_load_minimal_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            # Create trident.yaml
            (root / "trident.yaml").write_text("""
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

            (root / "trident.yaml").write_text("""
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
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(ParseError):
                load_project(tmpdir)

    def test_missing_required_field_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "trident.yaml").write_text("""
name: no-version
""")
            with self.assertRaises(ValidationError):
                load_project(root)


if __name__ == "__main__":
    unittest.main()
