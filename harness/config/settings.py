from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from harness.rag.config import RagConfig, load_rag_config


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
    subagents_enabled: bool = True
    max_concurrent_subagents: int = 3
    subagent_timeout_seconds: int = 900


@dataclass(slots=True)
class MemoryConfig:
    enabled: bool = True
    storage_path: Path = Path(".sandbox/memory.json")
    debounce_seconds: int = 30
    model_name: str | None = None
    max_facts: int = 100
    fact_confidence_threshold: float = 0.7
    injection_enabled: bool = True
    max_injection_tokens: int = 1200


@dataclass(slots=True)
class LocalBrowserConfig:
    enabled: bool = True
    search_engine: str = "https://www.bing.com/search?q={query}"
    allowed_domains: tuple[str, ...] = ()


@dataclass(slots=True)
class HarnessConfig:
    models: list[RegisteredModel]
    default_model: str
    sandbox: SandboxConfig
    runtime: RuntimeConfig
    memory: MemoryConfig
    local_browser: LocalBrowserConfig
    rag: RagConfig

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
    subagents_enabled = os.getenv("HARNESS_SUBAGENTS_ENABLED", "true").lower() == "true"
    max_concurrent_subagents = int(os.getenv("HARNESS_SUBAGENTS_MAX_CONCURRENT", "3"))
    subagent_timeout_seconds = int(os.getenv("HARNESS_SUBAGENTS_TIMEOUT_SECONDS", "900"))
    memory_enabled = os.getenv("HARNESS_MEMORY_ENABLED", "true").lower() == "true"
    memory_storage_path = os.getenv("HARNESS_MEMORY_STORAGE_PATH", ".sandbox/memory.json").strip() or ".sandbox/memory.json"
    memory_debounce_seconds = int(os.getenv("HARNESS_MEMORY_DEBOUNCE_SECONDS", "30"))
    memory_model_name = os.getenv("HARNESS_MEMORY_MODEL", "").strip() or None
    memory_max_facts = int(os.getenv("HARNESS_MEMORY_MAX_FACTS", "100"))
    memory_fact_confidence_threshold = float(os.getenv("HARNESS_MEMORY_FACT_CONFIDENCE_THRESHOLD", "0.7"))
    memory_injection_enabled = os.getenv("HARNESS_MEMORY_INJECTION_ENABLED", "true").lower() == "true"
    memory_max_injection_tokens = int(os.getenv("HARNESS_MEMORY_MAX_INJECTION_TOKENS", "1200"))
    local_browser_enabled = os.getenv("HARNESS_LOCAL_BROWSER_ENABLED", "true").lower() == "true"
    local_browser_search_engine = (
        os.getenv("HARNESS_LOCAL_BROWSER_SEARCH_ENGINE", "https://www.bing.com/search?q={query}").strip()
        or "https://www.bing.com/search?q={query}"
    )
    raw_allowed_domains = os.getenv("HARNESS_LOCAL_BROWSER_ALLOWED_DOMAINS", "")
    local_browser_allowed_domains = tuple(item.strip() for item in raw_allowed_domains.split(",") if item.strip())

    raw_memory_path = Path(memory_storage_path)
    resolved_memory_path = raw_memory_path if raw_memory_path.is_absolute() else (root / raw_memory_path).resolve()

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
            subagents_enabled=subagents_enabled,
            max_concurrent_subagents=max(1, max_concurrent_subagents),
            subagent_timeout_seconds=max(1, subagent_timeout_seconds),
        ),
        memory=MemoryConfig(
            enabled=memory_enabled,
            storage_path=resolved_memory_path,
            debounce_seconds=max(1, memory_debounce_seconds),
            model_name=memory_model_name,
            max_facts=max(1, memory_max_facts),
            fact_confidence_threshold=max(0.0, min(1.0, memory_fact_confidence_threshold)),
            injection_enabled=memory_injection_enabled,
            max_injection_tokens=max(100, memory_max_injection_tokens),
        ),
        local_browser=LocalBrowserConfig(
            enabled=local_browser_enabled,
            search_engine=local_browser_search_engine,
            allowed_domains=local_browser_allowed_domains,
        ),
        rag=load_rag_config(root),
    )
