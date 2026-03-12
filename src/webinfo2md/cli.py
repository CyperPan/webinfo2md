from __future__ import annotations

import asyncio
from pathlib import Path
import re
from urllib.parse import urlparse

import click
from click.core import ParameterSource

from webinfo2md.pipeline import WebInfo2MDPipeline
from webinfo2md.prompts.templates import TEMPLATES
from webinfo2md.utils.config import AppConfig
from webinfo2md.utils.config import PipelineConfig
from webinfo2md.utils.config import load_app_config
from webinfo2md.utils.config import merge_playwright_config
from webinfo2md.utils.config import model_to_non_null_dict
from webinfo2md.utils.config import resolve_api_key


def _prompt_if_missing(value: str | None, prompt_text: str, *, hide_input: bool = False) -> str:
    if value:
        return value
    return click.prompt(prompt_text, hide_input=hide_input)


def _resolve_option(
    ctx: click.Context,
    name: str,
    cli_value,
    file_config: AppConfig,
    *,
    config_name: str | None = None,
):
    source = ctx.get_parameter_source(name)
    if source not in {None, ParameterSource.DEFAULT, ParameterSource.DEFAULT_MAP}:
        return cli_value
    config_value = getattr(file_config, config_name or name, None)
    if config_value is not None:
        return config_value
    return cli_value


def _load_urls(url: str | None, url_list: Path | None) -> list[str]:
    if url and url_list:
        raise click.ClickException("Use either '--url' or '--url-list', not both.")
    if url_list:
        raw_lines = url_list.read_text(encoding="utf-8").splitlines()
        urls = [line.strip() for line in raw_lines if line.strip() and not line.strip().startswith("#")]
        if not urls:
            raise click.ClickException(f"No URLs found in {url_list}")
        return urls
    if url:
        return [url]
    return []


def _slugify_url(url: str, index: int) -> str:
    parsed = urlparse(url)
    host = re.sub(r"[^a-zA-Z0-9]+", "-", parsed.netloc).strip("-") or "page"
    path_parts = [re.sub(r"[^a-zA-Z0-9]+", "-", part).strip("-") for part in parsed.path.split("/") if part]
    parts = [host, *[part for part in path_parts if part]]
    stem = "-".join(parts) if parts else f"page-{index + 1}"
    stem = stem[:96].strip("-") or f"page-{index + 1}"
    return f"{index + 1:02d}-{stem}.md"


