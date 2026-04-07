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
- `plugins/bundled/` — 内置插件（yunzhijia、zhichi、audit）
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

## 注意事项

- `claude_agent_sdk` 不一定可用（如 CLI 上下文）。CLI 工具链用到的模块不能在顶层 import 它，需用 lazy import 或 `TYPE_CHECKING` guard
- `.custom-settings.json` 由 `AgentService` 初始化时写入，包含安全配置（拒绝读取 `.env`、密钥文件等）
- 环境变量参考 `.env.example`，模型供应商通过 `DEFAULT_MODEL_CONFIG` 切换
- Claude Router 指 [claude-code-router](https://github.com/musistudio/claude-code-router)（ccr），使用前需 `eval "$(ccr activate)"`
