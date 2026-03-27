# Agent Service

这是一个使用 FastAPI 和 Claude Agent SDK 构建的 AI Agent 服务。它提供了一个基于 Skill 的可扩展 Agent 系统，具有两个主要集成点：

1. 通用的 `/api/query` 接口，用于程序化访问
2. 插件化的 Channel 集成（如云之家），通过插件系统无需修改核心代码即可接入新平台

系统采用多租户架构，并支持动态模型供应商切换 (GLM-4, Claude Router)。

## 快速开始

### 1. 环境准备

确保你的系统已安装 Python 3.11+。

```bash
# 克隆项目（如果还没有）
git clone <repository-url>
cd ai-knowledge-base

# 创建虚拟环境
python3 -m venv .venv

# 激活虚拟环境
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置环境变量

复制示例配置文件并根据你的需求修改：

```bash
cp .env.example .env
```

编辑 `.env` 文件，配置以下关键参数：

```bash
# Agent 工作目录（可选，默认为项目根目录）
AGENT_CWD=agent_cwd

# 选择模型提供商
DEFAULT_MODEL_CONFIG=claude-router  # 或 "glm"

# 配置认证令牌
GLM_AUTH_TOKEN=your_glm_token_here
CLAUDE_ROUTER_AUTH_TOKEN=test # 不需要配置

# 配置服务端口
PORT=9090

# 其他配置...
```

> **Claude Router**:  指的是 [claude-code-router](https://github.com/musistudio/claude-code-router)，简称 ccr，可以将 Claude Agent SDK 的请求在本地中转到其他 LLM，比如: Claude Agent SDK --> ccr --> deepseek
>
> 使用 Claude Router 时，需每次启动程序运行：`eval "$(ccr activate)"`，具体参考[官方介绍](https://github.com/musistudio/claude-code-router/blob/main/README_zh.md)。

### 3. 启动服务

```bash
# 启动服务（带自动重载）
./run.sh start

# 停止服务
./run.sh stop

# 重启服务（默认命令）
./run.sh
./run.sh restart
```

服务启动后，默认运行在 9090 端口（可通过 `PORT` 环境变量配置）。

访问以下地址：
- API 根路径: http://localhost:9090
- API 文档: http://localhost:9090/docs
- 健康检查: http://localhost:9090/api/health

日志文件位于 `log/app.log`。

## 开发工具

### CLI 调试工具

提供了一个交互式终端，用于在不运行完整 API 服务器的情况下测试 Agent 查询：

```bash
source .venv/bin/activate
python cli.py
```

CLI 日志保存在 `log/cli.log`。

## 项目架构

### 核心组件

**API 层** (`api/`)
- `routers/agent.py` - 通用 `/api/query` 接口 (SSE streaming)
- `routers/plugins.py` - 插件管理 API (`/api/plugins/`)
- `dependencies.py` - 单例服务注入容器

**服务层** (`api/services/`)
- `AgentService` - 编排 Claude SDK 查询、Prompt 组装
- `SessionService` - 管理活跃 Agent 会话（支持中断）
- `ConfigService` - 动态模型供应商切换（线程安全）

**核心处理** (`api/core/`)
- `StreamProcessor` - 处理 Claude SDK 消息流，发送 SSE 事件

**插件系统** (`api/plugins/`)
- `manager.py` - 插件编排器（发现→加载→注册→启动）
- `channel.py` - Channel 插件抽象基类
- `config.py` - 插件配置服务（`plugins/config.json`）
- `session_mapper.py` - 通用会话映射器，供所有 Channel 插件复用

**内置插件** (`plugins/bundled/`)
- `yunzhijia/` - 云之家 Channel 插件（webhook 接收、消息发送、图片卡片）

**CLI** (`cli/`)
- `repl.py` - 带有 SSE 流式显示的交互式 REPL
- `command_handler.py` - 特殊命令 (/switch, /sessions, /quit)
- `stream_renderer.py` - 基于终端的 SSE 流渲染

### Skill 系统

Skills 是从 `agent_cwd/.claude/skills/` 加载的 [Agent Skills](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)。示例技能：

**customer-service** - 发票云客服 Agent
- 处理售前（产品能力）、售后（故障排除）、API 集成等问题
- 知识库位于 `agent_cwd/data/kb/`：
  - `产品与交付知识/` - 产品/交付文档（默认）
  - `营销知识库/` - 营销/销售材料
  - `API文档/` - API 文档
- 多产品消歧：当存在多个产品时，会阻断并询问用户

### Skill 与知识库关联

每个 Skill 通过 `agent_cwd/.claude/skills/{skill-name}/SKILL.md` 定义其能力和上下文。Skill 可以访问 `agent_cwd/data/kb/` 目录下的知识库文件，通过工具（如 Glob、Grep、Read）搜索和读取相关文档。

**示例：customer-service Skill**
- **Skill 定义**: `agent_cwd/.claude/skills/customer-service/SKILL.md` 包含了处理逻辑、产品识别规则、输出格式等
- **知识库路径**:
  - `agent_cwd/data/kb/产品与交付知识/` - 默认搜索路径，覆盖 80%+ 售后场景
  - `agent_cwd/data/kb/营销知识库/` - 当检测到售前信号（能力、功能、方案等）时搜索
  - `agent_cwd/data/kb/API文档/` - 当检测到 API 信号（接口、参数、集成等）时搜索
- **引用机制**: Skill 通过 Read 工具读取 KB 文件第 1 行的 markdown 链接并原样引用（`kb_link.py` 仅作可选辅助脚本）

## API 使用示例

### 通用查询接口

```bash
curl -X POST "http://localhost:9090/api/query" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "test-user",
    "prompt": "星空旗舰版如何配置开票人员？",
    "skill": "customer-service",
    "language": "中文"
  }'
