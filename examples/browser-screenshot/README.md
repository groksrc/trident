# Browser Screenshot Example

This example demonstrates using a Trident agent node with the `chrome-devtools-mcp` MCP server to automate browser interactions.

## Prerequisites

1. Install chrome-devtools-mcp globally:
   ```bash
   npm install -g chrome-devtools-mcp
   ```

2. Set your Anthropic API key:
   ```bash
   export ANTHROPIC_API_KEY=your-key-here
   ```

## Usage

### Validate the workflow

```bash
python -m trident project validate ./examples/browser-screenshot
```

### Dry run (no actual browser)

```bash
python -m trident project run ./examples/browser-screenshot \
  --dry-run \
  -i '{"url": "https://example.com"}'
```

### Full execution

```bash
python -m trident project run ./examples/browser-screenshot \
  -i '{"url": "https://example.com"}' \
  --trace
```

## Output

The workflow returns:
- `screenshot_path`: Filename of the captured screenshot
- `page_title`: The webpage's title
- `status`: "success" or error message

## Configuration Options

The `chrome-devtools-mcp` server supports several options:

| Option | Description |
|--------|-------------|
| `--headless` | Run without visible browser window |
| `--isolated` | Use temporary profile (cleaned up after) |
| `--viewport WxH` | Set viewport size (e.g., `1280x720`) |
| `--channel` | Chrome channel: `stable`, `beta`, `canary`, `dev` |

Example with custom viewport:
```yaml
mcp_servers:
  chrome:
    command: npx
    args:
      - chrome-devtools-mcp
      - --headless
      - --isolated
      - --viewport
      - "1920x1080"
```

## How It Works

1. **Input Node**: Accepts a URL to capture
2. **Agent Node**: Uses Claude with Chrome DevTools MCP to:
   - Launch headless Chrome
   - Navigate to the URL
   - Wait for page load
   - Capture screenshot
   - Extract page title
3. **Output Node**: Returns the results as JSON

This pattern can be extended for:
- Web scraping workflows
- Visual regression testing
- Automated form filling
- Multi-page navigation sequences
