from __future__ import annotations

import asyncio
from pathlib import Path
import re
from urllib.parse import urlparse

import click
from click.core import ParameterSource

from webinfo2md.llm.factory import create_client
from webinfo2md.pipeline import WebInfo2MDPipeline
from webinfo2md.prompts.templates import TEMPLATES
from webinfo2md.utils.config import AppConfig
from webinfo2md.utils.config import DEFAULT_MODELS
from webinfo2md.utils.config import PipelineConfig
from webinfo2md.utils.config import load_app_config
from webinfo2md.utils.config import merge_playwright_config
from webinfo2md.utils.config import model_to_non_null_dict
from webinfo2md.utils.config import resolve_api_key
from webinfo2md.utils.config import SUPPORTED_PROVIDERS


def _prompt_if_missing(value: str | None, prompt_text: str, *, hide_input: bool = False) -> str:
    if value:
        return value
    return click.prompt(prompt_text, hide_input=hide_input)


def _split_url_text(raw: str) -> list[str]:
    return [item.strip() for item in re.split(r"[\s,]+", raw.strip()) if item.strip()]


def _prompt_for_urls(existing_urls: list[str]) -> list[str]:
    if existing_urls:
        return existing_urls
    raw = click.prompt(
        "网站 URL（可一次输入多个，使用空格或逗号分隔）",
        type=str,
    )
    urls = _split_url_text(raw)
    if not urls:
        raise click.ClickException("至少需要输入一个网站 URL。")
    return urls


def _prompt_for_prompt(prompt: str | None) -> str:
    if prompt:
        return prompt
    return click.prompt(
        "希望获取并整理什么信息",
        default="提取所有面试问题，整理为八股文格式，补充标准答案",
        show_default=True,
    )


def _prompt_for_provider(current: str) -> str:
    """Interactively ask the user to choose an LLM provider."""
    provider_list = list(SUPPORTED_PROVIDERS)
    click.echo("\n可选的 LLM 提供商:")
    for i, p in enumerate(provider_list, 1):
        default_model = DEFAULT_MODELS.get(p, "")
        marker = " (当前)" if p == current else ""
        click.echo(f"  {i}. {p} (默认模型: {default_model}){marker}")
    choice = click.prompt(
        "请选择提供商编号或名称",
        default=current,
        show_default=True,
    )
    # Accept number or name
    if choice.isdigit():
        idx = int(choice) - 1
        if 0 <= idx < len(provider_list):
            return provider_list[idx]
    if choice in provider_list:
        return choice
    click.echo(f"未识别的选项 '{choice}'，使用默认: {current}")
    return current


def _prompt_for_model(provider: str, current: str | None) -> str | None:
    """Interactively ask the user to choose or confirm a model."""
    default = current or DEFAULT_MODELS.get(provider, "")
    model = click.prompt(
        f"模型名称",
        default=default,
        show_default=True,
    )
    return model if model else default


def _validate_api_key(provider: str, api_key: str, model: str | None) -> bool:
    """Make a lightweight test call to validate the API key and model."""
    try:
        client = create_client(provider, api_key, model)
        return asyncio.run(client.validate())
    except Exception:
        return False


def _resolve_or_prompt_api_key(provider: str, api_key: str | None, *, dry_run: bool) -> str | None:
    if dry_run:
        return api_key
    try:
        return resolve_api_key(provider, api_key)
    except ValueError:
        return click.prompt(f"{provider.upper()} API Key", hide_input=True)


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
    type=click.Choice(list(SUPPORTED_PROVIDERS)),
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
    default=None,
    help="Output markdown file path. Defaults to output/<slug>.md",
)
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path, file_okay=False),
    help="Directory for batch outputs or derived single-file outputs.",
)
@click.option("--depth", default=0, show_default=True, type=int, help="Crawl depth.")
@click.option("--pages", default=5, show_default=True, type=int, help="Max crawled pages.")
@click.option("--chunk-size", default=3000, show_default=True, type=int, help="Approximate chunk token limit.")
@click.option(
    "--concurrency",
    "-j",
    default=5,
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
@click.option(
    "--user-data-dir",
    type=click.Path(path_type=Path, file_okay=False),
    help="Persistent browser profile directory (preserves login state across runs).",
)
@click.option(
    "--no-headless",
    is_flag=True,
    help="Show browser window (useful for manual login with --user-data-dir).",
)
@click.option(
    "--intercept-api",
    is_flag=True,
    help="Intercept API responses for structured data (useful for SPAs like xiaohongshu).",
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
    user_data_dir: Path | None,
    no_headless: bool,
    intercept_api: bool,
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
        user_data_dir=user_data_dir,
        intercept_api=intercept_api if intercept_api else None,
    )
    # Handle --no-headless flag
    if no_headless:
        if playwright_config is None:
            from webinfo2md.utils.config import PlaywrightConfig as _PC
            playwright_config = _PC(headless=False)
        else:
            playwright_config = playwright_config.model_copy(update={"headless": False})
    # --user-data-dir implies --force-playwright
    if user_data_dir:
        force_playwright = True

    if interactive and url_list:
        raise click.ClickException("'--interactive' does not support '--url-list'.")

    should_prompt_inputs = interactive or (not url and not url_list)
    if should_prompt_inputs:
        # Step 1: Choose provider and model interactively
        if interactive:
            provider = _prompt_for_provider(provider)
            model = _prompt_for_model(provider, model)

        # Step 2: Get API key
        api_key = _resolve_or_prompt_api_key(provider, api_key, dry_run=dry_run)

        # Step 3: Validate API key and model (unless dry-run)
        if not dry_run and api_key:
            click.echo("正在验证 API Key 和模型...")
            if _validate_api_key(provider, api_key, model):
                click.echo("✓ 验证通过")
            else:
                click.echo("✗ API Key 或模型验证失败，请检查后重试。")
                if not click.confirm("是否仍要继续？", default=False):
                    raise click.ClickException("API Key 验证失败，已退出。")

        # Step 4: Get URLs
        urls = _prompt_for_urls(_load_urls(url, url_list))
    else:
        urls = _load_urls(url, url_list)
        if not urls:
            raise click.ClickException("Missing option '--url' or '--url-list', or use '--interactive'.")
        api_key = _resolve_or_prompt_api_key(provider, api_key, dry_run=dry_run)

    # Step 5: Get prompt (what info to extract)
    if not dry_run:
        prompt = _prompt_for_prompt(prompt)

    if len(urls) > 1 and output_dir is not None:
        raise click.ClickException("多个 URL 现在会合并到一个 Markdown 文件中，请使用 '--output' 而不是 '--output-dir'。")

    # Default output to output/ directory if not specified
    if output is None:
        output_dir_path = Path("output")
        if len(urls) == 1:
            output = output_dir_path / _slugify_url(urls[0], 0)
        else:
            output = output_dir_path / "merged.md"

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

        resolved_output = (
            _build_output_path(urls[0], 0, 1, output, output_dir)
            if len(urls) == 1
            else output
        )
        run_config = PipelineConfig(
            url=urls[0],
            api_key=api_key,
            provider=provider,
            model=model,
            prompt=prompt,
            template=template,
            output=resolved_output,
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
        result = asyncio.run(pipeline.run(run_config, urls=urls))
        if result.dry_run:
            click.echo(
                f"[dry-run] sources={result.source_count} pages={result.page_count} "
                f"chunks={result.chunk_count} estimated_tokens={result.estimated_tokens} "
                f"output={result.output_path}"
            )
        else:
            click.echo(
                f"[done] sources={result.source_count} output={result.output_path} "
                f"questions={result.question_count} chunks={result.chunk_count}"
            )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
