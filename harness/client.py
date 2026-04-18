from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from harness.agents.loop import AsyncAgentLoop, LoopSettings, OpenAIChatCompletionsClient
from harness.config.settings import HarnessConfig, load_harness_config
from harness.models.types import AgentRunResult
from harness.sandbox.runtime import BasicSandbox
from harness.tools.executor import ToolExecutor
from harness.tools.registry import ToolRegistry


DEFAULT_INSTRUCTIONS = (
    "You are a minimal coding agent. Use tools when needed, keep answers concise, "
    "and never claim to run tools unless you actually called them."
)


class HarnessClient:
    def __init__(self, config: HarnessConfig | None = None, *, project_root: Path | None = None) -> None:
        self.config = config or load_harness_config(project_root)

        sandbox = BasicSandbox(
            self.config.sandbox.root_dir,
            command_timeout_seconds=self.config.sandbox.command_timeout_seconds,
            max_output_chars=self.config.runtime.max_output_chars,
        )
        registry = ToolRegistry.with_default_tools(sandbox)
        self._tool_executor = ToolExecutor(registry)
        self._tool_schemas = registry.list_tool_schemas()

    def _build_agent(self, model_name: str | None = None) -> AsyncAgentLoop:
        selected_model = self.config.get_model(model_name)

        model_client = OpenAIChatCompletionsClient(
            api_key=selected_model.read_api_key(),
            base_url=selected_model.base_url,
        )

        return AsyncAgentLoop(
            model_client=model_client,
            tool_executor=self._tool_executor,
            tool_schemas=self._tool_schemas,
            settings=LoopSettings(
                model=selected_model.model,
                max_steps=self.config.runtime.max_steps,
                temperature=selected_model.temperature,
                max_tokens=selected_model.max_tokens,
            ),
            instructions=DEFAULT_INSTRUCTIONS,
        )

    def list_models(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for model in self.config.models:
            items.append(
                {
                    "name": model.name,
                    "display_name": model.display_name,
                    "provider": model.provider,
                    "supports_vision": model.supports_vision,
                    "default": model.name == self.config.default_model,
                }
            )
        return items

    async def run_async(self, prompt: str, model_name: str | None = None) -> AgentRunResult:
        agent = self._build_agent(model_name)
        return await agent.run(prompt)

    def run(self, prompt: str, model_name: str | None = None) -> AgentRunResult:
        return asyncio.run(self.run_async(prompt, model_name))

