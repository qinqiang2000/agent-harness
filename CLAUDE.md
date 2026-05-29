# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

基于 FastAPI + Claude Agent SDK 的 AI Agent 服务。支持 Skill 扩展、插件化 Channel 集成、多租户、动态模型供应商切换（claude / claude-router / glm / litellm / kimi / deepseek 等）。

## 开发命令

```bash
# 服务管理
./run.sh start|stop|restart      # 启动/停止/重启服务（默认端口 9090）
./run.sh                         # 默认重启

# 交互式 CLI 调试（不启动 HTTP 服务器）
source .venv/bin/activate && python cli.py

# 单元测试
source .venv/bin/activate
pytest tests/audit/              # 运行 audit 插件测试
pytest tests/test_faq_db.py      # 运行单个测试文件

# 批量集成测试（需服务运行中）
python tests/batch_test.py tests/dataset/test_set_1.md
python tests/batch_test.py -p "问题内容" --default-product "星瀚旗舰版"

# 插件管理
python manage_plugins.py list|info|enable|disable|install|doctor
```

## 关键路径

- `AGENT_CWD`（默认 `agent_cwd/`，通过环境变量配置）— Agent 工作目录
  - `.claude/skills/` — Skill 定义（每个 skill 一个子目录，含 `SKILL.md`）
  - `data/kb/` — 知识库文件（Agent 通过 Read/Grep/Glob 工具访问）
  - `data/tenants/` — 租户数据
- `plugins/bundled/` — 内置插件（yunzhijia、zhichi、audit、wecom、wecom_group、linear 等）
- `plugins/installed/` — 用户安装的插件
- `plugins/config.json` — 插件启用列表与各插件参数
- `api/constants.py` — 所有路径常量（`AGENTS_ROOT`、`AGENT_CWD`、`DATA_DIR` 等）
- `log/app.log` — 服务日志（重启时轮转），`log/cli.log` — CLI 日志
- `tests/results/` — 批量测试结果
- `agent_cwd/.claude/commands/` — Agent 可调用的 command（`product-workflow.md`、`validate-upstream.md`）
- `agent_cwd/.claude/skills/` — 当前已有 skill：`01-requirement-analysis`、`02-ontology-context`、`03-ontology-update`、`04-prototype-design`、`05-generate-prd`、`customer-service`、`financial-audit`、`issue-diagnosis`、`issue-diagnosis-external`、`issue-diagnosis-workspace`、`operational-analytics`、`plugin-manager`

## 架构要点

### 请求链路

```
POST /api/query
  → api/routers/agent.py        # 参数校验、SSE 响应包装
  → AgentService.process_query  # Prompt 组装、SDK 配置、视觉降级
  → ClaudeSDKClient             # claude_agent_sdk（子进程 Claude CLI）
  → StreamProcessor             # 消息流解析，发出 SSE 事件
```

SSE 事件类型：`heartbeat` → `session_created` → `assistant_message` / `tool_use` / `todos_update` / `ask_user_question` / `transfer_human` → `result` / `error`

转人工信号：Agent 在 result 文本中输出 `[TRANSFER:组名]` 触发 `transfer_human` 事件。

### 会话缓存（sdk_pool.py）

`SDKSessionCache` 按 `session_id` 复用 `ClaudeSDKClient` 子进程，TTL 1 小时，后台 reaper 每 60 秒回收空闲连接。续接会话时命中缓存可消除冷启动开销；连接不健康时自动丢弃重建。

### 模型供应商切换

`ConfigService`（线程安全）通过切换环境变量（`ANTHROPIC_BASE_URL`、`ANTHROPIC_AUTH_TOKEN` 等）实现运行时模型切换。预定义配置在 `api/services/config_service.py` 的 `PREDEFINED_CONFIGS` 中，支持：`claude`、`claude-router`、`glm`、`kimi`、`litellm`、`minimax`、`tencentmaas`、`deepseek`。通过 `DEFAULT_MODEL_CONFIG` 环境变量选择默认供应商。

