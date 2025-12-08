"""Anthropic Claude provider."""

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from ..errors import ProviderError
from .base import CompletionConfig, CompletionResult


class AnthropicProvider:
    """Provider for Anthropic Claude models."""

    name = "anthropic"

    def __init__(self):
        self.base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
        self.api_version = "2023-06-01"

    def _get_api_key(self) -> str:
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise ProviderError("ANTHROPIC_API_KEY environment variable not set", retryable=False)
        return key

    def _build_schema_tool(self, schema: dict[str, tuple[str, str]]) -> dict[str, Any]:
        """Build a tool definition for structured output."""
        properties = {}
        required = []

        for field_name, (field_type, field_desc) in schema.items():
            json_type = {
                "string": "string",
                "number": "number",
                "boolean": "boolean",
                "array": "array",
                "object": "object",
            }.get(field_type, "string")

            properties[field_name] = {
                "type": json_type,
                "description": field_desc or f"The {field_name} field",
            }
            required.append(field_name)

        return {
            "name": "structured_output",
            "description": "Return structured output",
            "input_schema": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        }

    def complete(self, prompt: str, config: CompletionConfig) -> CompletionResult:
        """Execute a completion request to Claude."""
        api_key = self._get_api_key()

        messages = [{"role": "user", "content": prompt}]

        body: dict[str, Any] = {
            "model": config.model,
            "messages": messages,
            "max_tokens": config.max_tokens or 4096,
        }

        if config.temperature is not None:
            body["temperature"] = config.temperature

        # For JSON output, use tool_use to force structured response
        if config.output_format == "json" and config.output_schema:
            tool = self._build_schema_tool(config.output_schema)
            body["tools"] = [tool]
            body["tool_choice"] = {"type": "tool", "name": "structured_output"}

        return self._make_request(body, api_key, config.output_format == "json")

    def _make_request(self, body: dict, api_key: str, is_json: bool) -> CompletionResult:
        """Make API request with retry logic."""
        url = f"{self.base_url}/v1/messages"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": self.api_version,
        }

        delays = [1, 2, 4]  # Retry delays in seconds

        for attempt in range(4):  # 1 initial + 3 retries
            try:
                req = urllib.request.Request(
                    url,
                    data=json.dumps(body).encode("utf-8"),
                    headers=headers,
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=120) as response:
                    result = json.loads(response.read().decode("utf-8"))
                    return self._parse_response(result, is_json)

            except urllib.error.HTTPError as e:
                status = e.code
                error_body = e.read().decode("utf-8", errors="replace")

                # Non-retryable errors
                if status in (400, 401, 403, 404):
                    raise ProviderError(
                        f"Anthropic API error {status}: {error_body}", retryable=False
                    )

                # Retryable errors
                if status in (429, 500, 502, 503, 504):
                    if attempt < 3:
                        time.sleep(delays[attempt])
                        continue
                    raise ProviderError(
                        f"Anthropic API error {status} after retries: {error_body}", retryable=True
                    )

                raise ProviderError(f"Anthropic API error {status}: {error_body}", retryable=False)

            except urllib.error.URLError as e:
                if attempt < 3:
                    time.sleep(delays[attempt])
                    continue
                raise ProviderError(f"Network error: {e}", retryable=True)

            except TimeoutError:
                if attempt < 3:
                    time.sleep(delays[attempt])
                    continue
                raise ProviderError("Request timed out after retries", retryable=True)

        raise ProviderError("Max retries exceeded", retryable=True)

    def _parse_response(self, result: dict, is_json: bool) -> CompletionResult:
        """Parse API response into CompletionResult."""
        content = ""

        for block in result.get("content", []):
            if block.get("type") == "text":
                content = block.get("text", "")
                break
            elif block.get("type") == "tool_use":
                # For structured output, return the tool input as JSON
                content = json.dumps(block.get("input", {}))
                break

        usage = result.get("usage", {})
        return CompletionResult(
            content=content,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
        )
