from __future__ import annotations

from pathlib import Path

from harness.client import HarnessClient
from harness.context import ThreadRuntimeResolver


def _write_skill(root: Path, category: str, folder: str, *, name: str, description: str) -> None:
    skill_dir = root / "skills" / category / folder
    references_dir = skill_dir / "references"
    skill_dir.mkdir(parents=True, exist_ok=True)
    references_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                f"name: {name}",
                f"description: {description}",
                "---",
                "",
                "# Body",
                "- See references/info.md",
            ]
        ),
        encoding="utf-8",
    )
    (references_dir / "info.md").write_text(f"reference for {name}", encoding="utf-8")


def _make_project(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='tmp'\nversion='0.0.0'\n", encoding="utf-8")
    (tmp_path / "harness").mkdir(parents=True, exist_ok=True)
    (tmp_path / "extensions_config.json").write_text('{"skills": {}}', encoding="utf-8")


def test_skills_are_synced_once_into_shared_user_dir_and_reused(tmp_path):
    _make_project(tmp_path)
    _write_skill(tmp_path, "public", "alpha", name="alpha", description="Alpha")

    client = HarnessClient(project_root=tmp_path)
    runtime = ThreadRuntimeResolver(client.config.sandbox.root_dir)
    thread_a = runtime.ensure_dirs(runtime.resolve("thread-a"))
    thread_b = runtime.ensure_dirs(runtime.resolve("thread-b"))

    loaded = client._load_enabled_skills(thread_paths=thread_a)

    assert [item.name for item in loaded] == ["alpha"]
    assert thread_a.skills_dir.is_symlink()
    assert thread_b.skills_dir.is_symlink()
    assert thread_a.shared_skills_dir == thread_b.shared_skills_dir
    assert (thread_a.shared_skills_dir / "public" / "alpha" / "SKILL.md").exists()
    assert (thread_a.shared_skills_dir / "public" / "alpha" / "references" / "info.md").exists()

    sandbox = client._make_sandbox(thread_a)
    assert sandbox.read_file("skills/public/alpha/references/info.md") == "reference for alpha"


def test_skills_cache_and_shared_sync_pick_up_new_skill_dirs(tmp_path):
    _make_project(tmp_path)
    _write_skill(tmp_path, "public", "alpha", name="alpha", description="Alpha")

    client = HarnessClient(project_root=tmp_path)
    runtime = ThreadRuntimeResolver(client.config.sandbox.root_dir)
    thread_paths = runtime.ensure_dirs(runtime.resolve("thread-a"))

    first = client._load_enabled_skills(thread_paths=thread_paths)
    assert [item.name for item in first] == ["alpha"]

    _write_skill(tmp_path, "public", "beta", name="beta", description="Beta")

    second = client._load_enabled_skills(thread_paths=thread_paths)
    assert [item.name for item in second] == ["alpha", "beta"]
    assert (thread_paths.shared_skills_dir / "public" / "beta" / "references" / "info.md").exists()
