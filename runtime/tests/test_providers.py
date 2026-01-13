"""Tests for model providers."""

import json
import unittest
from unittest.mock import patch

from trident.providers.anthropic import AnthropicProvider
from trident.providers.base import CompletionConfig, CompletionResult


class TestAnthropicBuildSchemaTool(unittest.TestCase):
    """Tests for AnthropicProvider._build_schema_tool()."""

    def setUp(self):
        self.provider = AnthropicProvider()

    def test_build_schema_tool_basic(self):
        """Test basic schema tool generation."""
        schema = {
            "status": ("string", "The status message"),
            "score": ("number", "Quality score"),
        }

        tool = self.provider._build_schema_tool(schema)

        self.assertEqual(tool["name"], "structured_output")
        self.assertEqual(tool["description"], "Return structured output")
        self.assertIn("input_schema", tool)

        input_schema = tool["input_schema"]
        self.assertEqual(input_schema["type"], "object")
        self.assertIn("properties", input_schema)
        self.assertIn("required", input_schema)

        # Check properties
        props = input_schema["properties"]
        self.assertEqual(props["status"]["type"], "string")
        self.assertEqual(props["status"]["description"], "The status message")
        self.assertEqual(props["score"]["type"], "number")
        self.assertEqual(props["score"]["description"], "Quality score")

        # Check required
        self.assertIn("status", input_schema["required"])
        self.assertIn("score", input_schema["required"])

    def test_build_schema_tool_all_types(self):
        """Test schema tool handles all JSON types."""
        schema = {
            "text": ("string", "A string"),
            "count": ("number", "A number"),
            "enabled": ("boolean", "A boolean"),
            "items": ("array", "An array"),
            "data": ("object", "An object"),
        }

        tool = self.provider._build_schema_tool(schema)
        props = tool["input_schema"]["properties"]

        self.assertEqual(props["text"]["type"], "string")
        self.assertEqual(props["count"]["type"], "number")
        self.assertEqual(props["enabled"]["type"], "boolean")
        self.assertEqual(props["items"]["type"], "array")
        self.assertEqual(props["data"]["type"], "object")

    def test_build_schema_tool_unknown_type_defaults_to_string(self):
        """Test unknown types default to string."""
        schema = {
            "field": ("unknown_type", "Some field"),
        }

        tool = self.provider._build_schema_tool(schema)
        props = tool["input_schema"]["properties"]

        self.assertEqual(props["field"]["type"], "string")

    def test_build_schema_tool_empty_description(self):
        """Test empty descriptions get default."""
        schema = {
            "field": ("string", ""),
        }

        tool = self.provider._build_schema_tool(schema)
        props = tool["input_schema"]["properties"]

        self.assertEqual(props["field"]["description"], "The field field")


class TestAnthropicProviderComplete(unittest.TestCase):
    """Tests for AnthropicProvider.complete() structured output handling."""

    def setUp(self):
        self.provider = AnthropicProvider()

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    @patch.object(AnthropicProvider, "_make_request")
    def test_complete_json_format_uses_tool(self, mock_request):
        """Test JSON format triggers tool_use with correct schema."""
        mock_request.return_value = CompletionResult(
            content='{"status": "ok", "score": 95}',
            input_tokens=10,
            output_tokens=20,
        )

        config = CompletionConfig(
            model="claude-sonnet-4-20250514",
            output_format="json",
            output_schema={
                "status": ("string", "Status message"),
                "score": ("number", "Quality score"),
            },
        )

        self.provider.complete("Test prompt", config)

        # Verify _make_request was called
        mock_request.assert_called_once()
        call_args = mock_request.call_args
        body = call_args[0][0]

        # Verify tool was added
        self.assertIn("tools", body)
        self.assertEqual(len(body["tools"]), 1)
        self.assertEqual(body["tools"][0]["name"], "structured_output")

        # Verify tool_choice was set
        self.assertIn("tool_choice", body)
        self.assertEqual(body["tool_choice"]["type"], "tool")
        self.assertEqual(body["tool_choice"]["name"], "structured_output")

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    @patch.object(AnthropicProvider, "_make_request")
    def test_complete_text_format_no_tool(self, mock_request):
        """Test text format does NOT use tool."""
        mock_request.return_value = CompletionResult(
            content="Plain text response",
            input_tokens=10,
            output_tokens=20,
        )

        config = CompletionConfig(
            model="claude-sonnet-4-20250514",
            output_format="text",
        )

        self.provider.complete("Test prompt", config)

        call_args = mock_request.call_args
        body = call_args[0][0]

        # Verify no tool was added
        self.assertNotIn("tools", body)
        self.assertNotIn("tool_choice", body)

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    @patch.object(AnthropicProvider, "_make_request")
    def test_complete_json_without_schema_no_tool(self, mock_request):
        """Test JSON format without schema does NOT use tool."""
        mock_request.return_value = CompletionResult(
            content='{"result": "data"}',
            input_tokens=10,
            output_tokens=20,
        )

        config = CompletionConfig(
            model="claude-sonnet-4-20250514",
            output_format="json",
            output_schema=None,  # No schema
        )

        self.provider.complete("Test prompt", config)

        call_args = mock_request.call_args
        body = call_args[0][0]

        # Verify no tool was added (schema is required for tool)
        self.assertNotIn("tools", body)


