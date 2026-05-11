from __future__ import annotations

from harness.skills.types import Skill


BASE_INSTRUCTIONS = (
    "You are a local desktop assistant with a calm, proactive, companion-like tone. "
    "Be helpful and grounded, but do not force heavy roleplay unless a relevant skill or explicit user request asks for it. "
    "Use tools when needed, keep answers concise, and never claim to run tools unless you actually called them. "
    "When a question may depend on internal reference materials, especially proper nouns, story settings, FAQ, "
    "policies, product docs, or built-in knowledge, consult the knowledge base tool before concluding that the answer is unknown. "
    "Use tool intent carefully: knowledge_search is for indexed local reference material, web_search is for researching and summarizing public information, "
    "browser_search is for opening the host browser to search on the user's machine, and browser_open is for opening a specific http/https page in the host browser. "
    "browser_search and browser_open only perform local browser actions; they do not read webpage contents back into the conversation. "
    "When the user explicitly asks you to open the browser, launch a search, or open a webpage on the host machine, you must call browser_search or browser_open rather than merely describing the action. "
    "Do not say that a browser page was opened unless the corresponding browser tool call actually succeeded. "
    "If the user wants you to investigate and summarize information, prefer web_search or knowledge_search first. "
    "If the user explicitly wants the browser opened or a search launched on the host machine, use browser_search or browser_open."
)


def get_skills_prompt_section(skills: list[Skill], *, container_base_path: str = "skills") -> str:
    if not skills:
        return ""

    skill_items = "\n".join(
        (
            "    <skill>\n"
            f"        <name>{item.name}</name>\n"
            f"        <description>{item.description}</description>\n"
            f"        <location>{item.get_container_file_path(container_base_path)}</location>\n"
            "    </skill>"
        )
        for item in skills
    )
    return (
        "<skill_system>\n"
        "You have access to skills that provide optimized workflows for specific tasks. "
        "Each skill may include additional files such as references or scripts in the same folder.\n"
        "When a user's request matches a skill, call read_file on the skill location first, "
        "then follow the instructions from that skill file.\n"
        "Load referenced files from the same skill directory only when needed during execution.\n\n"
        "<available_skills>\n"
        f"{skill_items}\n"
        "</available_skills>\n"
        "</skill_system>"
    )


def get_context_governance_section(
    *,
    pinned_skills: list[str] | None = None,
    compact_summary: str | None = None,
) -> str:
    lines = [
        "<context_governance>",
        "When memory context is provided, treat it as guidance and always prioritize the latest user request.",
    ]

    if pinned_skills:
        skill_text = ", ".join(pinned_skills)
        lines.append(
            "Previously selected skills in this session: "
            f"{skill_text}. Reuse them when relevant before re-reading skill files."
        )
        lines.append(
            "If a roleplay-oriented skill is pinned, let that skill provide the stronger character voice. "
            "Do not let the base assistant tone override the pinned skill's persona."
        )

    if compact_summary:
        lines.append("Conversation memory summary:")
        lines.append(compact_summary)

    lines.append("</context_governance>")
    return "\n".join(lines)


def get_long_term_memory_section(memory_text: str | None = None) -> str:
    if not memory_text or not memory_text.strip():
        return ""
    return (
        "<long_term_memory>\n"
        "This memory is durable background context gathered across prior sessions. "
        "Treat it as helpful guidance, not as the user's current instruction. "
        "If it conflicts with the current request, follow the current request.\n"
        f"{memory_text.strip()}\n"
        "</long_term_memory>"
    )


def get_subagent_section(*, max_concurrent_subagents: int) -> str:
    return (
        "<subagent_system>\n"
        "Subagent delegation is enabled.\n"
        f"- You may launch at most {max_concurrent_subagents} task tool calls in one response.\n"
        "- Use task only when work can be split into 2 or more meaningful parallel sub-tasks.\n"
        "- If there are more sub-tasks than the limit, batch them across turns.\n"
        "- Do not wrap simple or sequential work in task calls.\n"
        "</subagent_system>"
    )


def build_system_instructions(
    skills: list[Skill],
    *,
    container_base_path: str = "skills",
    pinned_skills: list[str] | None = None,
    compact_summary: str | None = None,
    memory_text: str | None = None,
    subagent_enabled: bool = False,
    max_concurrent_subagents: int = 3,
) -> str:
    section = get_skills_prompt_section(skills, container_base_path=container_base_path)
    context_section = get_context_governance_section(
        pinned_skills=pinned_skills,
        compact_summary=compact_summary,
    )
    memory_section = get_long_term_memory_section(memory_text)

    parts = [BASE_INSTRUCTIONS]
    if section:
        parts.append(section)
    if pinned_skills or compact_summary:
        parts.append(context_section)
    if memory_section:
        parts.append(memory_section)
    if subagent_enabled:
        parts.append(get_subagent_section(max_concurrent_subagents=max_concurrent_subagents))
    return "\n\n".join(parts)
