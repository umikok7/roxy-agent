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
    assert "You are a local desktop assistant" in instructions
    assert "<available_skills>" in instructions


def test_build_system_instructions_includes_long_term_memory_when_present():
    instructions = build_system_instructions([], memory_text="Stable Profile:\n- Personal: Prefers concise replies")

    assert "<long_term_memory>" in instructions
    assert "Prefers concise replies" in instructions


def test_build_system_instructions_includes_browser_tool_governance():
    instructions = build_system_instructions([])

    assert "browser_search is for opening the host browser to search on the user's machine" in instructions
    assert "browser_search and browser_open only perform local browser actions" in instructions
    assert "Do not say that a browser page was opened unless the corresponding browser tool call actually succeeded." in instructions


def test_build_system_instructions_preserves_pinned_skill_priority():
    instructions = build_system_instructions([], pinned_skills=["roxy-skill"])

    assert "Previously selected skills in this session: roxy-skill." in instructions
    assert "Do not let the base assistant tone override the pinned skill's persona." in instructions
