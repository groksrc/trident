"""Tests for agent node functionality (SPEC-3)."""

import os
import tempfile
import unittest
from pathlib import Path

from trident.executor import run
from trident.parser import AgentNode, MCPServerConfig, OutputSchema, PromptNode
from trident.project import Edge, InputNode, OutputNode, Project


class TestAgentNodeDryRun(unittest.TestCase):
    """Tests for agent node dry-run execution."""

    def _make_agent_project(self) -> Project:
        """Create a project with an agent node for testing."""
        project = Project(name="test-agents", root=Path("."))
        project.input_nodes["input"] = InputNode(id="input")
        project.output_nodes["output"] = OutputNode(id="output")

        # Create agent node with prompt
        prompt_node = PromptNode(
            id="tester",
            body="Test the app at {{app_url}}",
            output=OutputSchema(
                format="json",
                fields={
                    "status": ("string", "Test status"),
                    "passed": ("array", "Passed tests"),
                },
            ),
        )

        agent = AgentNode(
            id="tester",
            prompt_path="prompts/tester.prompt",
            allowed_tools=["Read", "Glob"],
            max_turns=10,
            prompt_node=prompt_node,  # Pre-loaded for testing
        )
        project.agents["tester"] = agent

        project.edges["e1"] = Edge(id="e1", from_node="input", to_node="tester")
        project.edges["e2"] = Edge(id="e2", from_node="tester", to_node="output")
        project.entrypoints = ["input"]

        return project

    def test_dry_run_agent_json_output(self):
        """Dry run generates mock JSON output for agent nodes."""
        project = self._make_agent_project()
        result = run(project, dry_run=True, inputs={"app_url": "http://localhost:3000"})

        self.assertTrue(result.success)
        # Check that agent node executed
        agent_trace = next((n for n in result.trace.nodes if n.id == "tester"), None)
        self.assertIsNotNone(agent_trace)
        self.assertIn("status", agent_trace.output)
        self.assertIn("passed", agent_trace.output)

    def test_dry_run_agent_text_output(self):
        """Dry run generates mock text output for text-format agents."""
        project = self._make_agent_project()
        # Change to text output
        project.agents["tester"].prompt_node.output = OutputSchema(format="text")

        result = run(project, dry_run=True, inputs={"app_url": "http://localhost:3000"})

        self.assertTrue(result.success)
        agent_trace = next((n for n in result.trace.nodes if n.id == "tester"), None)
        self.assertIsNotNone(agent_trace)
        self.assertIn("text", agent_trace.output)
        self.assertIn("DRY RUN", agent_trace.output["text"])


class TestAgentNodeConfig(unittest.TestCase):
    """Tests for agent node configuration parsing."""

    def test_mcp_server_config(self):
        """MCP server configuration is properly structured."""
        config = MCPServerConfig(
            command="npx",
            args=["@playwright/mcp@latest"],
            env={"DEBUG": "true"},
        )

        self.assertEqual(config.command, "npx")
        self.assertEqual(config.args, ["@playwright/mcp@latest"])
        self.assertEqual(config.env, {"DEBUG": "true"})

    def test_agent_node_defaults(self):
        """Agent node has sensible defaults."""
        agent = AgentNode(id="test", prompt_path="prompts/test.prompt")

        self.assertEqual(agent.max_turns, 50)
        self.assertEqual(agent.permission_mode, "acceptEdits")
        self.assertEqual(agent.allowed_tools, [])
        self.assertEqual(agent.mcp_servers, {})
        self.assertIsNone(agent.cwd)


