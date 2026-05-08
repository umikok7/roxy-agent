from __future__ import annotations

from harness.rag.chunker import chunk_document
from harness.rag.loader import LoadedDocument


def test_chunk_document_splits_text_with_overlap():
    document = LoadedDocument(
        source_path="faq.txt",
        title="FAQ",
        text="A" * 1000,
    )

    chunks = chunk_document(document, chunk_size=400, chunk_overlap=100)

    assert len(chunks) == 3
    assert chunks[0].text[-100:] == chunks[1].text[:100]
    assert chunks[0].chunk_id == "faq.txt::chunk-0"


def test_chunk_document_ignores_blank_content():
    document = LoadedDocument(source_path="empty.txt", title="Empty", text="  \n\n  ")

    assert chunk_document(document, chunk_size=400, chunk_overlap=100) == []
