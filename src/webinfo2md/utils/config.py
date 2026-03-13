from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field, model_validator
import yaml

load_dotenv()

SUPPORTED_PROVIDERS = ("openai", "anthropic", "claude", "deepseek", "kimi", "gemini")
ProviderName = Literal["openai", "anthropic", "claude", "deepseek", "kimi", "gemini"]
DEFAULT_CONFIG_PATH = Path.home() / ".webinfo2md" / "config.yaml"

DEFAULT_MODELS: dict[str, str] = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-7-sonnet-latest",
    "claude": "claude-3-7-sonnet-latest",
    "deepseek": "deepseek-chat",
    "kimi": "moonshot-v1-32k",
    "gemini": "gemini-2.5-flash",
}

PROVIDER_ENV_MAP: dict[str, list[str]] = {
    "openai": ["OPENAI_API_KEY", "LLM_API_KEY"],
    "anthropic": ["ANTHROPIC_API_KEY", "CLAUDE_API_KEY", "LLM_API_KEY"],
    "claude": ["CLAUDE_API_KEY", "ANTHROPIC_API_KEY", "LLM_API_KEY"],
    "deepseek": ["DEEPSEEK_API_KEY", "LLM_API_KEY"],
    "kimi": ["KIMI_API_KEY", "MOONSHOT_API_KEY", "LLM_API_KEY"],
    "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY", "LLM_API_KEY"],
}


def default_model_for_provider(provider: str) -> str:
    if provider not in DEFAULT_MODELS:
        raise ValueError(f"Unsupported provider: {provider}")
    return DEFAULT_MODELS[provider]


def resolve_api_key(provider: str, explicit_api_key: str | None) -> str:
    if explicit_api_key:
        return explicit_api_key

    for env_name in PROVIDER_ENV_MAP[provider]:
        value = os.getenv(env_name)
        if value:
            return value
    raise ValueError(
        f"Missing API key for provider '{provider}'. "
        "Use --api-key or set an environment variable."
    )


class PipelineConfig(BaseModel):
    url: str
    api_key: str | None = None
    provider: ProviderName = "openai"
    model: str | None = None
    prompt: str | None = None
    template: str = "interview-general"
    output: Path = Path("output.md")
    depth: int = 0
    pages: int = 5
    verbose: bool = False
    interactive: bool = False
    dry_run: bool = False
    chunk_size: int = 3000
    max_concurrency: int = 5
    force_playwright: bool = False
    timeout: float = 20.0
    min_content_length: int = 500
    crawl_delay_min: float = 1.0
    crawl_delay_max: float = 3.0
    headers: dict[str, str] = Field(default_factory=dict)
    cookies: dict[str, str] = Field(default_factory=dict)
    playwright: "PlaywrightConfig | None" = None

    @model_validator(mode="after")
    def apply_defaults(self) -> "PipelineConfig":
        if not self.dry_run:
            self.api_key = resolve_api_key(self.provider, self.api_key)
        if not self.model:
            self.model = default_model_for_provider(self.provider)
        self.output = Path(self.output)
        if self.depth < 0:
            raise ValueError("depth must be >= 0")
        if self.pages < 1:
            raise ValueError("pages must be >= 1")
        if self.chunk_size < 200:
            raise ValueError("chunk_size must be >= 200")
        if self.max_concurrency < 1:
            raise ValueError("max_concurrency must be >= 1")
        if self.crawl_delay_min < 0 or self.crawl_delay_max < 0:
            raise ValueError("crawl delays must be >= 0")
        if self.crawl_delay_min > self.crawl_delay_max:
            raise ValueError("crawl_delay_min must be <= crawl_delay_max")
        return self


class PlaywrightConfig(BaseModel):
    headless: bool = True
    enable_scroll: bool = False
    scroll_max_iterations: int = 10
    scroll_pause_ms: int = 1500
    wait_until: Literal["networkidle", "domcontentloaded", "selector"] = "networkidle"
    wait_selector: str | None = None
    wait_timeout_ms: int = 20000
    cookie_file: Path | None = None
    screenshot_path: Path | None = None
    user_agent: str | None = None
    viewport_width: int = 1440
    viewport_height: int = 1024

    @model_validator(mode="after")
    def validate_options(self) -> "PlaywrightConfig":
        if self.scroll_max_iterations < 1:
            raise ValueError("scroll_max_iterations must be >= 1")
        if self.scroll_pause_ms < 0:
            raise ValueError("scroll_pause_ms must be >= 0")
        if self.wait_timeout_ms < 1:
            raise ValueError("wait_timeout_ms must be >= 1")
        return self


class AppConfig(BaseModel):
    api_key: str | None = None
    provider: ProviderName | None = None
    model: str | None = None
    prompt: str | None = None
    template: str | None = None
    output: Path | None = None
    output_dir: Path | None = None
    depth: int | None = None
    pages: int | None = None
    chunk_size: int | None = None
    max_concurrency: int | None = None
    force_playwright: bool | None = None
    verbose: bool | None = None
    dry_run: bool | None = None
    timeout: float | None = None
    min_content_length: int | None = None
    crawl_delay_min: float | None = None
    crawl_delay_max: float | None = None
    headers: dict[str, str] | None = None
    cookies: dict[str, str] | None = None
    playwright: PlaywrightConfig | None = None


def merge_playwright_config(
    base: PlaywrightConfig | None,
    *,
    cookie_file: Path | None = None,
    enable_scroll: bool | None = None,
    screenshot_path: Path | None = None,
) -> PlaywrightConfig | None:
    payload: dict[str, Any] = {}
    if base is not None:
        payload.update(model_to_non_null_dict(base))
    if cookie_file is not None:
        payload["cookie_file"] = cookie_file
    if enable_scroll is not None:
        payload["enable_scroll"] = enable_scroll
    if screenshot_path is not None:
        payload["screenshot_path"] = screenshot_path
    if not payload:
        return None
    return PlaywrightConfig.model_validate(payload)


def load_app_config(config_path: Path | None = None) -> AppConfig:
    target_path = config_path or DEFAULT_CONFIG_PATH
    if not target_path.exists():
        if config_path is not None:
            raise FileNotFoundError(f"Config file not found: {target_path}")
        return AppConfig()

    raw_data = yaml.safe_load(target_path.read_text(encoding="utf-8"))
    if raw_data is None:
        raw_data = {}
    if not isinstance(raw_data, dict):
        raise ValueError(f"Config file must contain a YAML object: {target_path}")
    return AppConfig.model_validate(raw_data)


def model_to_non_null_dict(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(exclude_none=True)


PipelineConfig.model_rebuild()
