# webinfo2md

`webinfo2md` is a CLI tool that fetches a webpage, cleans the content, asks an LLM to extract and organize key information, and writes a Markdown file.

## MVP scope

This initial version implements:

- CLI via `click`
- Static page fetching with `httpx`
- Optional Playwright fallback when installed
- Configurable Playwright mode for cookie-based or JS-heavy pages
- HTML cleaning and Markdown conversion
- Two-stage LLM pipeline with concurrent chunk extraction
- OpenAI, Anthropic, and DeepSeek client adapters
- Markdown output writer
- YAML config loading from `~/.webinfo2md/config.yaml`
- Batch processing with `--url-list`
- `--dry-run` mode for crawl/chunk/token inspection

## Install

```bash
pip install -e .
```

Optional extras:

```bash
pip install -e ".[dev,openai,anthropic,playwright]"
```

## Usage

```bash
webinfo2md \
  --url "https://example.com/interview-post" \
  --api-key "$OPENAI_API_KEY" \
  --provider openai \
  --model gpt-4o-mini \
  --prompt "提取所有面试问题，整理为八股文格式，补充标准答案" \
  --output interview_qa.md
```

Interactive mode:

```bash
webinfo2md --interactive
```

Batch mode:

```bash
webinfo2md \
  --config ~/.webinfo2md/config.yaml \
  --url-list urls.txt \
  --output-dir ./results
```

Dry run:

```bash
webinfo2md \
  --url "https://example.com/interview-post" \
  --dry-run \
  --output preview.md
```

Dynamic page example:

```bash
webinfo2md \
  --url "https://example.com/discuss/post" \
  --api-key "$OPENAI_API_KEY" \
  --force-playwright \
  --scroll \
  --cookie-file ~/.webinfo2md/cookies.json \
  --concurrency 5 \
  --output interview_qa.md
```

## Config file

Default path: `~/.webinfo2md/config.yaml`

Example:

```yaml
provider: openai
model: gpt-4o-mini
template: interview-general
chunk_size: 6000
max_concurrency: 4
force_playwright: false
pages: 5
output_dir: ./results
crawl_delay_min: 0.5
crawl_delay_max: 1.5
playwright:
  enable_scroll: false
  wait_until: networkidle
  wait_timeout_ms: 20000
  # cookie_file: ~/.webinfo2md/cookies.json
  # screenshot_path: ./debug.png
```

CLI arguments override config file values.

## Environment variables

Supported variables:

- `LLM_API_KEY`
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `DEEPSEEK_API_KEY`

## Notes

- `httpx` crawler is used first. Playwright is attempted only if content is too short and the package is installed.
- Use `--force-playwright` for JS-rendered pages or sites that require authenticated browser cookies.
- `--concurrency` controls how many chunk-level extraction requests are sent to the LLM in parallel.
- The default pipeline is designed to be generic, but the prompt templates are optimized for interview content.
- Depth crawling is implemented conservatively for same-host links.
- `--dry-run` skips API key resolution and all LLM calls.
- For batch mode, use `--output-dir`; single-file `--output` is only for one URL.
