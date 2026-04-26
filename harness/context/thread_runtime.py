from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


def normalize_thread_id(thread_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]", "_", thread_id.strip())
    return cleaned[:120] or "default"


@dataclass(slots=True)
class ThreadRuntimePaths:
    thread_id: str
    thread_root: Path
    workspace_dir: Path
    skills_dir: Path
    uploads_dir: Path
    outputs_dir: Path
    context_file: Path


class ThreadRuntimeResolver:
    def __init__(self, sandbox_root: Path) -> None:
        self.sandbox_root = sandbox_root.resolve()
        self.sandbox_root.mkdir(parents=True, exist_ok=True)

    def resolve(self, thread_id: str) -> ThreadRuntimePaths:
        normalized = normalize_thread_id(thread_id)
        thread_root = self.sandbox_root / "threads" / normalized

        return ThreadRuntimePaths(
            thread_id=thread_id,
            thread_root=thread_root,
            workspace_dir=thread_root / "workspace",
            skills_dir=thread_root / "skills",
            uploads_dir=thread_root / "uploads",
            outputs_dir=thread_root / "outputs",
            context_file=thread_root / "context.json",
        )

    def ensure_dirs(self, paths: ThreadRuntimePaths) -> ThreadRuntimePaths:
        paths.workspace_dir.mkdir(parents=True, exist_ok=True)
        paths.skills_dir.mkdir(parents=True, exist_ok=True)
        paths.uploads_dir.mkdir(parents=True, exist_ok=True)
        paths.outputs_dir.mkdir(parents=True, exist_ok=True)
        return paths
