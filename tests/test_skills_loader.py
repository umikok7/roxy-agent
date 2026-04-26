from __future__ import annotations

from pathlib import Path

from harness.skills.loader import load_skills


def _write_skill(root: Path, category: str, folder: str, *, name: str, description: str) -> None:
    target = root / "skills" / category / folder / "SKILL.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "\n".join(
            [
                "---",
                f"name: {name}",
                f"description: {description}",
                "---",
                "",
                "# Body",
            ]
        ),
        encoding="utf-8",
    )


def test_load_skills_applies_enabled_state(tmp_path):
    _write_skill(tmp_path, "public", "alpha", name="alpha", description="A")
    _write_skill(tmp_path, "custom", "beta", name="beta", description="B")

    config_path = tmp_path / "extensions_config.json"
    config_path.write_text(
        '{"skills": {"alpha": {"enabled": true}, "beta": {"enabled": false}}}',
        encoding="utf-8",
    )

    loaded = load_skills(
        skills_path=tmp_path / "skills",
        enabled_only=False,
        extensions_config_path=str(config_path),
    )
    assert [item.name for item in loaded] == ["alpha", "beta"]

    flags = {item.name: item.enabled for item in loaded}
    assert flags == {"alpha": True, "beta": False}

    enabled_only = load_skills(
        skills_path=tmp_path / "skills",
        enabled_only=True,
        extensions_config_path=str(config_path),
    )
    assert [item.name for item in enabled_only] == ["alpha"]


def test_load_skills_skips_invalid_files(tmp_path):
    invalid = tmp_path / "skills" / "public" / "bad" / "SKILL.md"
    invalid.parent.mkdir(parents=True, exist_ok=True)
    invalid.write_text("# missing frontmatter", encoding="utf-8")

    loaded = load_skills(skills_path=tmp_path / "skills", enabled_only=False)
    assert loaded == []
