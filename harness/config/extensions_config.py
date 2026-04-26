from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class SkillStateConfig:
    enabled: bool = True


@dataclass(slots=True)
class ExtensionsConfig:
    skills: dict[str, SkillStateConfig] = field(default_factory=dict)

    @classmethod
    def resolve_config_path(cls, config_path: str | None = None) -> Path | None:
        if config_path:
            path = Path(config_path)
            if not path.exists():
                raise FileNotFoundError(f"extensions config not found: {path}")
            return path

        env_path = os.getenv("HARNESS_EXTENSIONS_CONFIG_PATH", "").strip()
        if env_path:
            path = Path(env_path)
            if not path.exists():
                raise FileNotFoundError(f"extensions config not found: {path}")
            return path

        candidates = [
            Path.cwd() / "extensions_config.json",
            Path.cwd().parent / "extensions_config.json",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    @classmethod
    def from_file(cls, config_path: str | None = None) -> "ExtensionsConfig":
        resolved_path = cls.resolve_config_path(config_path)
        if resolved_path is None:
            return cls(skills={})

        with resolved_path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)

        skill_items = raw.get("skills", {})
        skills: dict[str, SkillStateConfig] = {}
        if isinstance(skill_items, dict):
            for name, value in skill_items.items():
                if isinstance(value, dict):
                    enabled = bool(value.get("enabled", True))
                else:
                    enabled = bool(value)
                skills[name] = SkillStateConfig(enabled=enabled)
        return cls(skills=skills)

    def is_skill_enabled(self, skill_name: str, skill_category: str) -> bool:
        entry = self.skills.get(skill_name)
        if entry is None:
            return skill_category in ("public", "custom")
        return entry.enabled
