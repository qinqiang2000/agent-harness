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

## Docker 部署与维护

### 首次部署

```bash
# 1. 克隆代码
git clone <repo-url> /opt/agent-harness
cd /opt/agent-harness

# 2. 准备配置
cp .env.example .env
# 编辑 .env，至少配置以下项：
#   - DEFAULT_MODEL_CONFIG（模型供应商）
#   - 对应供应商的 API Key
#   - PORT=9123（对外端口）
#   - SERVICE_BASE_URL=http://<公网IP>:9123
#   - YZJ_ALERT_WEBHOOK_TOKEN（云之家告警推送 token）

# 3. 放置 SSH 密钥
# 将密钥文件放到 ssh-keys/tencent/ 和 ssh-keys/aws/ 目录
# 确保权限为 600
chmod 600 ssh-keys/tencent/*.pem ssh-keys/aws/*.pem

# 4. 构建并启动
docker compose up -d --build
```

### 常用运维命令

```bash
# 查看日志
docker logs -f agent-harness --tail 100

# 重启服务
docker compose restart

# 更新代码后重新部署
git pull
docker compose up -d --build

# 进入容器调试
docker exec -it agent-harness bash

# 查看服务状态
docker compose ps
```

### 端口说明

| 配置 | 说明 |
|------|------|
| 容器内部端口 | 9123（Dockerfile 固定） |
| 宿主机映射端口 | 由 `.env` 中 `PORT` 决定，默认 9123 |

如需改端口，修改 `.env` 中的 `PORT`，同时更新 Dockerfile 和 docker-compose.yml。

### 数据持久化

以下目录通过 volume 挂载，容器重建不会丢失：

| 宿主机路径 | 容器路径 | 用途 |
|-----------|---------|------|
| `./ssh-keys/` | `/opt/agent-harness/agent_cwd/ssh-keys` | SSH 密钥（只读） |
| `./agent_cwd/data/` | `/opt/agent-harness/agent_cwd/data` | 诊断报告、案例库 |
| `./.env` | `/opt/agent-harness/.env` | 环境配置（只读） |

### 环境变量速查

| 变量 | 必填 | 说明 | 示例 |
|------|------|------|------|
| `DEFAULT_MODEL_CONFIG` | ✅ | 模型供应商 | `claude` / `litellm` / `glm` |
| `PORT` | ✅ | 对外服务端口 | `9123` |
| `SERVICE_BASE_URL` | ✅ | 公网可访问地址（完整 URL） | `http://42.193.101.189:9123` |
| `YZJ_ALERT_WEBHOOK_TOKEN` | ✅ | 云之家告警群机器人 token | `e74c5794...` |
| `CLAUDE_CODE_OAUTH_TOKEN` | 按需 | Claude 官方 API token | `sk-ant-...` |
| `LITELLM_BASE_URL` | 按需 | LiteLLM 代理地址 | `http://host:4000` |
| `LITELLM_API_KEY` | 按需 | LiteLLM API Key | - |
| `GLM_AUTH_TOKEN` | 按需 | 智谱清言 token | - |
| `CLAUDE_PROXY` | 按需 | Claude API 代理 | `http://127.0.0.1:7890` |

### 故障排查

```bash
# 服务无法启动
docker logs agent-harness 2>&1 | head -50

# SSH 连接失败
docker exec agent-harness ls -la /opt/agent-harness/agent_cwd/ssh-keys/tencent/
docker exec agent-harness ssh -T -i /opt/agent-harness/agent_cwd/ssh-keys/tencent/cosmic_test.pem -o ConnectTimeout=5 root@172.31.16.29 echo ok

# 云之家推送失败
docker exec agent-harness printenv | grep YZJ_ALERT_WEBHOOK_TOKEN

# 报告链接 404
docker exec agent-harness ls /opt/agent-harness/agent_cwd/data/diagnosis-reports/
```

- `claude_agent_sdk` 不一定可用（如 CLI 上下文）。CLI 工具链用到的模块不能在顶层 import 它，需用 lazy import 或 `TYPE_CHECKING` guard
- `.custom-settings.json` 由 `AgentService` 初始化时写入，包含安全配置（拒绝读取 `.env`、密钥文件等）
- 环境变量参考 `.env.example`，模型供应商通过 `DEFAULT_MODEL_CONFIG` 切换
- Claude Router 指 [claude-code-router](https://github.com/musistudio/claude-code-router)（ccr），使用前需 `eval "$(ccr activate)"`