class TestAnthropicResponseParsing(unittest.TestCase):
    """Tests for parsing Anthropic API responses."""

    def setUp(self):
        self.provider = AnthropicProvider()

    def test_parse_text_response(self):
        """Test parsing a text response."""
        api_response = {
            "content": [{"type": "text", "text": "Hello, world!"}],
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }

        result = self.provider._parse_response(api_response, is_json=False)

        self.assertEqual(result.content, "Hello, world!")
        self.assertEqual(result.input_tokens, 10)
        self.assertEqual(result.output_tokens, 5)

    def test_parse_tool_use_response(self):
        """Test parsing a tool_use response (structured output)."""
        api_response = {
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_123",
                    "name": "structured_output",
                    "input": {"status": "success", "score": 95},
                }
            ],
            "usage": {"input_tokens": 15, "output_tokens": 10},
        }

        result = self.provider._parse_response(api_response, is_json=True)

        # Tool input should be JSON serialized
        parsed = json.loads(result.content)
        self.assertEqual(parsed["status"], "success")
        self.assertEqual(parsed["score"], 95)
        self.assertEqual(result.input_tokens, 15)
        self.assertEqual(result.output_tokens, 10)

    def test_parse_empty_content(self):
        """Test parsing response with empty content."""
        api_response = {
            "content": [],
            "usage": {"input_tokens": 5, "output_tokens": 0},
        }

        result = self.provider._parse_response(api_response, is_json=False)

        self.assertEqual(result.content, "")


class TestSchemaFlowIntegration(unittest.TestCase):
    """Integration tests verifying schema flows from prompt to provider."""

    def test_prompt_schema_to_completion_config(self):
        """Test that prompt output schema is correctly passed to CompletionConfig."""
        from trident.parser import OutputSchema, PromptNode
        from trident.providers.base import CompletionConfig

        # Create a prompt node with JSON output schema
        prompt_node = PromptNode(
            id="test_prompt",
            body="Analyze this: {{content}}",
            output=OutputSchema(
                format="json",
                fields={
                    "sentiment": ("string", "Positive, negative, or neutral"),
                    "confidence": ("number", "Confidence score 0-100"),
                },
            ),
        )

        # Build CompletionConfig the same way executor.py does (line 861-867)
        config = CompletionConfig(
            model="test-model",
            temperature=0.7,
            max_tokens=1024,
            output_format=prompt_node.output.format,
            output_schema=(
                prompt_node.output.fields if prompt_node.output.format == "json" else None
            ),
        )

        # Verify schema was passed correctly
        self.assertEqual(config.output_format, "json")
        self.assertIsNotNone(config.output_schema)
        self.assertIn("sentiment", config.output_schema)
        self.assertIn("confidence", config.output_schema)
        self.assertEqual(
            config.output_schema["sentiment"], ("string", "Positive, negative, or neutral")
        )
        self.assertEqual(config.output_schema["confidence"], ("number", "Confidence score 0-100"))

    def test_parsed_prompt_file_schema(self):
        """Test that parsing a .prompt file correctly extracts output schema."""
        import tempfile
        from pathlib import Path

        from trident.parser import parse_prompt_file

        content = """---
id: sentiment_analyzer
name: Sentiment Analyzer

output:
  format: json
  schema:
    sentiment: string, The detected sentiment
    confidence: number, Confidence score 0-100
    keywords: array, Key terms found
---
Analyze the sentiment of: {{text}}

Return JSON with sentiment, confidence, and keywords.
"""
        with tempfile.NamedTemporaryFile(suffix=".prompt", delete=False, mode="w") as f:
            f.write(content)
            f.flush()
            path = Path(f.name)

        try:
            node = parse_prompt_file(path)

            # Verify output format
            self.assertEqual(node.output.format, "json")

            # Verify schema fields
            self.assertIn("sentiment", node.output.fields)
            self.assertIn("confidence", node.output.fields)
            self.assertIn("keywords", node.output.fields)

            # Verify field types and descriptions
            self.assertEqual(node.output.fields["sentiment"], ("string", "The detected sentiment"))
            self.assertEqual(node.output.fields["confidence"], ("number", "Confidence score 0-100"))
            self.assertEqual(node.output.fields["keywords"], ("array", "Key terms found"))
        finally:
            path.unlink()

    def test_end_to_end_schema_to_tool(self):
        """Test complete flow: prompt file → parsed schema → tool definition."""
        import tempfile
        from pathlib import Path

        from trident.parser import parse_prompt_file
        from trident.providers.anthropic import AnthropicProvider
        from trident.providers.base import CompletionConfig

        content = """---
id: classifier
output:
  format: json
  schema:
    category: string, The classification category
    score: number, Confidence score
---
Classify: {{input}}
"""
        with tempfile.NamedTemporaryFile(suffix=".prompt", delete=False, mode="w") as f:
            f.write(content)
            f.flush()
            path = Path(f.name)

        try:
            # Step 1: Parse prompt
            node = parse_prompt_file(path)

            # Step 2: Build CompletionConfig (as executor does)
            config = CompletionConfig(
                model="test-model",
                output_format=node.output.format,
                output_schema=node.output.fields if node.output.format == "json" else None,
            )

            # Step 3: Build tool (as provider does)
            provider = AnthropicProvider()
            tool = provider._build_schema_tool(config.output_schema)

            # Verify complete chain
            self.assertEqual(tool["name"], "structured_output")
            props = tool["input_schema"]["properties"]
            self.assertEqual(props["category"]["type"], "string")
            self.assertEqual(props["score"]["type"], "number")
            self.assertIn("category", tool["input_schema"]["required"])
            self.assertIn("score", tool["input_schema"]["required"])
        finally:
            path.unlink()


if __name__ == "__main__":
    unittest.main()
