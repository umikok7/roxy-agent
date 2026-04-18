# My Deer Flow

一个场景特化的 Agent Harness 项目，目前仍在积极开发中。

## 快速开始

```bash
# 安装依赖
uv sync

# 运行后端
cd APP && uvicorn main:app --reload

# 运行前端
cd frontend && npm run dev
```

## 项目概述

My Deer Flow 旨在构建一个模块化的 AI Agent运行时引擎，核心包含：

- **Agent 循环**：支持多轮 tool_call -> tool_result 的异步执行循环
- **Tool 系统**：可扩展的工具注册与执行机制
- **Sandbox 安全执行**：本地文件系统与命令的权限隔离环境
- **多模型支持**：OpenAI 兼容的 Chat Completions 调用链


## 目录结构

```
my-deer-flow/
├── harness/               # 核心 Agent 运行时引擎
│   ├── agents/            # Agent 循环逻辑
│   ├── tools/             # 工具注册与执行
│   ├── sandbox/           # 安全执行环境
│   ├── config/            # 配置管理
│   └── models/            # 数据结构定义
├── APP/                   # FastAPI 应用层
│   ├── api/               # API 路由
│   ├── dto/               # 数据传输对象
│   └── service/           # 业务逻辑层
├── frontend/              # Next.js 前端
├── tests/                 # 测试文件
└── docs/                  # 文档
```


## 状态

项目处于早期阶段，核心架构已初步成型，更多功能正在陆续添加中。
