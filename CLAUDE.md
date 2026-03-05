# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目简介

基于 FastAPI + Claude Agent SDK 的 AI Agent 服务，支持 Skill 扩展和插件化 Channel 集成（如云之家）。多租户架构，支持动态模型供应商切换（GLM-4、Claude Router）。

## 开发命令

```bash
# 启动/停止/重启服务（带自动重载）
./run.sh start
./run.sh stop
./run.sh          # 默认重启

# 交互式 CLI 调试（无需启动服务器）
source .venv/bin/activate && python cli.py

# 批量测试 customer-service skill
python tests/batch_test.py tests/dataset/test_set_1.md
python tests/batch_test.py -p "问题内容" --default-product "星瀚旗舰版"
python tests/batch_test.py tests/dataset/test_set_1.md --concurrency 3 --timeout 600

# 插件管理 CLI
python manage_plugins.py list|info|enable|disable|install|doctor
```

## 关键路径

- `AGENTS_ROOT` = 项目根目录（`api/constants.py` 中定义）
- `AGENT_CWD` = Agent 工作目录（默认 `agent_cwd/`，通过 `.env` 的 `AGENT_CWD` 变量配置）
  - `agent_cwd/.claude/skills/` — Skills 定义（每个 Skill 含 `SKILL.md`）
  - `agent_cwd/data/kb/` — 知识库文件（Skill 通过 Grep/Read 工具搜索）
  - `agent_cwd/data/tenants/` — 租户数据
- `plugins/bundled/` — 内置插件（如云之家）
- `plugins/installed/` — 用户安装的插件
- `plugins/config.json` — 插件启用列表与配置参数
- 日志：`log/app.log`（服务）、`log/cli.log`（CLI）、`log/batch.log`（批量测试）
- 测试结果：`tests/results/`

## 代码架构

### 请求处理流程

```
POST /api/query
  → api/routers/agent.py          # SSE streaming 路由
  → api/services/agent_service.py # 组装 prompt、配置 Claude SDK
      → api/utils/prompt_builder.py  # 构建初始 prompt（skill 名 + 租户上下文）
      → claude_agent_sdk (ClaudeSDKClient)  # cwd=AGENT_CWD，Skill 在此目录被发现
  → api/core/streaming.py         # StreamProcessor 处理 SDK 消息流
      → 发送 SSE 事件：session_created / assistant_message / ask_user_question / todos_update / result / error
```

### 服务层（`api/services/`）

- **`AgentService`** — 核心业务逻辑：组装 prompt、配置 `ClaudeAgentOptions`（allowed_tools、max_turns=30、setting_sources=["project"]）、启动流式处理。初始化时写入 `.custom-settings.json` 安全配置（拒绝读取 `.env`、密钥文件等）。
- **`SessionService`** — 用 `asyncio.Lock` 管理活跃 Agent 会话，支持中断（`POST /api/interrupt/{session_id}`）。
- **`ConfigService`** — 用 `threading.Lock` 实现线程安全的模型供应商动态切换（`/api/config/switch`）。

### 插件系统（`api/plugins/`）

Channel 插件架构：`PluginManager` 协调 Discovery → Load → Register → Lifecycle。

- **`channel.py`** — `ChannelPlugin` 抽象基类，实现 `get_meta()`, `get_capabilities()`, `create_router()`, `send_text()`，可选 `on_start()`/`on_stop()`
- **`manager.py`** — 负责插件发现、加载、路由注册到 FastAPI、生命周期管理
- **`session_mapper.py`** — 通用外部 sessionId ↔ Agent session_id 映射，供所有 Channel 插件复用
- **`api.py`** — 向插件注入 `AgentService` 和 `SessionService` 的 `PluginAPI` 容器

### Skill 系统

Skills 是 Claude Agent SDK 的 [Agent Skills](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)，在 `AGENT_CWD` 中通过 `SKILL.md` 定义。

Agent 的 allowed_tools 限制为：`Skill`, `Read`, `Grep`, `Glob`, `Bash`, `WebFetch`, `WebSearch`, `AskUserQuestion`。

**注意**：
- Skill 输出最终结果：直接输出内容
- Skill 询问用户：必须使用 `AskUserQuestion` 工具（会触发 `ask_user_question` SSE 事件）

### 云之家插件（`plugins/bundled/yunzhijia/`）

1. `POST /yzj/chat?yzj_token=xxx` — 立即返回 200，后台处理
2. 后台任务调用 `AgentService.process_query()`，流式消费 SSE
3. 通过云之家 webhook 发送 markdown/卡片消息

### SSE 事件类型

`heartbeat`, `session_created`, `assistant_message`, `tool_use`, `todos_update`, `ask_user_question`, `result`, `error`

## 环境变量（`.env`）

```bash
AGENT_CWD=agent_cwd              # Agent 工作目录
DEFAULT_MODEL_CONFIG=claude-router  # 或 "glm"
GLM_AUTH_TOKEN=xxx
CLAUDE_ROUTER_AUTH_TOKEN=xxx
CLAUDE_ROUTER_PROXY=http://127.0.0.1:7890  # 可选
PORT=9090
LOG_LEVEL=INFO
# PLUGIN_PATHS=/path1:/path2    # 额外插件搜索路径
```

Claude Router 指 [claude-code-router](https://github.com/musistudio/claude-code-router)（ccr），使用前需运行 `eval "$(ccr activate)"`。