不支持视觉的模型（`supports_vision=False`）可配置 `vision_helper` 指向另一个 config，由 `VisionService` 调用 helper 识图后将描述注入 prompt。

### 插件系统

`PluginManager`（`api/plugins/manager.py`）协调 Discovery → Load → Register → Lifecycle。插件实现 `ChannelPlugin` 抽象基类（`api/plugins/channel.py`），通过 `create_router()` 注册自己的 FastAPI 路由，通过 `on_start/on_stop` 管理生命周期。`session_mapper.py` 提供通用的外部会话 ID → Agent session_id 映射，供所有 Channel 插件复用。

### 依赖注入

`api/dependencies.py` 以全局单例模式管理 `ConfigService`、`SessionService`、`AgentService`、`PluginManager`，通过 `get_*()` 函数获取。测试时可调用 `reset_services()` 重置。

### 安全配置

`AgentService.__init__` 在启动时写入 `.custom-settings.json`，通过 `permissions.deny` 禁止 Agent 访问 `.env`、密钥文件、`settings.json`，以及 `WebFetch`、`WebSearch`、`ScheduleWakeup` 等工具。额外的 allow/deny 规则从 `agent_cwd/.claude/settings.json` 的 `permissions` 字段加载。

### Linear Agent 插件（plugins/bundled/linear/）

Linear Agent 集成，接收 Linear AgentSession Webhook，通过 Python 编排器逐步调用五步 skill 生成 PRD，支持父子 Issue 自动创建和 PRD 回填。

**路由：**
- `POST /linear/webhook` — 接收 AgentSession 事件（nginx: `/prd-agent/webhook`）
- `GET /linear/oauth/install` — OAuth 安装入口
- `GET /linear/oauth/callback` — OAuth 回调（nginx: `/prd-agent/oauth/callback`）
- `GET /linear/stats` — 安装状态查询

**关键文件：**
- `token_store.py` — SQLite OAuth token 存储（`data/linear/linear_tokens.db`）
- `linear_client.py` — Linear GraphQL API 封装
- `handler.py` — LinearSessionHandler，处理 created/prompted/stop 事件
- `workflow_orchestrator.py` — Python 编排器，逐步调用 ①②③④⑤ skill，每步完成后更新 Linear plan
- `feature_list_parser.py` — 特性清单 Markdown 解析
- `issue_creator.py` — 阶段 A：父子 Issue 骨架创建
- `prd_backfiller.py` — 阶段 B：PRD 回填

**PRD 产物目录：** `data/linear/prd/{issue_identifier}/`
**Git 同步仓库：** `https://github.com/invagent/develop-workflow-artifacts`（master 分支，通过 `LINEAR_GIT_REPO_URL`/`LINEAR_GIT_BRANCH`/`LINEAR_GIT_LOCAL_PATH` 环境变量配置）
**Git 目录结构：** 服务器 `data/linear/prd/{issue_id}/` → Git `{issue_id}/PRD/`（所有产物放在 PRD 子目录下）

**plugin.json 必须包含 `type` 和 `entry_point` 字段**，否则插件加载失败。

**Linear Webhook payload 结构（AgentSessionEvent）：**
- session_id → `agentSession.id`（不是 `data.id`）
- issueId → `agentSession.issueId`
- 用户输入 → `agentActivity.content.body`
- stop 信号 → `agentActivity.signal == "stop"`
- `created` 事件包含 `promptContext` 字段（XML 格式的 issue 信息）

**Linear handler 调用 AgentService 时不能传 session_id**，否则会被当成 resume 旧会话导致 `No conversation found` 错误。

**Linear Agent 已验证的行为：**
- 小需求（Fast Lane Bug·规则类）：①→②(lite)→⑤，约 8-10 分钟完成，Python 编排器逐步驱动
- 大需求（Deep Lane 新增业务能力）：①→②→③→④→⑤，约 30+ 分钟，Step 5 多份 PRD 时可能触发推理网关 504 超时
- 小需求 PRD 回填：PRD 内容自动追加到原 Issue 描述末尾，用 `---PRD文档---` 包裹，已有则替换
- 阶段 A/B（Issue 骨架创建 + PRD 回填到子 Issue）：仅大需求且特性清单 `stage=confirmed` 时触发，目前大需求因 504 超时未完整验证

