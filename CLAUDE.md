# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

My Deer Flow is a modular AI Agent runtime engine with:
- **Agent Loop**: Async tool_call -> tool_result execution cycle with multi-step support
- **Tool System**: Extensible tool registration via `harness/tools/registry.py`
- **Sandbox Security**: Filesystem and command permission isolation in `harness/sandbox/runtime.py`
- **Multi-Model Support**: OpenAI-compatible Chat Completions calling chain
- **Skills System**: Session-pinned skills loaded from `skills/public/` and `skills/custom/`
- **Thread Context**: Per-thread JSON context store with pinned_skills and compact_summary

## Commands

### Full Stack (using Make)
```bash
# First-time setup (installs all dependencies)
make bootstrap

# Start all services (qdrant + backend + frontend + desktop)
make up

# Check status and health
make status
make health

# View logs
make logs SERVICE=backend
make down
```

### Backend
```bash
# Install dependencies
uv sync

# Run backend
cd APP && uvicorn main:app --reload

# Run tests
pytest tests/ -v

# Run a single test file
pytest tests/test_agent_loop.py -v
```

### Frontend
```bash
cd frontend
npm install
npm run dev
npm run build
npm run lint
```

### Desktop Client
```bash
cd desktop
npm install
npm run dev
```

## Architecture

### Request Flow
1. Frontend (`frontend/src/lib/api.ts`) calls `/chat` or `/chat/stream`
2. FastAPI (`APP/api/app.py`) routes to `ChatService`
3. `HarnessClient` (`harness/client.py`) assembles runtime: `BasicSandbox + ToolRegistry + ToolExecutor + OpenAIChatCompletionsClient + AsyncAgentLoop`
4. `AsyncAgentLoop.run()` executes the agent loop:
   - Calls model → parses tool_calls → executes via `ToolExecutor` → fills assistant/tool messages → loops until no tool_calls or max_steps reached
5. Results stream back via SSE or return as `ChatResponse`

### Core Files
- `harness/agents/loop.py`: `AsyncAgentLoop` with `OpenAIChatCompletionsClient`
- `harness/tools/registry.py`: `ToolRegistry.with_default_tools()` — registers 6 tools: bash, ls, read_file, write_file, str_replace, web_search
- `harness/tools/executor.py`: `ToolExecutor.execute_batch()` dispatches to handlers
- `harness/sandbox/runtime.py`: `BasicSandbox` enforces path boundaries and blocks dangerous commands (rm -rf, sudo, shutdown, etc.)
- `harness/context/thread_store.py`: Thread-level JSON context persistence
- `harness/skills/loader.py`: Loads skills from `skills/{public,custom}/*/SKILL.md`
- `harness/client.py`: `HarnessClient` assembles the runtime: `BasicSandbox + ToolRegistry + ToolExecutor + OpenAIChatCompletionsClient + AsyncAgentLoop`

### Configuration
Environment variables (defined in `harness/config/settings.py`):
- `MINIMAX_API_KEY` — API key for default model
- `HARNESS_DEFAULT_MODEL` — default model name (default: minimax-m2.7)
- `HARNESS_SANDBOX_ROOT` — sandbox root directory (default: .sandbox)
- `HARNESS_MAX_STEPS` — max agent loop iterations (default: 8)

### Skills System
Skills are Markdown files at `skills/{public,custom}/*/SKILL.md` with frontmatter for metadata. They are enabled/disabled via `extensions_config.json`. Enabled skills are injected into the agent's system prompt and synced into the sandbox filesystem.

## Reading Order
For understanding the codebase, read in this order:
1. `APP/api/app.py` — entry point
2. `harness/client.py` — runtime assembly
3. `harness/agents/loop.py` — agent loop
4. `harness/tools/registry.py` — tool registration
5. `harness/sandbox/runtime.py` — sandbox security
