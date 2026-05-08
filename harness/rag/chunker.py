from __future__ import annotations

from dataclasses import dataclass

from harness.rag.loader import LoadedDocument


@dataclass(slots=True)
class DocumentChunk:
    chunk_id: str
    source_path: str
    title: str
    text: str


def chunk_document(document: LoadedDocument, *, chunk_size: int, chunk_overlap: int) -> list[DocumentChunk]:
    normalized = " ".join(part.strip() for part in document.text.splitlines() if part.strip()).strip()
    if not normalized:
        return []

    step = max(1, chunk_size - chunk_overlap)
    chunks: list[DocumentChunk] = []
    start = 0
    index = 0

    while start < len(normalized):
        end = min(len(normalized), start + chunk_size)
        text = normalized[start:end].strip()
        if text:
            chunks.append(
                DocumentChunk(
                    chunk_id=f"{document.source_path}::chunk-{index}",
                    source_path=document.source_path,
                    title=document.title,
                    text=text,
                )
            )
            index += 1
        if end >= len(normalized):
            break
        start += step

    return chunks
