from __future__ import annotations

import re
import subprocess
from pathlib import Path


class SandboxError(RuntimeError):
    """Base sandbox error."""


class SandboxPermissionError(SandboxError):
    """Raised when a path is outside of sandbox root."""


class SandboxExecutionError(SandboxError):
    """Raised when command execution fails."""


_DANGEROUS_COMMAND_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"(^|[;&|()])\s*rm\s+-[A-Za-z]*[rf][A-Za-z]*\b", "recursive rm is not allowed"),
    (r"(^|[;&|()])\s*sudo\b", "sudo is not allowed"),
    (r"(^|[;&|()])\s*(shutdown|reboot|halt|poweroff)\b", "system power commands are not allowed"),
    (r"(^|[;&|()])\s*(mkfs|fdisk|diskutil\s+eraseDisk|diskutil\s+partitionDisk)\b", "disk formatting commands are not allowed"),
    (r"(^|[;&|()])\s*dd\b", "raw disk copy commands are not allowed"),
    (r"(^|[;&|()])\s*mv\s+.+\s+/dev/null\b", "destructive move commands are not allowed"),
)


class BasicSandbox:
    def __init__(
        self,
        root_dir: Path,
        *,
        command_cwd: Path | None = None,
        command_timeout_seconds: int = 60,
        max_output_chars: int = 12000,
    ) -> None:
        self.root_dir = root_dir.resolve()
        self.command_cwd = (command_cwd or self.root_dir).resolve()
        self.command_timeout_seconds = command_timeout_seconds
        self.max_output_chars = max_output_chars
        if not self.command_cwd.is_relative_to(self.root_dir):
            raise SandboxPermissionError(f"Command cwd is outside sandbox root: {self.command_cwd}")
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.command_cwd.mkdir(parents=True, exist_ok=True)

    def _truncate(self, text: str) -> str:
        if len(text) <= self.max_output_chars:
            return text
        return text[: self.max_output_chars] + "\n...[truncated]"

    def _resolve_path(self, user_path: str) -> Path:
        base = self.root_dir
        target = Path(user_path)
        if target.is_absolute():
            resolved = target.resolve()
        else:
            resolved = (base / target).resolve()

        if not resolved.is_relative_to(base):
            raise SandboxPermissionError(f"Path is outside sandbox root: {user_path}")
        return resolved

    def _guard_command(self, command: str) -> None:
        normalized = command.strip()
        if not normalized:
            raise SandboxExecutionError("Command cannot be empty")

        lowered = normalized.lower()
        for pattern, reason in _DANGEROUS_COMMAND_PATTERNS:
            if re.search(pattern, lowered):
                raise SandboxPermissionError(f"Blocked dangerous command: {reason}")

    def run_bash(self, command: str) -> str:
        self._guard_command(command)

        completed = subprocess.run(
            command,
            shell=True,
            cwd=self.command_cwd,
            capture_output=True,
            text=True,
            timeout=self.command_timeout_seconds,
        )
        output = (completed.stdout or "") + (completed.stderr or "")
        output = output.strip() or "(no output)"
        if completed.returncode != 0:
            output = f"Command exited with {completed.returncode}\n{output}"
        return self._truncate(output)

    def list_dir(self, path: str = ".") -> str:
        target = self._resolve_path(path)
        if not target.exists():
            raise SandboxExecutionError(f"Path not found: {path}")

        if target.is_file():
            return str(target.relative_to(self.root_dir))

        rows: list[str] = []
        for child in sorted(target.iterdir(), key=lambda p: p.name):
            suffix = "/" if child.is_dir() else ""
            rows.append(f"{child.name}{suffix}")
        return self._truncate("\n".join(rows) or "(empty directory)")

    def read_file(self, path: str, start_line: int | None = None, end_line: int | None = None) -> str:
        target = self._resolve_path(path)
        if not target.exists() or not target.is_file():
            raise SandboxExecutionError(f"File not found: {path}")

        lines = target.read_text(encoding="utf-8").splitlines()
        if start_line is None and end_line is None:
            return self._truncate("\n".join(lines))

        start = max((start_line or 1) - 1, 0)
        end = min(end_line or len(lines), len(lines))
        selected = lines[start:end]
        return self._truncate("\n".join(selected))

    def write_file(self, path: str, content: str, append: bool = False) -> str:
        target = self._resolve_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)

        mode = "a" if append else "w"
        with target.open(mode, encoding="utf-8") as handle:
            handle.write(content)

        action = "Appended" if append else "Wrote"
        return f"{action} {len(content)} chars to {target.relative_to(self.root_dir)}"

    def str_replace(self, path: str, old_str: str, new_str: str, replace_all: bool = False) -> str:
        if not old_str:
            raise SandboxExecutionError("old_str cannot be empty")

        target = self._resolve_path(path)
        if not target.exists() or not target.is_file():
            raise SandboxExecutionError(f"File not found: {path}")

        original = target.read_text(encoding="utf-8")
        if old_str not in original:
            raise SandboxExecutionError("old_str was not found in file")

        if replace_all:
            updated = original.replace(old_str, new_str)
            replacements = original.count(old_str)
        else:
            updated = original.replace(old_str, new_str, 1)
            replacements = 1

        target.write_text(updated, encoding="utf-8")
        return f"Replaced {replacements} occurrence(s) in {target.relative_to(self.root_dir)}"
