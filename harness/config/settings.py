from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class RegisteredModel:
    name: str
    display_name: str
    provider: str
    base_url: str | None = None
    model: str = ""
    api_key_env: str = "HARNESS_API_KEY"
    max_tokens: int = 4096
    temperature: float = 1.0
    supports_vision: bool = False

    def read_api_key(self) -> str:
        value = os.getenv(self.api_key_env, "").strip()
        if not value:
            raise ValueError(f"Environment variable {self.api_key_env} is required.")
        return value


@dataclass(slots=True)
class SandboxConfig:
    root_dir: Path
    command_timeout_seconds: int = 60


@dataclass(slots=True)
class RuntimeConfig:
    max_steps: int = 8
    max_output_chars: int = 12000
    max_recent_messages: int = 16
    compact_threshold_chars: int = 24000
    skill_memory_max: int = 12


@dataclass(slots=True)
class HarnessConfig:
    models: list[RegisteredModel]
    default_model: str
    sandbox: SandboxConfig
    runtime: RuntimeConfig

    def get_model(self, model_name: str | None = None) -> RegisteredModel:
        target_name = model_name or self.default_model
        for item in self.models:
            if item.name == target_name:
                return item
        raise ValueError(f"Unknown model: {target_name}")


def _load_registered_models() -> list[RegisteredModel]:
    model = RegisteredModel(
        name=os.getenv("HARNESS_NAME", ""),
        display_name=os.getenv("HARNESS_DISPLAY_NAME", ""),
        provider=os.getenv("HARNESS_PROVIDER", "openai-compatible"),
        model=os.getenv("HARNESS_MODEL", ""),
        api_key_env="HARNESS_API_KEY",
        base_url=os.getenv("HARNESS_BASE_URL", ""),
        max_tokens=int(os.getenv("HARNESS_MAX_TOKENS", "4096")),
        temperature=float(os.getenv("HARNESS_TEMPERATURE", "1.0")),
        supports_vision=os.getenv("HARNESS_SUPPORTS_VISION", "true").lower() == "true",
    )
    return [model]


def load_harness_config(project_root: Path | None = None) -> HarnessConfig:
    root = project_root or Path.cwd()

    models = _load_registered_models()
    default_model = os.getenv("HARNESS_DEFAULT_MODEL", models[0].name)

    sandbox_root = os.getenv("HARNESS_SANDBOX_ROOT", str(root / ".sandbox"))
    timeout = int(os.getenv("HARNESS_SANDBOX_TIMEOUT", "60"))

    max_steps = int(os.getenv("HARNESS_MAX_STEPS", "8"))
    max_output_chars = int(os.getenv("HARNESS_MAX_OUTPUT_CHARS", "12000"))
    max_recent_messages = int(os.getenv("HARNESS_CONTEXT_MAX_RECENT_MESSAGES", "16"))
    compact_threshold_chars = int(os.getenv("HARNESS_CONTEXT_COMPACT_THRESHOLD_CHARS", "24000"))
    skill_memory_max = int(os.getenv("HARNESS_CONTEXT_SKILL_MEMORY_MAX", "12"))

    return HarnessConfig(
        models=models,
        default_model=default_model,
        sandbox=SandboxConfig(
            root_dir=Path(sandbox_root).resolve(), command_timeout_seconds=timeout
        ),
        runtime=RuntimeConfig(
            max_steps=max_steps,
            max_output_chars=max_output_chars,
            max_recent_messages=max_recent_messages,
            compact_threshold_chars=compact_threshold_chars,
            skill_memory_max=skill_memory_max,
        ),
    )
