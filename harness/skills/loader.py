from __future__ import annotations

import logging
import os
from pathlib import Path

from harness.config.extensions_config import ExtensionsConfig
from harness.skills.parser import parse_skill_file
from harness.skills.types import Skill


logger = logging.getLogger(__name__)


def get_skills_root_path() -> Path:
    return Path(__file__).resolve().parents[2] / "skills"


def load_skills(
    skills_path: Path | None = None,
    *,
    enabled_only: bool = False,
    extensions_config_path: str | None = None,
) -> list[Skill]:
    root = skills_path or get_skills_root_path()
    if not root.exists():
        return []

    skills: list[Skill] = []
    for category in ("public", "custom"):
        category_path = root / category
        if not category_path.exists() or not category_path.is_dir():
            continue

        for current_root, dir_names, file_names in os.walk(category_path, followlinks=True):
            dir_names[:] = sorted(name for name in dir_names if not name.startswith("."))
            if "SKILL.md" not in file_names:
                continue

            skill_file = Path(current_root) / "SKILL.md"
            relative_path = skill_file.parent.relative_to(category_path)
            skill = parse_skill_file(skill_file, category=category, relative_path=relative_path)
            if skill is not None:
                skills.append(skill)

    try:
        config = ExtensionsConfig.from_file(extensions_config_path)
        for item in skills:
            item.enabled = config.is_skill_enabled(item.name, item.category)
    except Exception as exc:
        logger.warning("Failed to apply skill states from config: %s", exc)

    if enabled_only:
        skills = [item for item in skills if item.enabled]

    skills.sort(key=lambda item: item.name)
    return skills