class TestJsonParsing(unittest.TestCase):
    """Tests for JSON response parsing."""

    def test_parse_direct_json(self):
        """Direct JSON is parsed correctly."""
        from trident.agents import _parse_json_response

        result = _parse_json_response('{"status": "pass", "count": 5}')
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["count"], 5)

    def test_parse_json_code_block(self):
        """JSON in ```json block is extracted."""
        from trident.agents import _parse_json_response

        text = """Here's the result:

```json
{"status": "pass", "items": [1, 2, 3]}
```

That's all!"""
        result = _parse_json_response(text)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["items"], [1, 2, 3])

    def test_parse_plain_code_block(self):
        """JSON in plain ``` block is extracted."""
        from trident.agents import _parse_json_response

        text = """Result:
```
{"key": "value"}
```"""
        result = _parse_json_response(text)
        self.assertEqual(result["key"], "value")

    def test_parse_array_wrapped(self):
        """Top-level arrays are wrapped in dict."""
        from trident.agents import _parse_json_response

        result = _parse_json_response("[1, 2, 3]")
        self.assertEqual(result["result"], [1, 2, 3])

    def test_parse_invalid_json_raises(self):
        """Invalid JSON raises JSONDecodeError."""
        import json

        from trident.agents import _parse_json_response

        with self.assertRaises(json.JSONDecodeError):
            _parse_json_response("This is not JSON at all")

    def test_parse_code_block_with_language(self):
        """Code block with language identifier is handled."""
        from trident.agents import _parse_json_response

        text = """```javascript
{"language": "js"}
```"""
        result = _parse_json_response(text)
        self.assertEqual(result["language"], "js")


class TestSchemaValidation(unittest.TestCase):
    """Tests for agent output schema validation."""

    def test_validation_missing_field(self):
        """Missing required field raises error."""
        from trident.agents import AgentExecutionError, _validate_agent_output

        schema = {"name": ("string", "User name"), "age": ("number", "User age")}

        with self.assertRaises(AgentExecutionError) as ctx:
            _validate_agent_output({"name": "Alice"}, schema, "test_agent")

        self.assertIn("age", str(ctx.exception))
        self.assertIn("missing", str(ctx.exception).lower())

    def test_validation_wrong_type(self):
        """Wrong field type raises error."""
        from trident.agents import AgentExecutionError, _validate_agent_output

        schema = {"count": ("integer", "Item count")}

        with self.assertRaises(AgentExecutionError) as ctx:
            _validate_agent_output({"count": "five"}, schema, "test_agent")

        self.assertIn("count", str(ctx.exception))
        self.assertIn("integer", str(ctx.exception))

    def test_validation_success(self):
        """Valid data passes validation."""
        from trident.agents import _validate_agent_output

        schema = {
            "status": ("string", "Status"),
            "count": ("number", "Count"),
            "items": ("array", "Items"),
            "active": ("boolean", "Active flag"),
        }

        # Should not raise
        _validate_agent_output(
            {"status": "ok", "count": 42, "items": [1, 2], "active": True},
            schema,
            "test_agent",
        )


class TestJsonSchemaBuilder(unittest.TestCase):
    """Tests for JSON schema builder for structured outputs."""

    def test_build_basic_schema(self):
        """Build JSON schema from field definitions."""
        from trident.agents import _build_json_schema

        fields = {
            "name": ("string", "User name"),
            "age": ("number", "User age"),
            "active": ("boolean", "Active flag"),
        }

        schema = _build_json_schema(fields)

        self.assertEqual(schema["type"], "object")
        self.assertEqual(schema["additionalProperties"], False)
        self.assertEqual(set(schema["required"]), {"name", "age", "active"})

        props = schema["properties"]
        self.assertEqual(props["name"]["type"], "string")
        self.assertEqual(props["name"]["description"], "User name")
        self.assertEqual(props["age"]["type"], "number")
        self.assertEqual(props["active"]["type"], "boolean")

    def test_build_schema_all_types(self):
        """Build schema with all supported types."""
        from trident.agents import _build_json_schema

        fields = {
            "str_field": ("string", ""),
            "num_field": ("number", ""),
            "int_field": ("integer", ""),
            "bool_field": ("boolean", ""),
            "arr_field": ("array", ""),
            "obj_field": ("object", ""),
        }

        schema = _build_json_schema(fields)
        props = schema["properties"]

        self.assertEqual(props["str_field"]["type"], "string")
        self.assertEqual(props["num_field"]["type"], "number")
        self.assertEqual(props["int_field"]["type"], "integer")
        self.assertEqual(props["bool_field"]["type"], "boolean")
        self.assertEqual(props["arr_field"]["type"], "array")
        self.assertEqual(props["obj_field"]["type"], "object")

    def test_build_schema_empty_description(self):
        """Schema without descriptions still valid."""
        from trident.agents import _build_json_schema

        fields = {"result": ("string", "")}
        schema = _build_json_schema(fields)

        # Empty description should not add key
        self.assertNotIn("description", schema["properties"]["result"])


