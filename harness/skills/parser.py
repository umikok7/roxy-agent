from __future__ import annotations

import logging
import re
from pathlib import Path

from harness.skills.types import Skill


logger = logging.getLogger(__name__)


def parse_skill_file(skill_file: Path, category: str, relative_path: Path | None = None) -> Skill | None:
    if not skill_file.exists() or skill_file.name != "SKILL.md":
        return None

    try:
        content = skill_file.read_text(encoding="utf-8")
        front_matter_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
        if not front_matter_match:
            return None

        front_matter = front_matter_match.group(1)
        metadata: dict[str, str] = {}
        for line in front_matter.split("\n"):
            row = line.strip()
            if not row or ":" not in row:
                continue
            key, value = row.split(":", 1)
            metadata[key.strip()] = value.strip()

        name = metadata.get("name")
        description = metadata.get("description")
        if not name or not description:
            return None

        return Skill(
            name=name,
            description=description,
            license=metadata.get("license"),
            skill_dir=skill_file.parent,
            skill_file=skill_file,
            relative_path=relative_path or Path(skill_file.parent.name),
            category=category,
            enabled=True,
        )
    except Exception as exc:
        logger.warning("Failed to parse skill file %s: %s", skill_file, exc)
        return None
