from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


SUPPORTED_KB_SUFFIXES = {".md", ".txt", ".json"}


@dataclass(slots=True)
class LoadedDocument:
    source_path: str
    title: str
    text: str


def _extract_title(path: Path, text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or path.stem
        return stripped[:80]
    return path.stem


def _read_document(path: Path) -> str:
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        return json.dumps(payload, ensure_ascii=False, indent=2)
    return path.read_text(encoding="utf-8")


def load_documents(knowledge_dir: Path) -> list[LoadedDocument]:
    if not knowledge_dir.exists():
        return []

    documents: list[LoadedDocument] = []
    for path in sorted(knowledge_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_KB_SUFFIXES:
            continue
        text = _read_document(path).strip()
        if not text:
            continue
        documents.append(
            LoadedDocument(
                source_path=str(path.relative_to(knowledge_dir)),
                title=_extract_title(path, text),
                text=text,
            )
        )
    return documents
