"""Configuration management with YAML support and Playwright options.

Config precedence: CLI args > env vars > config file > defaults.

Example ~/.webinfo2md/config.yaml:

    default_provider: deepseek
    default_model: deepseek-chat
    chunk_size: 6000
    max_concurrency: 3
    crawl_delay: 2
    max_pages: 10
    output_dir: ~/Documents/interview-notes/

    playwright:
      headless: true
      enable_scroll: false
      scroll_max_iterations: 10
      scroll_pause_ms: 1500
      wait_strategy: networkidle
      wait_timeout_ms: 15000
      cookie_file: ~/.webinfo2md/cookies.json
      headers:
        Accept-Language: "zh-CN,zh;q=0.9,en;q=0.8"
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


DEFAULT_CONFIG_PATH = Path("~/.webinfo2md/config.yaml").expanduser()

# Default models per provider
DEFAULT_MODELS = {
    "openai": "gpt-4o",
    "anthropic": "claude-sonnet-4-20250514",
    "deepseek": "deepseek-chat",
}


@dataclass
class AppConfig:
    """Full application configuration."""

    # --- Core ---
    api_key: str = ""
    provider: str = "openai"
    model: str = ""
    prompt: str = ""
    output: str = "output.md"
    output_dir: str = ""

    # --- Crawling ---
    depth: int = 0
    max_pages: int = 5
    min_content_length: int = 500
    force_playwright: bool = False

    # --- Processing ---
    chunk_size: int = 6000
    max_concurrency: int = 3
    template: str = "interview-general"

    # --- Playwright ---
    playwright: dict[str, Any] = field(default_factory=dict)

    # --- Runtime ---
    dry_run: bool = False
    verbose: bool = False

    def resolve_model(self) -> str:
        """Get model name, falling back to provider default."""
        return self.model or DEFAULT_MODELS.get(self.provider, "gpt-4o")

    def resolve_api_key(self) -> str:
        """Get API key from config or environment."""
        if self.api_key:
            return self.api_key
        env_keys = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
        }
        env_name = env_keys.get(self.provider, "LLM_API_KEY")
        return os.environ.get(env_name, os.environ.get("LLM_API_KEY", ""))

    def get_playwright_config(self) -> Optional[dict[str, Any]]:
        """Return Playwright config dict if any options are set."""
        if self.playwright:
            return self.playwright
        return None


def load_config(
    config_path: Optional[str] = None,
    cli_overrides: Optional[dict[str, Any]] = None,
) -> AppConfig:
    """Load config from YAML file, then apply CLI overrides.

    Args:
        config_path: Explicit path, or None to use default location.
        cli_overrides: Dict of CLI-provided values (None values are skipped).

    Returns:
        Merged AppConfig.
    """
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH

    file_data: dict[str, Any] = {}
    if path.exists():
        with open(path) as f:
            file_data = yaml.safe_load(f) or {}

    # Map config file keys to AppConfig fields
    key_map = {
        "default_provider": "provider",
        "default_model": "model",
        "chunk_size": "chunk_size",
        "max_concurrency": "max_concurrency",
        "max_pages": "max_pages",
        "output_dir": "output_dir",
        "min_content_length": "min_content_length",
        "template": "template",
        "playwright": "playwright",
    }

    init_kwargs: dict[str, Any] = {}
    for file_key, field_name in key_map.items():
        if file_key in file_data:
            init_kwargs[field_name] = file_data[file_key]

    # Apply CLI overrides (skip None values)
    if cli_overrides:
        for k, v in cli_overrides.items():
            if v is not None:
                init_kwargs[k] = v

    return AppConfig(**init_kwargs)


def ensure_config_dir() -> Path:
    """Create ~/.webinfo2md/ if it doesn't exist."""
    config_dir = Path("~/.webinfo2md").expanduser()
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def write_default_config(path: Optional[Path] = None) -> Path:
    """Write a default config.yaml template."""
    if path is None:
        path = ensure_config_dir() / "config.yaml"

    template = """\
# webinfo2md configuration
# See README.md for full documentation

default_provider: openai
default_model: gpt-4o
chunk_size: 6000
max_concurrency: 3
max_pages: 10
min_content_length: 500
template: interview-general
# output_dir: ~/Documents/interview-notes/

# Playwright browser settings (used for JS-heavy pages)
playwright:
  headless: true
  enable_scroll: false
  scroll_max_iterations: 10
  scroll_pause_ms: 1500
  wait_strategy: networkidle
  wait_timeout_ms: 15000
  # cookie_file: ~/.webinfo2md/cookies.json
  # headers:
  #   Accept-Language: "zh-CN,zh;q=0.9,en;q=0.8"
"""
    path.write_text(template)
    return path