class TestAgentInDAG(unittest.TestCase):
    """Tests for agent nodes in DAG structure."""

    def test_agent_node_in_dag(self):
        """Agent nodes are properly added to DAG."""
        from trident.dag import build_dag

        project = Project(name="test", root=Path("."))
        project.input_nodes["input"] = InputNode(id="input")
        project.output_nodes["output"] = OutputNode(id="output")
        project.agents["agent1"] = AgentNode(
            id="agent1",
            prompt_path="prompts/agent1.prompt",
        )
        project.edges["e1"] = Edge(id="e1", from_node="input", to_node="agent1")
        project.edges["e2"] = Edge(id="e2", from_node="agent1", to_node="output")

        dag = build_dag(project)

        self.assertIn("agent1", dag.nodes)
        self.assertEqual(dag.nodes["agent1"].type, "agent")
        self.assertIn("agent1", dag.execution_order)

    def test_agent_visualization_symbol(self):
        """Agent nodes show [A] symbol in visualization."""
        from trident.dag import build_dag, visualize_dag

        project = Project(name="test", root=Path("."))
        project.input_nodes["input"] = InputNode(id="input")
        project.agents["tester"] = AgentNode(id="tester", prompt_path="p.prompt")
        project.edges["e1"] = Edge(id="e1", from_node="input", to_node="tester")

        dag = build_dag(project)
        viz = visualize_dag(dag)

        self.assertIn("[A]", viz)
        self.assertIn("tester", viz)


class TestAgentProjectLoading(unittest.TestCase):
    """Tests for loading projects with agent nodes."""

    def test_load_agent_with_all_options(self):
        """Agent node with all configuration options loads correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            (root / "agent.tml").write_text("""
trident: "0.2"
name: full-agent-test
nodes:
  analyzer:
    type: agent
    prompt: prompts/analyzer.prompt
    allowed_tools:
      - Read
      - Write
      - Bash
    mcp_servers:
      github:
        command: npx
        args:
          - "@modelcontextprotocol/server-github"
        env:
          GITHUB_TOKEN: "${GITHUB_TOKEN}"
    max_turns: 100
    permission_mode: bypassPermissions
    cwd: /tmp/workspace
""")

            (root / "prompts").mkdir()
            (root / "prompts" / "analyzer.prompt").write_text("""---