def _build_output_path(
    url: str,
    index: int,
    total: int,
    output: Path,
    output_dir: Path | None,
) -> Path:
    if total == 1 and output_dir is None:
        return output
    target_dir = output_dir or Path("results")
    return target_dir / _slugify_url(url, index)


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.pass_context
@click.option(
    "--config",
    type=click.Path(path_type=Path, dir_okay=False),
    help="Path to a YAML config file. Defaults to ~/.webinfo2md/config.yaml if present.",
)
@click.option("--url", help="Target webpage URL.")
@click.option(
    "--url-list",
    type=click.Path(path_type=Path, dir_okay=False, exists=True),
    help="File containing one URL per line.",
)
@click.option("--api-key", help="LLM API key. Falls back to environment variables.")
@click.option(
    "--provider",
    type=click.Choice(["openai", "anthropic", "deepseek"]),
    default="openai",
    show_default=True,
    help="LLM provider.",
)
@click.option("--model", help="Model name. Defaults to a provider-specific model.")
@click.option("--prompt", help="Custom generation instructions.")
@click.option(
    "--template",
    type=click.Choice(sorted(TEMPLATES.keys())),
    default="interview-general",
    show_default=True,
    help="Built-in template name.",
)
@click.option(
    "--output",
    type=click.Path(path_type=Path, dir_okay=False),
    default="output.md",
    show_default=True,
    help="Output markdown file path.",
)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path, file_okay=False),
    help="Directory for batch outputs or derived single-file outputs.",
)
@click.option("--depth", default=0, show_default=True, type=int, help="Crawl depth.")
@click.option("--pages", default=5, show_default=True, type=int, help="Max crawled pages.")
@click.option("--chunk-size", default=6000, show_default=True, type=int, help="Approximate chunk token limit.")
@click.option(
    "--concurrency",
    "-j",
    default=3,
    show_default=True,
    type=int,
    help="Max concurrent LLM extraction requests.",
)
@click.option("--force-playwright", is_flag=True, help="Skip httpx and use Playwright directly.")
@click.option(
    "--cookie-file",
    type=click.Path(path_type=Path, dir_okay=False),
    help="Path to a Playwright cookie JSON file.",
)
@click.option(
    "--scroll/--no-scroll",
    default=None,
    help="Enable or disable Playwright infinite scrolling.",
)
@click.option(
    "--screenshot",
    type=click.Path(path_type=Path, dir_okay=False),
    help="Save a Playwright screenshot for debugging.",
)
@click.option("--dry-run", is_flag=True, help="Crawl and chunk only, skipping all LLM calls.")
@click.option("--verbose", is_flag=True, help="Enable verbose logging.")
@click.option("--interactive", is_flag=True, help="Run in interactive mode.")
def main(
    ctx: click.Context,
    config: Path | None,
    url: str | None,
    url_list: Path | None,
    api_key: str | None,
    provider: str,
    model: str | None,
    prompt: str | None,
    template: str,
    output: Path,
    output_dir: Path | None,
    depth: int,
    pages: int,
    chunk_size: int,
    concurrency: int,
    force_playwright: bool,
    cookie_file: Path | None,
    scroll: bool | None,
    screenshot: Path | None,
    dry_run: bool,
    verbose: bool,
    interactive: bool,
) -> None:
    try:
        file_config = load_app_config(config)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc

    provider = _resolve_option(ctx, "provider", provider, file_config)
    model = _resolve_option(ctx, "model", model, file_config)
    prompt = _resolve_option(ctx, "prompt", prompt, file_config)
    template = _resolve_option(ctx, "template", template, file_config)
    output = _resolve_option(ctx, "output", output, file_config)
    output_dir = _resolve_option(ctx, "output_dir", output_dir, file_config)
    depth = _resolve_option(ctx, "depth", depth, file_config)
    pages = _resolve_option(ctx, "pages", pages, file_config)
    chunk_size = _resolve_option(ctx, "chunk_size", chunk_size, file_config)
    concurrency = _resolve_option(
        ctx,
        "concurrency",
        concurrency,
        file_config,
        config_name="max_concurrency",
    )
    force_playwright = _resolve_option(ctx, "force_playwright", force_playwright, file_config)
    dry_run = _resolve_option(ctx, "dry_run", dry_run, file_config)
    verbose = _resolve_option(ctx, "verbose", verbose, file_config)
    api_key = _resolve_option(ctx, "api_key", api_key, file_config)
    playwright_config = merge_playwright_config(
        file_config.playwright,
        cookie_file=cookie_file,
        enable_scroll=scroll,
        screenshot_path=screenshot,
    )

    if interactive:
        if url_list:
            raise click.ClickException("'--interactive' does not support '--url-list'.")
        url = _prompt_if_missing(url, "URL")
        if not api_key and not dry_run:
            try:
                api_key = resolve_api_key(provider, None)
            except ValueError:
                api_key = click.prompt("API Key", hide_input=True)
        prompt = prompt or click.prompt(
            "Prompt",
            default="提取所有面试问题，整理为八股文格式，补充标准答案",
            show_default=True,
        )
    urls = _load_urls(url, url_list)
    if not urls:
        raise click.ClickException("Missing option '--url' or '--url-list', or use '--interactive'.")

    explicit_output = ctx.get_parameter_source("output") not in {
        None,
        ParameterSource.DEFAULT,
        ParameterSource.DEFAULT_MAP,
    }
    file_output = model_to_non_null_dict(file_config).get("output")
    if len(urls) > 1 and (explicit_output or file_output is not None):
        raise click.ClickException("Use '--output-dir' for batch mode; '--output' is only for a single URL.")

    try:
        pipeline = WebInfo2MDPipeline()
        headers = file_config.headers or {}
        cookies = file_config.cookies or {}
        timeout = file_config.timeout if file_config.timeout is not None else 20.0
        min_content_length = (
            file_config.min_content_length
            if file_config.min_content_length is not None
            else 500
        )
        crawl_delay_min = (
            file_config.crawl_delay_min if file_config.crawl_delay_min is not None else 1.0
        )
        crawl_delay_max = (
            file_config.crawl_delay_max if file_config.crawl_delay_max is not None else 3.0
        )

        for index, item_url in enumerate(urls):
            run_config = PipelineConfig(
                url=item_url,
                api_key=api_key,
                provider=provider,
                model=model,
                prompt=prompt,
                template=template,
                output=_build_output_path(item_url, index, len(urls), output, output_dir),
                depth=depth,
                pages=pages,
                chunk_size=chunk_size,
                max_concurrency=concurrency,
                force_playwright=force_playwright,
                verbose=verbose,
                interactive=interactive,
                dry_run=dry_run,
                timeout=timeout,
                min_content_length=min_content_length,
                crawl_delay_min=crawl_delay_min,
                crawl_delay_max=crawl_delay_max,
                headers=headers,
                cookies=cookies,
                playwright=playwright_config,
            )
            result = asyncio.run(pipeline.run(run_config))
            if result.dry_run:
                click.echo(
                    f"[dry-run] {result.url} pages={result.page_count} "
                    f"chunks={result.chunk_count} estimated_tokens={result.estimated_tokens} "
                    f"output={result.output_path}"
                )
            else:
                click.echo(
                    f"[done] {result.url} output={result.output_path} "
                    f"questions={result.question_count} chunks={result.chunk_count}"
                )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
