# CLAUDE.md

基于 FastAPI + Claude Agent SDK 的 AI Agent 服务。支持 Skill 扩展、插件化 Channel 集成、多租户、动态模型供应商切换（claude / claude-router / glm / litellm）。

## 开发命令

```bash
./run.sh start|stop              # 启动/停止服务
./run.sh                         # 默认重启
source .venv/bin/activate && python cli.py  # 交互式 CLI 调试

# 批量测试
python tests/batch_test.py tests/dataset/test_set_1.md
python tests/batch_test.py -p "问题内容" --default-product "星瀚旗舰版"

# 插件管理
python manage_plugins.py list|info|enable|disable|install|doctor
```

## 关键路径

- `AGENT_CWD`（默认 `agent_cwd/`）— Agent 工作目录，Skills 和知识库在此目录下
  - `.claude/skills/` — Skill 定义（`SKILL.md`）
  - `data/kb/` — 知识库文件
  - `data/tenants/` — 租户数据
- `plugins/bundled/` — 内置插件（yunzhijia、zhichi、audit、linear）
- `plugins/installed/` — 用户安装的插件
- `plugins/config.json` — 插件启用列表与配置
- `log/` — 日志目录
- `tests/results/` — 测试结果
- 常量定义见 `api/constants.py`

## 架构要点

请求入口 `POST /api/query` → `api/routers/agent.py` → `AgentService` → Claude SDK → `StreamProcessor` 输出 SSE。

SSE 事件：`heartbeat`, `session_created`, `assistant_message`, `todos_update`, `ask_user_question`, `transfer_human`, `result`, `error`

Agent allowed_tools 在 `api/services/agent_service.py` 中配置，包含基础工具（Skill、Read、Grep 等）和 MCP 工具（elastic、gitlab）。

插件系统（`api/plugins/`）：`PluginManager` 协调 Discovery → Load → Register → Lifecycle。插件通过 `ChannelPlugin` 基类实现，详见 `channel.py`。

## code-fix skill

`agent_cwd/.claude/skills/code-fix/` — 代码自动修复 skill，与 issue-diagnosis-billing 联动。

**触发流程**：
1. issue-diagnosis-billing 输出结论后，若 `【结论类型】CODE_BUG`，skill 内部直接调用 `Skill("code-fix", ...)`
2. Linear handler（`plugins/bundled/linear/handler.py`）收到诊断结论后，检测到 `【结论类型】CODE_BUG` 且不含"修复完成"时，由 handler 层兜底触发

**结论类型枚举**（issue-diagnosis-billing 输出）：
- `CODE_BUG`：代码级 bug，自动触发 code-fix
- `CONFIG_CHANGE`：配置变更，等用户确认
- `REQUIREMENT`：需求/变更任务，等用户确认
- `BUSINESS_FAQ`：业务疑问，等用户确认
- `EXTERNAL_ISSUE`：外部系统问题，等用户确认
- `NEED_MORE_INFO`：信息不足，反问用户

**目录隔离**：code-fix 使用 `/tmp/gitlab/fix/{repoName}_{年月日时分秒}`，与 issue-diagnosis 的 `/tmp/gitlab/src/` 完全隔离，避免并发冲突。

**分支复用（SQLite 持久化）**：code-fix 每次执行前查询 `data/code_fix_sessions.db`，同一 issue 二次修改时复用原分支。脚本：`agent_cwd/.claude/skills/code-fix/scripts/session_store.py`，支持 `CODE_FIX_DATA_DIR` 或 `AGENT_DATA_DIR` 环境变量覆盖路径。

**权限配置**：`agent_service.py` 中 `permission_mode="acceptEdits"`，`add_dirs=["/tmp/gitlab"]`，允许修改 `/tmp/gitlab/` 下文件。

**服务仓库映射**：`agent_cwd/.claude/skills/code-fix/references/service-repo-map.md` 和 `gitlab-lookup.md` 与 `issue-diagnosis-billing/references/` 下同名文件内容保持一致，两份独立维护，更新时需同步修改两处。

## CICD + autotest 自动化链路

code-fix Step 8（push 成功后执行）统一负责 CICD + autotest，两个入口（Linear / Chat UI）行为一致：

