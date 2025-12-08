"""OpenAI provider."""

import json
import os
import time
import urllib.request
import urllib.error
from typing import Any

from ..errors import ProviderError
from .base import Provider, CompletionConfig, CompletionResult


class OpenAIProvider:
    """Provider for OpenAI GPT models."""

    name = "openai"

    def __init__(self):
        self.base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com")

    def _get_api_key(self) -> str:
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise ProviderError("OPENAI_API_KEY environment variable not set", retryable=False)
        return key

    def _build_json_schema(self, schema: dict[str, tuple[str, str]]) -> dict[str, Any]:
        """Build JSON schema for structured output."""
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
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }

    def complete(self, prompt: str, config: CompletionConfig) -> CompletionResult:
        """Execute a completion request to OpenAI."""
        api_key = self._get_api_key()

        messages = [{"role": "user", "content": prompt}]

        body: dict[str, Any] = {
            "model": config.model,
            "messages": messages,
        }

        if config.max_tokens:
            body["max_tokens"] = config.max_tokens

        if config.temperature is not None:
            body["temperature"] = config.temperature

        # For JSON output, use response_format
        if config.output_format == "json":
            if config.output_schema:
                body["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "response",
                        "strict": True,
                        "schema": self._build_json_schema(config.output_schema),
                    },
                }
            else:
                body["response_format"] = {"type": "json_object"}

        return self._make_request(body, api_key)

    def _make_request(self, body: dict, api_key: str) -> CompletionResult:
        """Make API request with retry logic."""
        url = f"{self.base_url}/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
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
                    return self._parse_response(result)

            except urllib.error.HTTPError as e:
                status = e.code
                error_body = e.read().decode("utf-8", errors="replace")

                # Non-retryable errors
                if status in (400, 401, 403, 404):
                    raise ProviderError(f"OpenAI API error {status}: {error_body}", retryable=False)

                # Retryable errors
                if status in (429, 500, 502, 503, 504):
                    if attempt < 3:
                        time.sleep(delays[attempt])
                        continue
                    raise ProviderError(f"OpenAI API error {status} after retries: {error_body}", retryable=True)

                raise ProviderError(f"OpenAI API error {status}: {error_body}", retryable=False)

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

    def _parse_response(self, result: dict) -> CompletionResult:
        """Parse API response into CompletionResult."""
        choices = result.get("choices", [])
        content = ""
        if choices:
            message = choices[0].get("message", {})
            content = message.get("content", "")

        usage = result.get("usage", {})
        return CompletionResult(
            content=content,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
        )
