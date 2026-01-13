# Structured Output Example

This example demonstrates Trident's JSON structured output feature, which uses Claude's tool_use to enforce schema-compliant responses.

## How It Works

1. The prompt defines an `output.schema` with typed fields
2. Trident converts this to a Claude tool definition
3. Claude is forced to call the tool with matching JSON
4. The response is validated against the schema

## Running

```bash
# Validate the project
python -m trident project validate ./examples/structured-output

# Dry run (no API calls)
python -m trident project run ./examples/structured-output \
  --input '{"text": "I love this product!"}' \
  --dry-run

# Real execution
python -m trident project run ./examples/structured-output \
  --input '{"text": "I love this product! Best purchase ever."}' \
  --verbose
```

## Expected Output

```json
{
  "sentiment": "positive",
  "confidence": 95,
  "reasoning": "The text contains strong positive language like 'love' and 'best purchase ever'.",
  "keywords": ["love", "best purchase ever"]
}
```

## Schema Definition

The prompt file (`prompts/analyze.prompt`) defines the output schema:

```yaml
output:
  format: json
  schema:
    sentiment:
      type: string
      description: One of positive, negative, or neutral
    confidence:
      type: number
      description: Confidence score from 0 to 100
    reasoning:
      type: string
      description: Brief explanation of the sentiment classification
    keywords:
      type: array
      description: Key words or phrases that influenced the classification
```

This schema is converted to a Claude tool with `tool_choice: {"type": "tool", "name": "structured_output"}` to ensure compliant responses.