id: analyzer
---
Analyze the code.
""")

            from trident.project import load_project

            project = load_project(root)
            agent = project.agents["analyzer"]

            self.assertEqual(agent.allowed_tools, ["Read", "Write", "Bash"])
            self.assertEqual(agent.max_turns, 100)
            self.assertEqual(agent.permission_mode, "bypassPermissions")
            self.assertEqual(agent.cwd, "/tmp/workspace")
            self.assertIn("github", agent.mcp_servers)
            self.assertEqual(
                agent.mcp_servers["github"].args,
                ["@modelcontextprotocol/server-github"],
            )


class TestAgentResultDataclass(unittest.TestCase):
    """Tests for AgentResult dataclass (Phase 3)."""

    def test_agent_result_fields(self):
        """AgentResult has all expected fields."""
        from trident.agents import AgentResult

        result = AgentResult(
            output={"status": "pass"},
            session_id="sess-123",
            num_turns=5,
            cost_usd=0.0123,
            tokens={"input": 100, "output": 50},
        )

        self.assertEqual(result.output, {"status": "pass"})
        self.assertEqual(result.session_id, "sess-123")
        self.assertEqual(result.num_turns, 5)
        self.assertEqual(result.cost_usd, 0.0123)
        self.assertEqual(result.tokens["input"], 100)
        self.assertEqual(result.tokens["output"], 50)

    def test_agent_result_defaults(self):
        """AgentResult has sensible defaults."""
        from trident.agents import AgentResult

        result = AgentResult(output={"text": "hello"})

        self.assertIsNone(result.session_id)
        self.assertEqual(result.num_turns, 0)
        self.assertIsNone(result.cost_usd)
        self.assertEqual(result.tokens, {})


class TestNodeTraceAgentFields(unittest.TestCase):
    """Tests for NodeTrace agent-specific fields (Phase 3)."""

    def test_node_trace_has_agent_fields(self):
        """NodeTrace includes cost, session, and num_turns fields."""
        from trident.executor import NodeTrace

        trace = NodeTrace(
            id="agent1",
            start_time="2025-01-05T00:00:00Z",
            cost_usd=0.05,
            session_id="sess-abc",
            num_turns=3,
        )

        self.assertEqual(trace.cost_usd, 0.05)
        self.assertEqual(trace.session_id, "sess-abc")
        self.assertEqual(trace.num_turns, 3)

    def test_node_trace_agent_defaults(self):
        """NodeTrace agent fields have sensible defaults."""
        from trident.executor import NodeTrace

        trace = NodeTrace(id="test", start_time="2025-01-05T00:00:00Z")

        self.assertIsNone(trace.cost_usd)
        self.assertIsNone(trace.session_id)
        self.assertEqual(trace.num_turns, 0)


class TestExecutorAgentParameters(unittest.TestCase):
    """Tests for executor agent-related parameters (Phase 3)."""

    def test_run_accepts_resume_sessions(self):
        """run() accepts resume_sessions parameter."""
        from trident.executor import run

        # Just check it accepts the parameter without error
        project = Project(name="test", root=Path("."))
        project.input_nodes["input"] = InputNode(id="input")
        project.output_nodes["output"] = OutputNode(id="output")
        project.edges["e1"] = Edge(id="e1", from_node="input", to_node="output")
        project.entrypoints = ["input"]

        result = run(
            project,
            inputs={},
            dry_run=True,
            resume_sessions={"agent1": "sess-123"},
        )

        self.assertTrue(result.success)

    def test_run_accepts_on_agent_message(self):
        """run() accepts on_agent_message callback."""
        from trident.executor import run

        messages = []

        def callback(msg_type: str, content):
            messages.append((msg_type, content))

        project = Project(name="test", root=Path("."))
        project.input_nodes["input"] = InputNode(id="input")
        project.output_nodes["output"] = OutputNode(id="output")
        project.edges["e1"] = Edge(id="e1", from_node="input", to_node="output")
        project.entrypoints = ["input"]

        result = run(
            project,
            inputs={},
            dry_run=True,
            on_agent_message=callback,
        )

        self.assertTrue(result.success)
        # No agents in this project, so no messages expected
        self.assertEqual(messages, [])


@unittest.skipUnless(
    os.environ.get("ANTHROPIC_API_KEY") and os.environ.get("RUN_INTEGRATION_TESTS"),
    "Integration tests require ANTHROPIC_API_KEY and RUN_INTEGRATION_TESTS=1",
)
class TestAgentIntegration(unittest.TestCase):
    """Integration tests that require Claude Agent SDK and API key."""

    def test_agent_execution_with_tools(self):
        """Agent can use tools to read files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            (root / "agent.tml").write_text("""
trident: "0.2"
name: integration-test
nodes:
  input:
    type: input
  reader:
    type: agent
    prompt: prompts/reader.prompt
    allowed_tools:
      - Read
      - Glob
    max_turns: 10
  output:
    type: output
edges:
  e1:
    from: input
    to: reader
  e2:
    from: reader
    to: output
    mapping:
      result: result
""")

            (root / "prompts").mkdir()
            (root / "prompts" / "reader.prompt").write_text("""---
id: reader
output:
  format: json
  schema:
    result:
      type: string
      description: What was found
---
Use Glob to list files in the current directory. Return {"result": "found N files"}.
""")

            # Create a test file to find
            (root / "test.txt").write_text("hello world")

            from trident.executor import run
            from trident.project import load_project

            project = load_project(root)
            result = run(project, inputs={})

            self.assertTrue(result.success)
            self.assertIn("result", result.outputs.get("output", {}))


if __name__ == "__main__":
    unittest.main()
