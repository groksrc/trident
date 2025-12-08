"""Tests for .prompt file parser."""

import tempfile
import unittest
from pathlib import Path
from trident.parser import parse_prompt_file, parse_yaml_simple, ParseError


class TestYamlParser(unittest.TestCase):
    def test_simple_values(self):
        yaml = """
name: test
count: 42
enabled: true
"""
        result = parse_yaml_simple(yaml)
        self.assertEqual(result["name"], "test")
        self.assertEqual(result["count"], 42)
        self.assertEqual(result["enabled"], True)

    def test_nested_dict(self):
        yaml = """
outer:
  inner: value
"""
        result = parse_yaml_simple(yaml)
        self.assertEqual(result["outer"]["inner"], "value")

    def test_quoted_string(self):
        yaml = """
message: "Hello, World!"
"""
        result = parse_yaml_simple(yaml)
        self.assertEqual(result["message"], "Hello, World!")


class TestPromptParser(unittest.TestCase):
    def test_parse_basic_prompt(self):
        content = """---
id: test
name: Test Prompt
model: anthropic/claude-sonnet-4-20250514
---
Hello {{name}}!
"""
        with tempfile.NamedTemporaryFile(suffix=".prompt", delete=False, mode="w") as f:
            f.write(content)
            f.flush()
            path = Path(f.name)

        try:
            node = parse_prompt_file(path)
            self.assertEqual(node.id, "test")
            self.assertEqual(node.name, "Test Prompt")
            self.assertEqual(node.model, "anthropic/claude-sonnet-4-20250514")
            self.assertEqual(node.body, "Hello {{name}}!")
        finally:
            path.unlink()

    def test_parse_with_schema(self):
        content = """---
id: classify
output:
  format: json
  schema:
    intent: string, The classified intent
    confidence: number, Confidence score
---
Classify this.
"""
        with tempfile.NamedTemporaryFile(suffix=".prompt", delete=False, mode="w") as f:
            f.write(content)
            f.flush()
            path = Path(f.name)

        try:
            node = parse_prompt_file(path)
            self.assertEqual(node.output.format, "json")
            self.assertIn("intent", node.output.fields)
            self.assertEqual(node.output.fields["intent"], ("string", "The classified intent"))
        finally:
            path.unlink()

    def test_missing_id_raises(self):
        content = """---
name: No ID
---
Body
"""
        with tempfile.NamedTemporaryFile(suffix=".prompt", delete=False, mode="w") as f:
            f.write(content)
            f.flush()
            path = Path(f.name)

        try:
            with self.assertRaises(ParseError):
                parse_prompt_file(path)
        finally:
            path.unlink()


if __name__ == "__main__":
    unittest.main()
