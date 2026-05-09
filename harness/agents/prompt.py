from __future__ import annotations

from harness.skills.types import Skill


BASE_INSTRUCTIONS = (
    "You are a minimal coding agent. Use tools when needed, keep answers concise, "
    "and never claim to run tools unless you actually called them. "
    "When a question may depend on internal reference materials, especially proper nouns, story settings, FAQ, "
    "policies, product docs, or built-in knowledge, consult the knowledge base tool before concluding that the answer is unknown."
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

    if compact_summary:
        lines.append("Conversation memory summary:")
        lines.append(compact_summary)

    lines.append("</context_governance>")
    return "\n".join(lines)


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
    subagent_enabled: bool = False,
    max_concurrent_subagents: int = 3,
) -> str:
    section = get_skills_prompt_section(skills, container_base_path=container_base_path)
    context_section = get_context_governance_section(
        pinned_skills=pinned_skills,
        compact_summary=compact_summary,
    )

    parts = [BASE_INSTRUCTIONS]
    if section:
        parts.append(section)
    if pinned_skills or compact_summary:
        parts.append(context_section)
    if subagent_enabled:
        parts.append(get_subagent_section(max_concurrent_subagents=max_concurrent_subagents))
    return "\n\n".join(parts)