```

该接口使用 Server-Sent Events (SSE) 进行流式响应。

### SSE 事件类型

- `heartbeat` - 连接状态
- `session_created` - 新会话 ID（第一条消息）
- `assistant_message` - 来自 Agent 的文本响应
- `tool_use` - 工具调用（信息性）
- `todos_update` - 来自 TodoWrite 的任务列表更新
- `ask_user_question` - Agent 请求用户输入
- `result` - 带有会话统计的最终结果
- `error` - 错误信息

### 中断会话

```bash
curl -X POST "http://localhost:9090/api/interrupt/{session_id}"
```

## 插件系统

Channel（如云之家）等外部集成通过插件方式管理，无需修改核心代码。

```bash
# 管理插件
python manage_plugins.py list              # 列出所有插件
python manage_plugins.py info yunzhijia    # 查看插件详情
python manage_plugins.py enable <id>       # 启用插件
python manage_plugins.py disable <id>      # 禁用插件
python manage_plugins.py install <path>    # 安装本地插件
python manage_plugins.py doctor            # 健康检查
```

插件配置集中在 `plugins/config.json`：

```json
{
  "enabled": ["yunzhijia"],
  "plugins": {
    "yunzhijia": {
      "session_timeout": 1800,
      "default_skill": "customer-service"
    }
  }
}
```

### 云之家插件

云之家插件（`plugins/bundled/yunzhijia/`）接收企业聊天消息并通过 webhook 响应：

1. **Receive**: `POST /yzj/chat?yzj_token=xxx`（立即返回 200 响应）
2. **Process**: 后台任务处理 Agent 查询
3. **Reply**: 通过云之家 webhook 发送 markdown/卡片消息

会话管理：映射云之家 `sessionId` → Agent `session_id`，默认 30 分钟不活跃超时（可配置）

## 环境变量说明

关键环境变量配置（在 `.env` 中）：

```bash
# Agent 工作目录
AGENT_CWD=agent_cwd  # Agent 工作目录（Skills、知识库、租户数据）

# 模型提供商选择
DEFAULT_MODEL_CONFIG=claude-router  # 或 "glm"

# 模型提供商认证令牌
GLM_AUTH_TOKEN=xxx
CLAUDE_ROUTER_AUTH_TOKEN=xxx
CLAUDE_ROUTER_PROXY=http://127.0.0.1:7890  # 可选

# 服务配置
PORT=9090
LOG_LEVEL=INFO

# 插件额外搜索路径（可选，冒号分隔）
# PLUGIN_PATHS=/path/to/plugins1:/path/to/plugins2
```

## 开发指南

### 并发与线程安全

- `ConfigService` 使用 `threading.Lock` 进行原子配置切换
- `SessionService` 使用 `asyncio.Lock` 实现异步安全的会话注册
- 通过 FastAPI 的异步工作池处理多个并发请求

### 重要路径

- `AGENTS_ROOT` = 项目根目录
- `AGENT_CWD` = Agent 工作目录（默认 `agent_cwd/`，通过环境变量 `AGENT_CWD` 配置）
  - `agent_cwd/.claude/skills/` - Skills 定义
  - `agent_cwd/data/kb/` - 知识库文件
  - `agent_cwd/data/tenants/` - 租户数据
- `plugins/` - 插件目录
  - `plugins/bundled/` - 内置插件
  - `plugins/installed/` - 用户安装的插件
  - `plugins/config.json` - 插件配置（启用列表 + 各插件参数）
- 日志位于 `log/app.log`（重启时轮转）
- CLI 日志位于 `log/cli.log`
- 测试结果位于 `tests/results/`

## 更多文档

详细的开发文档和架构说明，请参阅 [CLAUDE.md](CLAUDE.md)。

## 许可证

[添加你的许可证信息]

## 贡献

[添加贡献指南]