**WorkflowOrchestrator 路由决策矩阵（workflow_orchestrator.py）：**

| lane | category | 调用链 |
|------|----------|--------|
| fast | rule | ①→②lite→③cond→⑤ |
| fast | ux/tech/其他 | ①→⑤lite |
| standard | new/extend | ①→②→③→⑤（大需求检测后拆子 Issue）|
| standard | config | ①→②→⑤ |
| standard | rule | ①→②lite→③cond→⑤ |
| standard | ux/tech/perf | ①→⑤lite |
| standard | exp | ①→④→⑤lite |
| deep | new/extend | ①→②→③→④→⑤（大需求，拆子 Issue）|
| deep | config | ①→②→③→⑤ |
| deep | rule | ①→②lite→③cond→⑤ |
| deep | ux/tech/perf | ①→⑤lite |
| deep | exp | ①→④→⑤lite |

- `_is_large_req()`：route 含完整 `②` 且 lane=deep，或 lane=standard+category in new/extend → 触发大需求拆子 Issue
- `_need_step3()`：lite 模式下 bug-ontology-result=PARTIAL/MISS 执行；完整模式下 exit_status=DONE_WITH_GAPS 执行
- 每步通过 `_invoke_skill` 独立调用 AgentService（不复用 session），prompt 前注入强制命名约束
- `on_step_start/on_step_done` 回调实时更新 Linear plan 进度
- ③ NEEDS_HUMAN 时通过 `wait_for_human` 暂停，等待 `handle_prompted` 的 Future resolve
- 子 Issue 流程：`_copy_parent_step2_artifacts` 将父 Issue 的需求分析报告、特性清单、对应特性本体映射报告复制到子 Issue 目录，供 ③④⑤ 使用
- `agent_cwd/.claude/settings.json` 必须包含 `Write/Edit(**/data/linear/prd/**)` 权限，否则 skill 写文件被拦截

**Linear Agent 关键 bug 修复记录：**
- `agent_cwd/.claude/hooks/restrict-edit-write.py` 白名单需包含 `/data/linear/prd/`，否则 subagent 写文件被拦截
- `agent_cwd/.claude/settings.json` allow 列表需包含 `Write/Edit(**/data/linear/prd/**)` — settings.json 权限先于 hook 执行，不加则弹权限提示导致文件写不进去
- `_sync_to_git` clone 失败后需 return，否则后续 git 命令在空目录执行报 `not a git repository`
- git clone 后需配置 `user.email` 和 `user.name`，否则 commit 报 `Author identity unknown`
- `_trigger_phase2` 完成后需再次调用 `update_agent_session` 将 plan 全部置为 `completed`，否则 Linear 里一直转圈
- `ALLOWED_MCP_TOOLS` 环境变量需在 `.env` 中启用，包含 `mcp__ontology__get_object_registry,mcp__ontology__get_object_detail`，否则 Agent 降级用 curl 调用 MCP 导致 Step 2 耗时 25+ 分钟

## 注意事项

- `claude_agent_sdk` 不一定可用（如 CLI 上下文）。CLI 工具链用到的模块不能在顶层 import 它，需用 lazy import 或 `TYPE_CHECKING` guard。
- `app.py` 顶部有 SDK patch，为 DeepSeek 等第三方模型补全缺失的 `signature` 字段，修改 message_parser 时注意兼容。
- `ALLOWED_MCP_TOOLS` 环境变量可追加 MCP 工具到 Agent 白名单（逗号分隔）。
- Claude Router 指 [claude-code-router](https://github.com/musistudio/claude-code-router)（ccr），使用前需 `eval "$(ccr activate)"`。
- `/open-api/` 前缀的路由使用统一的 `{errcode, description, data}` 错误格式，其他路由直接抛 HTTPException。
