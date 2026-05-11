from __future__ import annotations

from harness.subagents.config import SubagentConfig


GENERAL_PURPOSE_SUBAGENT = SubagentConfig(
    name="general-purpose",
    description="Use for non-trivial delegated tasks that need exploration or multiple steps.",
    system_prompt=(
        "You are a delegated subagent working on a focused task.\n"
        "- Complete the task autonomously.\n"
        "- Use tools when needed.\n"
        "- Do not ask the user follow-up questions.\n"
        "- Return a concise summary with key findings and any touched files.\n"
        "- Never call the task tool."
    ),
    tools=None,
    disallowed_tools=["task"],
    model="inherit",
    max_steps=8,
)


BASH_SUBAGENT = SubagentConfig(
    name="bash",
    description="Use for verbose shell-oriented delegated work.",
    system_prompt=(
        "You are a shell-focused delegated subagent.\n"
        "- Prefer bash, ls, read_file, write_file, and str_replace.\n"
        "- Execute carefully and summarize command results clearly.\n"
        "- Never call the task tool."
    ),
    tools=["bash", "ls", "read_file", "write_file", "str_replace"],
    disallowed_tools=["task", "web_search", "browser_search", "browser_open"],
    model="inherit",
    max_steps=6,
)


BUILTIN_SUBAGENTS: dict[str, SubagentConfig] = {
    GENERAL_PURPOSE_SUBAGENT.name: GENERAL_PURPOSE_SUBAGENT,
    BASH_SUBAGENT.name: BASH_SUBAGENT,
}


def get_subagent_config(name: str) -> SubagentConfig | None:
    return BUILTIN_SUBAGENTS.get(name)


def list_subagents() -> list[SubagentConfig]:
    return list(BUILTIN_SUBAGENTS.values())
