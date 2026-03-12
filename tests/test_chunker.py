from webinfo2md.extractor.chunker import TextChunker
from webinfo2md.utils.token_counter import estimate_tokens


def test_chunker_respects_limit():
    text = "\n\n".join([f"## Section {i}\n" + ("content " * 200) for i in range(5)])
    chunker = TextChunker(max_tokens=120)

    chunks = chunker.chunk(text)

    assert len(chunks) > 1
    assert all(estimate_tokens(chunk) <= 120 for chunk in chunks)
