from __future__ import annotations

from pathlib import Path

from harness.agents.prompt import build_system_instructions, get_skills_prompt_section
from harness.skills.types import Skill


def test_get_skills_prompt_section_contains_skill_locations():
    skill = Skill(
        name="example",
        description="Example skill",
        license=None,
        skill_dir=Path("/tmp/skills/public/example"),
        skill_file=Path("/tmp/skills/public/example/SKILL.md"),
        relative_path=Path("example"),
        category="public",
        enabled=True,
    )

    section = get_skills_prompt_section([skill], container_base_path="skills")

    assert "<skill_system>" in section
    assert "<name>example</name>" in section
    assert "<location>skills/public/example/SKILL.md</location>" in section
    assert "references or scripts in the same folder" in section


def test_build_system_instructions_includes_skills_section_when_present():
    skill = Skill(
        name="example",
        description="Example skill",
        license=None,
        skill_dir=Path("/tmp/skills/public/example"),
        skill_file=Path("/tmp/skills/public/example/SKILL.md"),
        relative_path=Path("example"),
        category="public",
        enabled=True,
    )

    instructions = build_system_instructions([skill])
    assert "You are a minimal coding agent" in instructions
    assert "<available_skills>" in instructions
