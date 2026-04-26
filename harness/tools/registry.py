from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from harness.sandbox.runtime import BasicSandbox
from harness.tools.web_search import WebSearchClient

ToolHandler = Callable[[dict[str, Any]], Awaitable[str]]


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]


class ToolRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}
        self._handlers: dict[str, ToolHandler] = {}

    def register(self, spec: ToolSpec, handler: ToolHandler) -> None:
        self._specs[spec.name] = spec
        self._handlers[spec.name] = handler

    def get_handler(self, name: str) -> ToolHandler | None:
        return self._handlers.get(name)

    def list_tool_schemas(self) -> list[dict[str, Any]]:
        schemas: list[dict[str, Any]] = []
        for spec in self._specs.values():
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": spec.name,
                        "description": spec.description,
                        "parameters": spec.parameters,
                    },
                }
            )
        return schemas

    @classmethod
    def with_default_tools(
        cls,
        sandbox: BasicSandbox,
        *,
        web_search_client: WebSearchClient | None = None,
    ) -> "ToolRegistry":
        registry = cls()
        search_client = web_search_client or WebSearchClient()

        async def bash_tool(args: dict[str, Any]) -> str:
            command = str(args.get("command", ""))
            return await asyncio.to_thread(sandbox.run_bash, command)

        async def ls_tool(args: dict[str, Any]) -> str:
            path = str(args.get("path", "."))
            return await asyncio.to_thread(sandbox.list_dir, path)

        async def read_file_tool(args: dict[str, Any]) -> str:
            path = str(args.get("path", ""))
            start_line = args.get("start_line")
            end_line = args.get("end_line")
            return await asyncio.to_thread(sandbox.read_file, path, start_line, end_line)

        async def write_file_tool(args: dict[str, Any]) -> str:
            path = str(args.get("path", ""))
            content = str(args.get("content", ""))
            append = bool(args.get("append", False))
            return await asyncio.to_thread(sandbox.write_file, path, content, append)

        async def str_replace_tool(args: dict[str, Any]) -> str:
            path = str(args.get("path", ""))
            old_str = str(args.get("old_str", ""))
            new_str = str(args.get("new_str", ""))
            replace_all = bool(args.get("replace_all", False))
            return await asyncio.to_thread(sandbox.str_replace, path, old_str, new_str, replace_all)

        async def web_search_tool(args: dict[str, Any]) -> str:
            query = str(args.get("query", ""))
            max_results = int(args.get("max_results", 5))
            return await asyncio.to_thread(lambda: search_client.search(query, max_results=max_results))

        registry.register(
            ToolSpec(
                name="bash",
                description="Run a shell command inside sandbox root directory.",
                parameters={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Shell command to run."}
                    },
                    "required": ["command"],
                },
            ),
            bash_tool,
        )
        registry.register(
            ToolSpec(
                name="ls",
                description="List directory entries.",
                parameters={
                    "type": "object",
                    "properties": {"path": {"type": "string", "description": "Relative path in sandbox."}},
                },
            ),
            ls_tool,
        )
        registry.register(
            ToolSpec(
                name="read_file",
                description="Read file content with optional line range.",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "start_line": {"type": "integer"},
                        "end_line": {"type": "integer"},
                    },
                    "required": ["path"],
                },
            ),
            read_file_tool,
        )
        registry.register(
            ToolSpec(
                name="write_file",
                description="Write or append content to a file.",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                        "append": {"type": "boolean"},
                    },
                    "required": ["path", "content"],
                },
            ),
            write_file_tool,
        )
        registry.register(
            ToolSpec(
                name="str_replace",
                description="Replace one or all occurrences in a file.",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "old_str": {"type": "string"},
                        "new_str": {"type": "string"},
                        "replace_all": {"type": "boolean"},
                    },
                    "required": ["path", "old_str", "new_str"],
                },
            ),
            str_replace_tool,
        )
        registry.register(
            ToolSpec(
                name="web_search",
                description="Search the public web and return a short list of relevant results.",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query."},
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of results to return (1-10).",
                        },
                    },
                    "required": ["query"],
                },
            ),
            web_search_tool,
        )

        return registry
