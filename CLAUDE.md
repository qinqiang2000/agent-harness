# CLAUDE.md

该文件在本项目中为 Claude Code (claude.ai/code) 提供操作指南。

## Project Overview

这是一个使用 FastAPI 和 Claude Agent SDK 构建的 AI Agent 服务。它提供了一个基于 Skill 的可扩展 Agent 系统，具有两个主要集成点：

1. 通用的 `/api/query` 接口，用于程序化访问
2. 云之家 (Yunzhijia) 消息集成，用于企业聊天

系统采用多租户架构，并支持动态模型供应商切换 (Claude Official API, GLM-4, Claude Router)。

> Claude Router指的是[claude-code-router](https://github.com/musistudio/claude-code-router) ，简称ccr，可以将Claude Agent SDK的请求中转到其他LLM，比如: Claude Agent SDK --> ccr --> deepseek
>
> 使用Claude Router时，需每次启动程序运行：eval "$(ccr activate)"  ，具体参考[官方介绍](https://github.com/musistudio/claude-code-router/blob/main/README_zh.md)。

## Development Commands
### Python Environment

```bash
# Create virtual environment
python3 -m venv .venv

# Activate
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

```
### Start/Stop Service

```bash
# Start the API service (with auto-reload)
./run.sh start

# Stop the service
./run.sh stop

# Restart (default)
./run.sh
./run.sh restart

```

服务默认运行在 9090 端口（可通过 `PORT` 环境变量配置）。日志位于 `log/app.log`。

### CLI Debug Tool

```bash
# Interactive REPL for testing agent queries
source .venv/bin/activate
python cli.py
```

CLI 提供了一个交互式终端，用于在不运行完整 API 服务器的情况下测试 Agent 查询。

**CLI 内置命令**：
- `/config` - 显示当前配置（模型、会话、工作目录）
- `/env` - 显示环境变量（包括代理、token、配置等）
- `/new` - 开始新会话
- `/help` - 查看所有命令

### Batch Testing

```bash
source .venv/bin/activate

# Run batch tests with a test dataset
python tests/batch_test.py tests/dataset/test_set_1.md

# Test single question
python tests/batch_test.py -p "星空旗舰版如何配置开票人员？"

# Control concurrency (default 1, recommend ≤3)
python tests/batch_test.py tests/dataset/test_set_1.md --concurrency 3

# Specify default product for auto-answers
python tests/batch_test.py -p "如何配置开票人员？" --default-product "星瀚旗舰版"

```

测试结果以 Markdown 和 JSON 格式保存在 `tests/results/` 中。

## Architecture

### Core Components

**API Layer** (`api/`)

* `routers/agent.py` - 通用 `/api/query` 接口 (SSE streaming)
* `routers/yunzhijia.py` - 云之家 webhook 集成 (`/yzj/chat`)
* `dependencies.py` - 单例服务注入容器

**Service Layer** (`api/services/`)

* `AgentService` - 编排 Claude SDK 查询、Prompt 组装
* `SessionService` - 管理活跃 Agent 会话（支持中断）
* `ConfigService` - 动态模型供应商切换（线程安全）

**Core Processing** (`api/core/`)

* `StreamProcessor` - 处理 Claude SDK 消息流，发送 SSE 事件

**Handlers** (`api/handlers/`)

* `yunzhijia/handler.py` - 带有会话映射的云之家消息处理
* `yunzhijia/message_sender.py` - 通过 webhook 将消息发回云之家
* `yunzhijia/card_builder.py` - 构建包含图片的富卡片消息
* `yunzhijia/session_mapper.py` - 将云之家会话 ID 映射到 Agent 会话

**CLI** (`cli/`)

* `repl.py` - 带有 SSE 流式显示的交互式 REPL
* `command_handler.py` - 特殊命令 (/switch, /sessions, /quit)
* `stream_renderer.py` - 基于终端的 SSE 流渲染

### Request Flow

1. **API Request** → `/api/query` (FastAPI 接口)
2. **Service Layer** → `AgentService.process_query()`
3. **Prompt Assembly** → 结合 skill/context 调用 `build_initial_prompt()`
4. **Claude SDK** → 使用 Agent SDK 选项调用 `ClaudeSDKClient`
5. **Stream Processing** → `StreamProcessor` 处理消息类型
6. **SSE Events** → 推送流至客户端：`session_created`, `assistant_message`, `tool_use`, `todos_update`, `result`

### Session Management

* **内存会话** 在 `SessionService` 中跟踪
* 会话在收到第一条消息时注册，在完成后注销
* **中断支持**：`POST /api/interrupt/{session_id}` 终止活跃会话
* 云之家会话通过 `session_mapper` 映射（30 分钟超时）

### Model Configuration

系统支持动态模型供应商切换：

```python
# Defined in api/services/config_service.py
PREDEFINED_CONFIGS = {
    "claude": ModelConfig(...),        # Claude Official API (官方 API)
    "glm": ModelConfig(...),           # GLM-4 (智谱清言)
    "claude-router": ModelConfig(...)  # Local Claude proxy
}

```

默认配置通过 `DEFAULT_MODEL_CONFIG` 环境变量设置。可在运行时通过 `ConfigService.switch_config()` 切换。

## Skill System

Skills 是从 `.claude/skills/` 加载的 Claude Code 技能。样例的技能为：

**customer-service** - 发票云客服 Agent

* 处理售前（产品能力）、售后（故障排除）、API 集成等问题
* 知识库位于 `data/kb/`：
  * `产品与交付知识/` - 产品/交付文档 (默认)
  * `营销知识库/` - 营销/销售材料
  * `API文档/` - API 文档
* 多产品消歧：当存在多个产品时，会阻断并询问用户

**operational-analytics** - 运营分析 Agent

* 处理 EOP（Enterprise Operation Platform，运营平台）数据库查询与分析
* 数据库表：
  * `t_ocm_kbc_order_settle` - 销售出库单/结算单（107K+ 记录）
  * `t_ocm_order_header` - 交易订单主表（109K+ 记录）
  * `t_ocm_order_lines` - 产品订单明细（114K+ 记录）
  * `t_ocm_tenant` - 租户表（35K+ 记录）
* 查询类型：订单查询、数据统计、趋势分析、报表生成
* 输出格式：Markdown 表格、SQL 透明化展示
* 安全机制：SELECT-only、表白名单、关键词黑名单、查询超时保护
* 触发词：EOP、运营平台、订单查询、租户数据、销售统计、t_ocm_*表

Skills 通过查询中的 `Skill` 工具调用。

### Skill Output Mechanism

**Skills 使用 Claude SDK 原生输出机制：**

- **最终输出**：直接输出内容，SDK 自动包装到 `ResultMessage.result` 字段
- **询问用户**：必须使用 `AskUserQuestion` 工具（禁止直接输出问题）
- **kb:// 链接**：使用 `kb://相对路径` 引用知识库文档，系统自动转换为实际 URL

**已废弃**：`<reply>` 和 `<ask>` 标签系统（代码保留用于回滚）

## Key Environment Variables

在 `.env` 中配置：

```bash
# Model provider selection
DEFAULT_MODEL_CONFIG=claude-router  # Options: "claude", "glm", "claude-router"

# Model provider auth tokens
CLAUDE_CODE_OAUTH_TOKEN=xxx         # Claude Official API (https://console.anthropic.com)
GLM_AUTH_TOKEN=xxx                  # GLM-4 (智谱清言)
CLAUDE_ROUTER_AUTH_TOKEN=xxx        # Claude Router (本地代理)

# Proxy settings (optional)
CLAUDE_PROXY=http://127.0.0.1:7890           # For Claude Official API
CLAUDE_ROUTER_PROXY=http://127.0.0.1:7890   # For Claude Router

# Service config
PORT=9090
LOG_LEVEL=INFO

# Yunzhijia integration
YZJ_CARD_TEMPLATE_ID=xxx
YZJ_MAX_IMG_PER_CARD=5
SERVICE_BASE_URL=http://your-public-ip:9090
YZJ_SESSION_TIMEOUT=3600  # 60 minutes
YZJ_VERBOSE=true  # false for concise mode

# PostgreSQL Database (for operational-analytics skill)
POSTGRES_HOST=bj-postgres-68aob3ms.sql.tencentcdb.com
POSTGRES_PORT=22898
POSTGRES_DATABASE=postgres
POSTGRES_USER=agent_eop
POSTGRES_PASSWORD=Fapiaoyun@2026
POSTGRES_QUERY_TIMEOUT=60
POSTGRES_ALLOWED_TABLES=t_ocm_kbc_order_settle,t_ocm_order_header,t_ocm_order_lines,t_ocm_tenant

```

## SSE Message Types

`/api/query` 接口推送以下 Server-Sent Events：

* `heartbeat` - 连接状态
* `session_created` - 新会话 ID (第一条消息)
* `assistant_message` - 来自 Agent 的文本响应
* `tool_use` - 工具调用 (信息性)
* `todos_update` - 来自 TodoWrite 的任务列表更新
* `ask_user_question` - Agent 请求用户输入
* `result` - 带有会话统计的最终结果
* `error` - 错误信息

## Yunzhijia Integration

云之家接口接收来自企业聊天的消息并通过 webhook 响应：

1. **Receive**: `POST /yzj/chat?yzj_token=xxx` (立即返回 200 响应)
2. **Process**: 后台任务处理 Agent 查询
3. **Reply**: 通过云之家 webhook 发送 markdown/卡片消息
4. **Interrupts**: 检测到同一会话的新消息 → 中断之前的查询

会话管理：

* 映射云之家 `sessionId` → Agent `session_id`
* 60 分钟不活跃超时

## Important Paths

* `AGENTS_ROOT` = 项目根目录 (Claude SDK 的工作目录，可配置)
* 本地数据在 `data`（可配置）
* 日志位于 `log/app.log` (重启时轮转)
* CLI 日志位于 `log/cli.log`
* 测试结果位于 `tests/results/`

## Concurrency & Thread Safety

* `ConfigService` 使用 `threading.Lock` 进行原子配置切换
* `SessionService` 使用 `asyncio.Lock` 实现异步安全的会话注册
* 通过 FastAPI 的异步工作池处理多个并发请求

## Claude SDK Configuration

```python
ClaudeAgentOptions(
    system_prompt={"type": "preset", "preset": "claude_code"},
    setting_sources=["project"],  # 从 .claude/settings.local.json 加载
    allowed_tools=["Skill", "Read", "Grep", "Glob", "Bash", "WebFetch", "WebSearch", "AskUserQuestion"],
    resume=session_id,  # 用于会话续接
    max_buffer_size=10 * 1024 * 1024,
    cwd=str(AGENTS_ROOT)
)

```

Skills 可通过 `.claude/skills/` 中的项目设置访问。