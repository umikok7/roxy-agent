# roxy-agent

<div align="center">
  <img src="desktop/assets/roxy/roxy-idle.svg" alt="Roxy - Your Desktop Companion" width="128" height="128" />
  <p>
    <strong>roxy-agent</strong> — 服务于洛神教的专属桌面 Agent，基于 deer-flow构建的模块化 AI Agent 运行时引擎。
  </p>
  <p>
    <img src="https://img.shields.io/badge/Python-3.11+-blue.svg" alt="Python">
    <img src="https://img.shields.io/badge/Node.js-18+-green.svg" alt="Node">
    <img src="https://img.shields.io/badge/Platform-macOS%20%7C%20Windows-blueviolet.svg" alt="Platform">
  </p>
</div>

---

## 项目简介

roxy-agent 是专为洛神教打造的桌面 AI Agent。它将像素风格的 Roxy ”桌宠“与强大的 Agent 能力结合，为你带来一个可交互、有灵魂的桌面助手。

## 对话展示

双击打开对话的轻交互模式

| 对话列表                       | 对话详情                                     |
|----------------------------|------------------------------------------|
| ![chat.png](docs/chat.png) | ![chat-result.png](docs/chat-result.png) |

### 核心特性

- **桌面桌宠**：像素风格的 Roxy 桌宠，内置于 Electron 应用，实时响应 Agent 状态
- **Agent 能力**：基于简易的deer-flow的完整Harness系统
- **RoxySkills**：内置蒸馏好的洛琪希角色技能系统，深度定制的角色 prompt 和行为模式
- **可扩展性**：完整的工具注册与执行框架，轻松添加自定义工具
- **沙箱安全**：基于路径边界和命令过滤的本地安全执行环境

### 灵感来源

本项目参考三个开源项目的核心能力：

| 项目 | 贡献 |
|------|------|
| [deer-flow](https://github.com/bytedance/deer-flow) | 模块化 Agent 运行时引擎核心 |
| [clawd-on-desk](https://github.com/rullerzhou-afk/clawd-on-desk) | Electron 桌宠实现参考 |
| [RoxySkills](https://github.com/umikok7/Roxy-SKILL) | 洛琪希角色定制化技能系统 |

## 快速开始

### 环境要求

- **Python**: 3.11+
- **Node.js**: 18+
- **pnpm** (推荐) 或 npm

### 安装与运行

```bash
# 1. 克隆项目
git clone https://github.com/umikok7/my-deer-flow.git
cd my-deer-flow

# 2. 安装后端依赖
uv sync

# 3. 启动后端 API 服务
cd APP && uvicorn main:app --reload

# 4. 新开终端，启动前端（可选，用于 Web 界面）
cd frontend && npm install && npm run dev

# 5. 新开终端，启动桌面客户端
cd desktop && npm install && npm run dev
```

### 一键启动所有服务

现在也可以直接从项目根目录统一管理全部服务：

```bash
# 首次安装依赖
make bootstrap

# 一键启动 qdrant + backend + frontend + desktop
make up

# 查看状态与健康检查
make status
make health

# 查看日志
make logs SERVICE=backend
make frontend-logs
make desktop-logs

# 一键停止
make down
```

运行说明：

- `make up` 会后台启动 `qdrant`、FastAPI 后端、Next.js 前端和 Electron desktop
- 日志会写入 `.runtime/logs/`
- PID 文件会写入 `.runtime/pids/`
- 如果只是想重启整套开发环境，可以直接执行 `make restart`

### 配置

在项目根目录创建 `.env` 文件：

```env
MINIMAX_API_KEY=your_api_key_here
HARNESS_DEFAULT_MODEL=minimax-m2.7
HARNESS_SANDBOX_ROOT=.sandbox
HARNESS_MAX_STEPS=8
```

## 项目架构

```
my-deer-flow/
├── desktop/               # Electron 桌面客户端
│   ├── assets/roxy/       # Roxy 像素资源
│   └── src/               # 客户端源码
│
├── harness/               # Agent 运行时引擎核心
│   ├── agents/            # AsyncAgentLoop 异步执行循环
│   ├── tools/             # 工具注册与执行 (ToolRegistry, ToolExecutor)
│   ├── sandbox/           # BasicSandbox 权限隔离
│   ├── context/            # ThreadContext 线程级上下文
│   ├── skills/            # SkillsLoader 技能加载
│   └── models/            # 数据结构定义
│
├── APP/                   # FastAPI 应用层
│   ├── api/               # API 路由 (/chat, /chat/stream)
│   ├── dto/               # 数据传输对象
│   └── service/            # ChatService 业务逻辑
│
├── frontend/              # Next.js Web 界面（可选）
├── skills/               # 技能系统
│   ├── public/           # 内置公共技能
│   └── custom/            # 自定义技能（如 roxy-skill）
│
└── tests/                 # 测试文件
```


## 核心模块

### AsyncAgentLoop (`harness/agents/loop.py`)

异步 Agent 执行循环，支持多步 Tool-Call 迭代。

```python
from harness.agents.loop import AsyncAgentLoop

loop = AsyncAgentLoop(client=chat_client, executor=tool_executor)
result = await loop.run(messages, max_steps=8)
```

### ToolRegistry (`harness/tools/registry.py`)

可扩展的工具注册表，默认注册 6 个工具：

| 工具 | 功能 |
|------|------|
| `bash` | 执行 Bash 命令 |
| `ls` | 列出目录内容 |
| `read_file` | 读取文件 |
| `write_file` | 写入文件 |
| `str_replace` | 原地编辑文件 |
| `web_search` | 网页搜索 |

### BasicSandbox (`harness/sandbox/runtime.py`)

安全执行环境，强制：
- 路径边界限制（禁止访问 `.sandbox` 外部）
- 危险命令过滤（`rm -rf`, `sudo`, `shutdown` 等）

### Skills 系统

技能是 Markdown 文件，位于 `skills/{public,custom}/*/SKILL.md`，通过 `extensions_config.json` 启用/禁用。

```
skills/
├── public/        # 内置技能
└── custom/        # 自定义技能
    └── roxy-skill/
        └── SKILL.md
```

## 自定义你的桌宠

想换掉 Roxy？完全可以！roxy-agent 设计为可泛化的 IP 定制框架：

1. **替换像素资源**：将 `desktop/assets/roxy/` 下的 SVG 替换为你喜欢的角色
2. **创建新技能**：在 `skills/custom/` 下创建新的技能目录和 `SKILL.md`
3. **修改 Agent Prompt**：编辑技能文件中的 system prompt 来定义角色行为

## License

MIT License
