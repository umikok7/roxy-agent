from __future__ import annotations

import re
import shutil
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
    shared_skills_dir: Path
    uploads_dir: Path
    outputs_dir: Path
    context_file: Path
    conversation_file: Path
    messages_file: Path


class ThreadRuntimeResolver:
    def __init__(self, sandbox_root: Path) -> None:
        self.sandbox_root = sandbox_root.resolve()
        self.sandbox_root.mkdir(parents=True, exist_ok=True)

    def resolve(self, thread_id: str) -> ThreadRuntimePaths:
        normalized = normalize_thread_id(thread_id)
        thread_root = self.sandbox_root / "threads" / normalized
        shared_skills_dir = self.sandbox_root / "users" / "local" / "skills"

        return ThreadRuntimePaths(
            thread_id=thread_id,
            thread_root=thread_root,
            workspace_dir=thread_root / "workspace",
            skills_dir=thread_root / "skills",
            shared_skills_dir=shared_skills_dir,
            uploads_dir=thread_root / "uploads",
            outputs_dir=thread_root / "outputs",
            context_file=thread_root / "context.json",
            conversation_file=thread_root / "conversation.json",
            messages_file=thread_root / "messages.json",
        )

    def ensure_dirs(self, paths: ThreadRuntimePaths) -> ThreadRuntimePaths:
        paths.workspace_dir.mkdir(parents=True, exist_ok=True)
        paths.shared_skills_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_skills_link(paths.skills_dir, paths.shared_skills_dir)
        paths.uploads_dir.mkdir(parents=True, exist_ok=True)
        paths.outputs_dir.mkdir(parents=True, exist_ok=True)
        return paths

    @staticmethod
    def _ensure_skills_link(skills_dir: Path, shared_skills_dir: Path) -> None:
        if skills_dir.is_symlink():
            try:
                if skills_dir.resolve() == shared_skills_dir.resolve():
                    return
            except OSError:
                pass
            skills_dir.unlink()
        elif skills_dir.exists():
            if skills_dir.is_dir():
                shutil.rmtree(skills_dir)
            else:
                skills_dir.unlink()

        skills_dir.parent.mkdir(parents=True, exist_ok=True)
        skills_dir.symlink_to(shared_skills_dir, target_is_directory=True)
