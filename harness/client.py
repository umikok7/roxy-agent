from __future__ import annotations

import asyncio
import shutil
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable

from harness.agents.loop import AsyncAgentLoop, LoopSettings, OpenAIChatCompletionsClient
from harness.agents.prompt import build_system_instructions
from harness.config.settings import HarnessConfig, load_harness_config
from harness.context import ThreadRuntimePaths
from harness.models.types import AgentRunResult, RuntimeContext
from harness.rag import KnowledgeBaseService
from harness.sandbox.runtime import BasicSandbox
from harness.skills import Skill, load_skills
from harness.subagents import (
    SubagentExecutor,
    SubagentResult,
    SubagentStatus,
    cleanup_background_task,
    get_background_task_result,
    get_subagent_config,
)
from harness.tools.executor import ToolExecutor
from harness.tools.registry import ToolRegistry, ToolRuntime


def resolve_project_root(start_path: Path) -> Path:
    current = start_path.resolve()
    if current.is_file():
        current = current.parent
    for candidate in [current, *current.parents]:
        if (candidate / "pyproject.toml").exists() and (candidate / "harness").is_dir():
            return candidate
    return current


class HarnessClient:
    def __init__(self, config: HarnessConfig | None = None, *, project_root: Path | None = None) -> None:
        self._project_root = resolve_project_root(project_root or Path.cwd())
        self.config = config or load_harness_config(self._project_root)
        self._sandbox_root = self.config.sandbox.root_dir
        self._knowledge_base: KnowledgeBaseService | None = None

    def _get_knowledge_base(self) -> KnowledgeBaseService:
        if self._knowledge_base is None:
            self._knowledge_base = KnowledgeBaseService(self.config.rag)
        return self._knowledge_base

    def _load_enabled_skills(
        self,
        *,
        sync_to_sandbox: bool = True,
        thread_paths: ThreadRuntimePaths | None = None,
    ) -> list[Skill]:
        skills_path = self._project_root / "skills"
        extensions_config_path = str(self._project_root / "extensions_config.json")
        skills = load_skills(
            skills_path=skills_path,
            enabled_only=True,
            extensions_config_path=extensions_config_path,
        )
        if sync_to_sandbox:
            self._sync_skills_into_sandbox(skills, thread_paths=thread_paths)
        return skills

    def list_enabled_skill_names(self) -> list[str]:
        return [item.name for item in self._load_enabled_skills(sync_to_sandbox=False)]

    def _sync_skills_into_sandbox(
        self,
        skills: list[Skill],
        *,
        thread_paths: ThreadRuntimePaths | None = None,
    ) -> None:
        sandbox_root = thread_paths.thread_root if thread_paths is not None else self._sandbox_root
        for item in skills:
            target_path = sandbox_root / item.get_container_file_path("skills")
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item.skill_file, target_path)

    def _make_runtime_context(
        self,
        *,
        selected_model_name: str,
        thread_paths: ThreadRuntimePaths | None,
        thread_id: str | None,
        subagent_depth: int,
        knowledge_base: KnowledgeBaseService | None = None,
    ) -> RuntimeContext:
        return RuntimeContext(
            thread_id=thread_id,
            thread_root=thread_paths.thread_root if thread_paths else self._sandbox_root,
            workspace_dir=thread_paths.workspace_dir if thread_paths else self._sandbox_root,
            model_name=selected_model_name,
            subagent_depth=subagent_depth,
            max_subagents=self.config.runtime.max_concurrent_subagents,
            subagent_timeout_seconds=self.config.runtime.subagent_timeout_seconds,
            knowledge_base=knowledge_base,
        )

    def _make_sandbox(self, thread_paths: ThreadRuntimePaths | None) -> BasicSandbox:
        # 没有沙箱才需要创建
        if thread_paths is None:
            return BasicSandbox(
                self._sandbox_root,
                command_timeout_seconds=self.config.sandbox.command_timeout_seconds,
                max_output_chars=self.config.runtime.max_output_chars,
            )
        # 如果已有沙箱则复用
        return BasicSandbox(
            thread_paths.thread_root,
            command_cwd=thread_paths.workspace_dir,
            command_timeout_seconds=self.config.sandbox.command_timeout_seconds,
            max_output_chars=self.config.runtime.max_output_chars,
        )

    async def _run_subagent(
        self,
        *,
        selected_model_name: str,
        thread_paths: ThreadRuntimePaths | None,
        thread_id: str | None,
        emit_event: Callable[[dict[str, Any]], Awaitable[None] | None] | None,
        description: str,
        prompt: str,
        subagent_type: str,
        max_steps: int | None,
    ) -> str:
        """
        在后台线程中启动一个子任务，并通过 SSE 事件持续汇报进度。

        调用流程：
          1. 根据 subagent_type 从 BUILTIN_SUBAGENTS 获取 SubagentConfig，得到：
             - system_prompt   ：子任务的系统提示词（覆盖默认的）
             - tools/disallowed_tools ：工具白名单/黑名单（用于过滤 ToolRegistry）
             - max_steps       ：最大迭代步数（覆盖默认的）
             - timeout_seconds ：超时时间（默认 900s）
          2. 创建 run_callable 闭包，在其中：
             - 用 _build_agent 构建一个新的 AsyncAgentLoop（subagent_depth=1，禁用嵌套 subagent）
             - 调用 agent.run_with_stream(prompt, on_text_delta=on_delta) 以流式方式执行
             - on_delta 每次收到增量文本就通过 emit_event 发送 "task_running" 事件
             - 若最终结果为空但有 progress_messages，返回拼接后的进度文本作为兜底结果
          3. 用 SubagentExecutor 包装 run_callable，并调用 execute_async() 提交到线程池异步执行
          4. 发送 "task_started" 事件，告知前端任务已启动、task_id 和 description
          5. 进入轮询循环（每 0.1 秒一次），通过 get_background_task_result(task_id) 获取状态：
               - COMPLETED  → 发送 "task_completed"，返回 "Task Succeeded. Result: <结果>"
               - FAILED     → 发送 "task_failed"，抛出 RuntimeError(result.error)
               - TIMED_OUT  → 发送 "task_timed_out"，抛出 RuntimeError("timed out")
          6. 任务结束后调用 cleanup_background_task(task_id) 清理内存中的结果记录

        参数：
          selected_model_name ：用于子任务的模型名称
          thread_paths        ：线程级路径（沙箱根目录、工作目录等），为 None 则使用全局默认
          thread_id           ：线程 ID，用于追踪和上下文传递
          emit_event          ：回调，用于向调用方发送 SSE 事件（task_started / task_running / task_completed / task_failed / task_timed_out）
          description         ：任务的简短描述（发送给前端展示）
          prompt              ：子任务的用户输入
          subagent_type       ：子任务类型，取值来自 BUILTIN_SUBAGENTS（"general-purpose" | "bash"）
          max_steps           ：覆盖子任务最大步数，为 None 则使用 SubagentConfig 中的默认值

        返回：
          字符串格式的最终结果，格式为 "Task Succeeded. Result: <文本>"
        """
        config = get_subagent_config(subagent_type)
        if config is None:
            raise RuntimeError(f"Unknown subagent type: {subagent_type}")

        # 生成唯一 task_id，用于在前端和轮询中追踪任务
        task_id = f"task_{uuid.uuid4().hex[:8]}"
        # 外部传入的 max_steps 优先，否则使用 SubagentConfig 中的默认值
        effective_steps = max_steps or config.max_steps

        # emit 辅助函数：将 payload 异步发送给 emit_event（如果注册了的话）
        async def emit(payload: dict[str, Any]) -> None:
            if emit_event is None:
                return
            maybe = emit_event(payload)
            if maybe is not None:
                await maybe

        async def run_callable(result_holder: SubagentResult) -> str:
            # last_emitted 记录上一次读取 progress_messages 的位置，用于兜底返回
            last_emitted = 0

            # on_delta：每次模型输出增量文本时，将其追加到 progress_messages 并发送 "task_running" 事件
            async def on_delta(delta: str) -> None:
                text = delta.strip()
                if not text:
                    return
                result_holder.progress_messages.append(text)
                await emit({"type": "task_running", "task_id": task_id, "message": text})

            # 构建subagent：
            # - subagent_depth=1 表示当前是嵌套层级，阻止进一步嵌套
            # - subagent_enabled=False 禁用子 agent 进一步调用 task 工具
            # - tool_allowlist/tool_denylist 应用子任务专属的工具过滤规则
            agent = self._build_agent(
                selected_model_name,
                thread_paths=thread_paths,
                subagent_depth=1,
                instructions_override=config.system_prompt,
                tool_allowlist=config.tools,
                tool_denylist=config.disallowed_tools,
                max_steps_override=effective_steps,
                subagent_enabled=False,
                event_callback=emit_event,
                thread_id=thread_id,
            )
            # 以流式方式执行，这样前端可以实时看到输出
            agent_result = await agent.run_with_stream(prompt, on_text_delta=on_delta)
            # 如果最终文本为空但有累计的 progress_messages，用它作为兜底结果
            if not agent_result.text.strip() and len(result_holder.progress_messages) > last_emitted:
                return "\n".join(result_holder.progress_messages[last_emitted:])
            return agent_result.text

        executor = SubagentExecutor(
            task_id=task_id,
            timeout_seconds=config.timeout_seconds or self.config.runtime.subagent_timeout_seconds,
            run_callable=run_callable,
        )
        # 通知前端任务已启动，携带 task_id、description 和 subagent_type
        await emit(
            {
                "type": "task_started",
                "task_id": task_id,
                "description": description,
                "subagent_type": subagent_type,
            }
        )
        # execute_async() 将任务提交到线程池，立即返回，不阻塞
        executor.execute_async()

        # 轮询：每 0.1 秒检查一次任务状态，直到完成/失败/超时
        while True:
            result = get_background_task_result(task_id)
            if result is None:
                raise RuntimeError(f"Subagent task disappeared: {task_id}")
            if result.status == SubagentStatus.COMPLETED:
                await emit({"type": "task_completed", "task_id": task_id, "result": result.result or ""})
                cleanup_background_task(task_id)
                return f"Task Succeeded. Result: {result.result or '(empty response)'}"
            if result.status == SubagentStatus.FAILED:
                await emit({"type": "task_failed", "task_id": task_id, "error": result.error or "unknown error"})
                cleanup_background_task(task_id)
                raise RuntimeError(result.error or "Subagent failed")
            if result.status == SubagentStatus.TIMED_OUT:
                await emit({"type": "task_timed_out", "task_id": task_id, "error": result.error or "timed out"})
                cleanup_background_task(task_id)
                raise RuntimeError(result.error or "Subagent timed out")
            await asyncio.sleep(0.1)

    def _build_agent(
        self,
        model_name: str | None = None,
        *,
        thread_paths: ThreadRuntimePaths | None = None,
        pinned_skills: list[str] | None = None,
        compact_summary: str | None = None,
        subagent_depth: int = 0,
        instructions_override: str | None = None,
        tool_allowlist: list[str] | None = None,
        tool_denylist: list[str] | None = None,
        max_steps_override: int | None = None,
        subagent_enabled: bool | None = None,
        event_callback: Callable[[dict[str, Any]], Awaitable[None] | None] | None = None,
        thread_id: str | None = None,
    ) -> AsyncAgentLoop:
        selected_model = self.config.get_model(model_name)
        sandbox = self._make_sandbox(thread_paths)
        knowledge_base = self._get_knowledge_base()
        effective_subagent_enabled = self.config.runtime.subagents_enabled if subagent_enabled is None else subagent_enabled
        include_task_tool = effective_subagent_enabled and subagent_depth == 0
        registry = ToolRegistry.with_default_tools(
            sandbox,
            knowledge_base=knowledge_base,
            include_task_tool=include_task_tool,
        )
        if tool_allowlist is not None or tool_denylist is not None:
            registry = registry.filtered(allowlist=tool_allowlist, denylist=tool_denylist)

        runtime_context = self._make_runtime_context(
            selected_model_name=selected_model.name,
            thread_paths=thread_paths,
            thread_id=thread_id,
            subagent_depth=subagent_depth,
            knowledge_base=knowledge_base,
        )

        runtime = ToolRuntime(
            sandbox=sandbox,
            context=runtime_context,
            emit_event=event_callback,
            run_subagent=(
                None
                if not include_task_tool
                else lambda description, prompt, subagent_type, max_steps: self._run_subagent(
                    selected_model_name=selected_model.name,
                    thread_paths=thread_paths,
                    thread_id=thread_id,
                    emit_event=event_callback,
                    description=description,
                    prompt=prompt,
                    subagent_type=subagent_type,
                    max_steps=max_steps,
                )
            ),
        )
        tool_executor = ToolExecutor(registry, runtime)
        tool_schemas = registry.list_tool_schemas()
        skills = self._load_enabled_skills(thread_paths=thread_paths)
        model_client = OpenAIChatCompletionsClient(
            api_key=selected_model.read_api_key(),
            base_url=selected_model.base_url,
        )

        instructions = instructions_override or build_system_instructions(
            skills,
            container_base_path="skills",
            pinned_skills=pinned_skills,
            compact_summary=compact_summary,
            subagent_enabled=include_task_tool,
            max_concurrent_subagents=self.config.runtime.max_concurrent_subagents,
        )

        return AsyncAgentLoop(
            model_client=model_client,
            tool_executor=tool_executor,
            tool_schemas=tool_schemas,
            settings=LoopSettings(
                model=selected_model.model,
                max_steps=max_steps_override or self.config.runtime.max_steps,
                temperature=selected_model.temperature,
                max_tokens=selected_model.max_tokens,
            ),
            instructions=instructions,
            max_concurrent_subagents=self.config.runtime.max_concurrent_subagents,
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

    async def run_async(
        self,
        prompt: str,
        model_name: str | None = None,
        *,
        on_text_delta: Callable[[str], Awaitable[None] | None] | None = None,
        conversation_history: list[dict[str, Any]] | None = None,
        thread_id: str | None = None,
        thread_paths: ThreadRuntimePaths | None = None,
        pinned_skills: list[str] | None = None,
        compact_summary: str | None = None,
        event_callback: Callable[[dict[str, Any]], Awaitable[None] | None] | None = None,
    ) -> AgentRunResult:
        agent = self._build_agent(
            model_name,
            thread_paths=thread_paths,
            pinned_skills=pinned_skills,
            compact_summary=compact_summary,
            event_callback=event_callback,
            thread_id=thread_id,
        )
        if on_text_delta is None:
            return await agent.run(prompt, history_messages=conversation_history)
        return await agent.run_with_stream(prompt, on_text_delta=on_text_delta, history_messages=conversation_history)

    def run(self, prompt: str, model_name: str | None = None) -> AgentRunResult:
        return asyncio.run(self.run_async(prompt, model_name))
