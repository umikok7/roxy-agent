from __future__ import annotations

from pathlib import Path

import pytest

from harness.sandbox.runtime import BasicSandbox, SandboxPermissionError


def test_sandbox_rejects_outside_path(tmp_path):
    sandbox = BasicSandbox(tmp_path)

    with pytest.raises(SandboxPermissionError):
        sandbox.read_file("../outside.txt")


def test_sandbox_runs_bash_from_command_cwd(tmp_path):
    workspace_dir = tmp_path / "workspace"
    sandbox = BasicSandbox(tmp_path, command_cwd=workspace_dir)

    output = sandbox.run_bash("pwd")

    assert output == str(workspace_dir.resolve())


def test_sandbox_rejects_command_cwd_outside_root(tmp_path):
    outside_dir = tmp_path.parent / "outside-workspace"

    with pytest.raises(SandboxPermissionError):
        BasicSandbox(tmp_path, command_cwd=Path(outside_dir))


def test_sandbox_blocks_dangerous_rm_rf_command(tmp_path):
    sandbox = BasicSandbox(tmp_path)

    with pytest.raises(SandboxPermissionError):
        sandbox.run_bash("rm -rf workspace")


def test_sandbox_blocks_sudo_commands(tmp_path):
    sandbox = BasicSandbox(tmp_path)

    with pytest.raises(SandboxPermissionError):
        sandbox.run_bash("sudo ls")


def test_sandbox_allows_symlinked_shared_skill_dir_with_allowed_root(tmp_path):
    shared_skills = tmp_path / "shared" / "skills"
    shared_skills.mkdir(parents=True)
    (shared_skills / "note.txt").write_text("shared", encoding="utf-8")

    thread_root = tmp_path / "threads" / "t1"
    thread_root.mkdir(parents=True)
    (thread_root / "skills").symlink_to(shared_skills, target_is_directory=True)

    sandbox = BasicSandbox(
        thread_root,
        command_cwd=thread_root,
        allowed_roots=[shared_skills],
    )

    assert sandbox.read_file("skills/note.txt") == "shared"
