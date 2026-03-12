from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from webinfo2md.cli import main
from webinfo2md.crawler.base import BaseCrawler, CrawlResult


class FakeCrawler(BaseCrawler):
    async def fetch(self, url: str) -> CrawlResult:
        html = f"""
        <html>
          <head><title>{url}</title></head>
          <body>
            <main>
              <h1>{url}</h1>
              <p>Transformer attention question.</p>
              <p>Cache optimization and distributed training.</p>
            </main>
          </body>
        </html>
        """
        return CrawlResult(
            url=url,
            title=url,
            raw_html=html,
            text_content="Transformer attention question. Cache optimization and distributed training.",
            links=[],
            status_code=200,
        )


async def fake_create(*args, **kwargs):
    return FakeCrawler(
        headers={},
        cookies={},
        timeout=kwargs.get("timeout", 20.0),
        crawl_delay_min=0.0,
        crawl_delay_max=0.0,
        verbose=False,
    )


def test_cli_batch_dry_run_uses_config_file():
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path("config.yaml").write_text(
            "\n".join(
                [
                    "provider: openai",
                    "chunk_size: 300",
                    "output_dir: batch-output",
                    "dry_run: true",
                    "crawl_delay_min: 0",
                    "crawl_delay_max: 0",
                ]
            ),
            encoding="utf-8",
        )
        Path("urls.txt").write_text(
            "https://example.com/post-one\nhttps://example.com/post-two\n",
            encoding="utf-8",
        )

        with patch("webinfo2md.pipeline.CrawlerFactory.create", side_effect=fake_create):
            result = runner.invoke(
                main,
                ["--config", "config.yaml", "--url-list", "urls.txt"],
            )

    assert result.exit_code == 0, result.output
    assert "[dry-run] https://example.com/post-one" in result.output
    assert "batch-output/01-example-com-post-one.md" in result.output
    assert "[dry-run] https://example.com/post-two" in result.output
    assert "batch-output/02-example-com-post-two.md" in result.output
