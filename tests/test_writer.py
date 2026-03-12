from datetime import datetime

from webinfo2md.writer.md_writer import DocumentMetadata, MarkdownWriter


def test_writer_adds_header(tmp_path):
    writer = MarkdownWriter()
    output = tmp_path / "result.md"
    metadata = DocumentMetadata(
        source_url="https://example.com/post",
        source_title="Example Title",
        generated_at=datetime(2026, 3, 12, 12, 0, 0),
        question_count=3,
        company="ExampleCo",
        position="SDE",
    )

    writer.write("## 内容\n\nhello", output, metadata=metadata)

    content = output.read_text(encoding="utf-8")
    assert content.startswith("# ExampleCo - SDE 面试整理")
    assert "> 问题总数: 3" in content