- 脚本：`agent_cwd/.claude/skills/code-fix/scripts/run_cicd.py`
- **必须用 `nohup` 后台运行**，否则会触发 API 流超时（600s 限制）
- 脚本自己读完临时文件后删除，SKILL.md 里**不能** `rm -f $TMP_FIX`（竞争条件）
- 流程：解析「仓库：xxx / 分支：xxx」→ 并行触发所有服务 cicd-pipeline → 全成功后触发 at-automated-test
- 日志：`/tmp/cicd_run_<时间戳>.log`
- 依赖 `requests` 库，服务器需确认已安装

## issue-diagnosis-billing skill

`agent_cwd/.claude/skills/issue-diagnosis-billing/` — 标准版产品统一诊断入口，覆盖故障/业务疑问/需求变更三类场景。

**执行路径**：
- 路径 A：有 traceId 或报错关键词 → 查 ELK 日志 → 源码联合分析
- 路径 B+：有业务标识符（BX-/IWO/20位发票号）→ 先查 ELK，查不到降级路径 B
- 路径 B：纯业务疑问 → 知识库检索 + 源码分析
- 路径 C：需求/变更任务 → 知识库项目地图确定服务 → 源码定位 → 输出变更方案

**知识库**：skill 只读 `.claude/skills/issue-diagnosis-billing/references/` 下的固定文件，`data/kb/` 下文件**不会被自动检索**。知识库按业务拆分为三个文件：
- `knowledge-base-input.md` — 收票业务（含 fpzs-pc/portal-web 前端排查指引）
- `knowledge-base-image.md` — 影像业务（含 image-system/image-asst 前端排查指引及 URL 路由规则）
- `knowledge-base-output.md` — 开票/销项业务（占位，待补充）

**前端影响面检查**：输出 CODE_BUG/REQUIREMENT 结论时，必须检查被改接口是否被前端调用，结论中包含【前端影响面】字段。前端项目路径：`{BILLING_CODE_BASE_DIR}/input-project/standard/frontend/`

**源码分析（子 agent 模式）**：Step 4.2 中，跨 2+ 文件或 3+ 源码文件时强制派发子 agent 专职读码，只返回摘要，主 agent 保持 context 轻量。

**max_turns**：`agent_service.py` 中 `build_default_options` 和 metadata 覆盖路径均设为 80（原为 40），避免复杂诊断超限中断。

## Token 成本统计与归因

按 issue 统计 token 消耗与成本，回答"每个 issue 花了多少、被什么内容占用"。

**数据链路**：`StreamProcessor`（采集）→ `usage_sink` 回调 → `api/services/token_usage_store.py`（SQLite `data/token_usage.db`）

**三张表**：
- `session_usage` — 一行 = 一次 `process_query`，永久保留
- `tool_volume` — 一行 = 一次工具返回（含字符数、轮次），归因用，默认保留 14 天
- `channel_issue_map` / `issue_sessions` — issue ↔ 会话绑定

**issue 归因**：一个 Linear issue 会产生多个独立 session（诊断 / code-fix / 追问），靠 `QueryRequest.metadata` 里的 `issue_key`（Linear identifier，如 CNPRD-1276）聚合。`handler.py` 在诊断时调 `bind_channel_issue` 绑定 AgentSession → issue，后两处调 `lookup_channel_issue` 反查。

**归因算法**（`attribute_buckets`）：
- **SDK 在流式模式下不填充 `AssistantMessage.usage`（实测恒为 0）**，拿不到逐轮 token，因此不能用相邻轮次 input 增量归因
- 改用工具返回体积按轮次加权：第 k 轮产生的内容会被其后每轮重放计费，权重 = 估算 token × (总轮数 − k)
- 各桶按权重分摊 `ResultMessage` 的真实 input 总量，残差归"系统底座"
- **占比是估算的，但各桶之和恒等于真实计费 token**
- 盲区：子 agent 内部消耗计入总量但无法细分

**成本口径**：`total_cost_usd` 走 litellm 代理时按上游模型定价，**实测与本地单价表偏差 +67%**，故以 `TOKEN_PRICE_*` 自算为准，日报中并列展示两个数供对照。

**日报**：`scripts/token_report.py`，每天 `TOKEN_REPORT_HOUR:MINUTE`（默认 09:10）走云之家 **notify 私聊**推送（复用 `RETROSPECTIVE_NOTIFY_URL/NAME`），与 `daily_report.py` 的群机器人 webhook 是两条独立通道。

