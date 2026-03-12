"""CLI argument additions for P2 features.

These are the new click options to add to the existing CLI.
Paste these into your existing cli.py's @click.command() decorator chain.
"""

# ============================================================
# Add these options to your existing @click.command() function:
# ============================================================
#
# @click.option(
#     "--concurrency", "-j",
#     type=int, default=None,
#     help="Max concurrent LLM requests (default: 3)"
# )
# @click.option(
#     "--force-playwright",
#     is_flag=True, default=False,
#     help="Skip httpx, go straight to Playwright browser"
# )
# @click.option(
#     "--cookie-file",
#     type=click.Path(exists=True),
#     default=None,
#     help="Path to JSON cookie file for authenticated pages"
# )
# @click.option(
#     "--scroll/--no-scroll",
#     default=None,
#     help="Enable infinite scroll for lazy-loaded content"
# )
# @click.option(
#     "--screenshot",
#     type=click.Path(),
#     default=None,
#     help="Save page screenshot for debugging (Playwright only)"
# )
#
# ============================================================
# Then in your main() handler, build the playwright config:
# ============================================================

def build_playwright_config(
    cookie_file=None,
    scroll=None,
    screenshot=None,
    base_config=None,
):
    """Build Playwright config dict from CLI args + base config.

    Args:
        cookie_file: CLI --cookie-file path
        scroll: CLI --scroll flag
        screenshot: CLI --screenshot path
        base_config: dict from config.yaml's 'playwright' section

    Returns:
        Merged Playwright config dict, or None if nothing configured.
    """
    pw = dict(base_config or {})

    if cookie_file is not None:
        pw["cookie_file"] = cookie_file
    if scroll is not None:
        pw["enable_scroll"] = scroll
    if screenshot is not None:
        pw["screenshot_path"] = screenshot

    return pw if pw else None


# ============================================================
# Example of the updated main() wiring:
# ============================================================
#
# def main(url, api_key, provider, model, prompt, output, ...,
#          concurrency, force_playwright, cookie_file, scroll, screenshot):
#
#     config = load_config(cli_overrides={
#         "api_key": api_key,
#         "provider": provider,
#         "model": model or None,
#         "prompt": prompt or None,
#         "output": output,
#         "max_concurrency": concurrency,
#         "force_playwright": force_playwright,
#     })
#
#     config.playwright = build_playwright_config(
#         cookie_file=cookie_file,
#         scroll=scroll,
#         screenshot=screenshot,
#         base_config=config.playwright,
#     ) or {}
#
#     pipeline_config = PipelineConfig(
#         url=url,
#         api_key=config.resolve_api_key(),
#         provider=config.provider,
#         model=config.resolve_model(),
#         prompt=config.prompt,
#         output=config.output,
#         max_concurrency=config.max_concurrency or 3,
#         force_playwright=config.force_playwright,
#         playwright_config=config.get_playwright_config(),
#         dry_run=config.dry_run,
#     )
#
#     asyncio.run(run_pipeline(pipeline_config))
