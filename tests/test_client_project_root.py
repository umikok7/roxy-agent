from __future__ import annotations

from pathlib import Path

from harness.client import resolve_project_root


def test_resolve_project_root_finds_pyproject(tmp_path):
    root = tmp_path / "repo"
    (root / "harness").mkdir(parents=True)
    (root / "pyproject.toml").write_text("[project]\nname='x'\nversion='0.1.0'\n", encoding="utf-8")

    nested = root / "APP" / "api"
    nested.mkdir(parents=True)

    resolved = resolve_project_root(nested)
    assert resolved == root


def test_resolve_project_root_fallbacks_to_start_when_markers_absent(tmp_path):
    start = tmp_path / "no-markers"
    start.mkdir(parents=True)

    resolved = resolve_project_root(start)
    assert resolved == start