所有云之家推送（token 日报 + 复盘通知）统一带前缀 `NOTIFY_MSG_PREFIX`（默认 `【CodingAgent项目】`，定义在 `api/constants.py`），便于在众多通知中辨识来源。

```bash
python scripts/token_report.py --date 20260908 --dry-run   # 预览日报
python scripts/token_report.py --issue CNPRD-1276          # 单 issue 明细
```

**接口**：`GET /api/report/tokens?date=`、`GET /api/report/tokens/issue/{issue_key}`、`POST /api/report/tokens/send`

## issue-retrospective skill（Self-Improving Agent）

`agent_cwd/.claude/skills/issue-retrospective/` — 每日复盘 skill，分析诊断 session 中的 Agent 错误，自动生成知识库改进草稿。

**触发方式**：APScheduler 每天凌晨 2:00 自动触发（`api/services/retrospective_service.py`），不对用户暴露。

**分析逻辑**：
- 读取前一天归档日志（优先 `log/interactions.log.YYYY-MM-DD`，不存在时回退 `interactions.log` 按日期过滤）
- 识别纠正信号（session 维度）：用户问题含明确纠正关键词、回复"2 未解决"、或第一条回答含【结论类型】后用户继续追问
- 纯多轮成功 session 不触发，必须有纠正信号
- LLM 读取项目 CLAUDE.md 和各 SKILL.md 理解架构，结合完整对话记录分析根因，生成知识条目草稿
- LLM 先判断 needs_review，成功完成的 session 返回 false 跳过草稿生成

**草稿目录**：`agent_cwd/.claude/skills/issue-retrospective/pending/`，文件名格式 `{YYYYMMDD}_correction_{sessionId}.md`

**运维流程**：
- 每天早上看云之家通知 → 打开 `pending/` 下草稿 → 确认 AI 分析内容
- 采纳：把知识条目复制到对应 `references/` 文件，再 `mv` 草稿到 `confirmed/`
- 不采纳：直接 `rm` 草稿文件

**环境变量**：
- `RETROSPECTIVE_NOTIFY_URL` — 云之家 notify 接口完整 URL（含 access_token）
- `RETROSPECTIVE_NOTIFY_NAME` — 通知接收人姓名
- `RETROSPECTIVE_HOUR/MINUTE` — 触发时间（默认 02:00）
- `RETROSPECTIVE_TEST_INTERVAL_MINUTES` — 本地验证用，设为 1 改为每分钟触发


- `claude_agent_sdk` 不一定可用（如 CLI 上下文）。CLI 工具链用到的模块不能在顶层 import 它，需用 lazy import 或 `TYPE_CHECKING` guard
- `.custom-settings.json` 由 `AgentService` 初始化时写入，包含安全配置（拒绝读取 `.env`、密钥文件等）
- 环境变量参考 `.env.example`，模型供应商通过 `DEFAULT_MODEL_CONFIG` 切换
- 模型名的 `[1m]` 后缀（如 `claude-agy-sonnet[1m]`）是 Claude Code 客户端约定，**不是** provider 侧的模型名。Agent SDK 会剥离后缀，实际发送 base model 名 + header `anthropic-beta: ...,context-1m-2025-08-07,...`。因此用裸 curl 打 provider 的 `/v1/messages` 带 `[1m]` 会报模型不存在/无权限，属正常现象，必须走 agent 接口验证
- 本地与生产 `.env` 各自独立维护，改配置时两端分别改、分别重启验证，禁止用本地 `.env` 覆盖生产（rsync 已 `--exclude='.env'`）
- Claude Router 指 [claude-code-router](https://github.com/musistudio/claude-code-router)（ccr），使用前需 `eval "$(ccr activate)"`
- 服务器部署在 `/data/panda_li/agent-harness`，端口 9125，详见 CLAUDE.local.md
- 服务器使用 Python 3.12，`claude-agent-sdk` 从 `/root/jinfan/linear-cc/agent-harness/.venv` 复制安装
- 服务器 MCP elastic URL：内网地址，详见 CLAUDE.local.md
- `run.sh` Linux 环境不带 `--reload`，macOS 保留热重载
