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
PORT=9123

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

服务启动后，默认运行在 9123 端口（可通过 `PORT` 环境变量配置）。

访问以下地址：
- API 根路径: http://localhost:9123
- API 文档: http://localhost:9123/docs
- 健康检查: http://localhost:9123/api/health

日志文件位于 `log/app.log`。

## Docker 部署与维护

### 构建镜像

```bash
# 首次构建（或代码/依赖变更后重新构建）
docker compose build

# 强制不使用缓存重新构建
docker compose build --no-cache
```

### 启动与停止

```bash
# 后台启动
docker compose up -d

# 查看运行状态
docker compose ps

# 停止服务（保留容器）
docker compose stop

# 停止并删除容器
docker compose down
```

### 查看日志

```bash
# 实时跟踪日志
docker compose logs -f

# 只看最近 100 行
docker compose logs --tail=100

# 查看容器内日志文件（应用自身写入的 log/app.log）
docker compose exec agent tail -f log/app.log
```

### 更新部署

代码有变更时的标准流程：

```bash
git pull
docker compose build
docker compose up -d
```

### 进入容器调试

```bash
# 进入容器 shell
docker compose exec agent bash

# 在容器内运行 CLI 调试工具
docker compose exec agent python cli.py
```

### 数据持久化说明

`docker-compose.yml` 通过 volume 挂载以下目录，容器重建后数据不丢失：

| 宿主机路径 | 容器内路径 | 说明 |
|-----------|-----------|------|
| `./agent_cwd/ssh-keys` | `/opt/agent-harness/agent_cwd/ssh-keys` | SSH 密钥（只读） |
| `./.env` | `/opt/agent-harness/.env` | 环境变量（只读） |
| `./.servers` | `/opt/agent-harness/.servers` | 服务器映射配置（只读） |
| `./agent_cwd/data` | `/opt/agent-harness/agent_cwd/data` | 诊断案例等运行时数据 |
| `./log` | `/opt/agent-harness/log` | 应用日志（持久化，容器重建后保留） |

> **注意**：`agent_cwd/data` 和 `.servers` 在宿主机上实时同步，无需重启容器即可更新；`log/` 持久化到宿主机后可用 `tail -f log/app.log` 实时跟踪。

### 端口配置

容器内固定监听 `9123`，宿主机端口通过 `.env` 中的 `PORT` 变量控制（默认也是 `9123`）：

```bash
# .env 中修改宿主机端口
PORT=8080
```

---

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


## 运维告警诊断（ops-diagnosis）

接收 Prometheus Alertmanager / 自定义脚本 / 腾讯云等多源告警，自动 SSH 采集数据、定位根因，推送结论到云之家群。

### 接入端点
标准告警会走ai诊断，文本告警会直接转发到群。

| 端点 | 用途 | Body 格式 |
|------|------|----------|
| `POST /api/alert-webhook` | Alertmanager 标准告警（结构化） | JSON（`alerts` 字段） |
| `POST /api/alert-text` | 文本告警（脚本告警、群机器人转发等） | `text/plain` 或 `{"text": "..."}` |

**Alertmanager 示例：**

```bash
curl -X POST http://host:9123/api/alert-webhook \
  -H "Content-Type: application/json" \
  -d '{
    "alerts": [{
      "status": "firing",
      "labels": {"alertname": "CPU使用率过高", "instance": "172.31.36.31:9100"},
      "startsAt": "2026-05-06T14:30:00.000Z"
    }]
  }'
```

**文本告警示例：**
```bash
curl -X POST http://host:9123/api/alert-text \
  -H "Content-Type: text/plain" \
  --data "666: 05-19 11:20 【✅ 恢复】云数据库 CPU 76% 已恢复"
```

### `/api/alert-text` 接入说明

该端点是**被动接口**，不会自动触发，需要在告警源侧配置 webhook 指向它。所有发到这个端点的文本告警都会原文转发到云之家群（恢复和非恢复均转发）。

**适用场景：**

| 告警源 | 接入方式 |
|--------|---------|
| 自定义 shell 监控脚本 | 脚本内 `curl -X POST http://host:9123/api/alert-text --data "告警内容"` |
| 腾讯云告警回调 | 告警策略 → 回调 URL 填 `http://host:9123/api/alert-text` |
| 云之家机器人转发 | 群机器人收到告警 → POST 到该端点 |
| Grafana Alerting | Contact Point 配置 webhook URL 指向该端点 |

> **注意**：Prometheus Alertmanager 有标准 JSON 格式（`alerts` 字段），应走 `/api/alert-webhook`，不要发到 `/api/alert-text`。

### 恢复告警直接转发（不走 LLM）

文本告警若命中恢复关键词（`✅ / 恢复 / 已解决 / resolved / RECOVERY`），直接将原文 POST 到 `$YZJ_ALERT_WEBHOOK`，**不调用 LLM 诊断、不消耗 token**。返回示例：

```json
{"msg": "ok", "action": "forwarded", "reason": "recovery alert (no diagnosis)"}
```

### 告警去重与限流

防止短时间内大量重复告警把 agent 打爆，内置三层防护：

| 层级 | 行为 | 配置 |
|------|------|------|
| **In-flight 锁** | 同一 `(alert_type, ip)` 已有诊断在跑 → 后续相同告警直接跳过并计数 | 自动 |
| **冷却期** | 诊断完成后 N 秒内不再触发同 key 诊断，期间跳过的告警继续累计 | `ALERT_COOLDOWN_SECONDS`（默认 1800 秒） |
| **全局并发** | 最多同时执行 N 个诊断任务，超出排队 | `ALERT_MAX_CONCURRENT`（默认 5） |

**完整时序示例**：100 条同 `(alert_type, ip)` 告警在 30 分钟内涌入：

1. 第 1 条 → 触发诊断（耗时约 10 分钟）
2. 第 2~100 条 → 命中 in-flight 或 cooldown，**跳过并累加计数**
3. 诊断完成 → 立即推送诊断结论到云之家
4. 冷却期结束（诊断完成后 30 分钟）→ 推送一条**频次汇总**：

```
📊 【告警频次汇总】
磁盘IO利用率高 - 172.31.16.40
过去 30 分钟内重复触发 99 次
首次: 11:20:34  末次: 11:48:12
（已自动诊断 1 次，详情见之前推送）
```

这样既不会刷屏，又能让运维知道告警频次是否异常。Webhook 调用方实时响应：

```json
{
  "msg": "ok",
  "triggered": 1,
  "skipped": 99,
  "skipped_details": [...]
}
```

### 告警类型与状态展示规则

不同告警类型在云之家推送的"状态行"展示对应的核心指标，详见 `agent_cwd/.claude/skills/ops-diagnosis/SKILL.md`：

| alert_type | 状态行内容 |
|-----------|-----------|
| CPU | 异常进程 -> CPU 使用率% |
| Memory | 异常进程/容器 -> 内存使用 |
| Disk（空间） | 挂载点 -> 使用率% (已用/总量) |
| **IO（读写速度）** | 设备 -> w:MB/s, r:MB/s, %util；定位到具体写入文件 |
| 容器 OOM | 容器名 -> OOMKilled 次数 + 最近时间 |
| 服务响应慢 | 服务名 -> P99 延迟 + QPS |

### SSH 服务器配置

`.servers`（项目根目录，和 `.env` 同级，`.gitignore` 已忽略）记录所有目标服务器的 SSH 信息。

**格式**（一行一台，`|` 分隔，`#` 注释）：
```
IP | 描述 | SSH用户 | 密钥文件(密码登录填-) | 密码(密钥登录填-)
```

**示例**：
```
172.31.36.31 | tke-sit-node01 | ubuntu | tencent/ubuntu_test.pem | -
172.31.16.40 | cosmic-nginx | ai_reader | - | m4B2pY5sHDIW@
```

- **密钥登录**：第 4 列填密钥相对路径（基础目录 `agent_cwd/ssh-keys/`），第 5 列为 `-`
- **密码登录**：第 4 列为 `-`，第 5 列直接填明文密码（容器通过 sshpass 调用）

**新增/修改服务器**：直接编辑宿主机的 `.servers` 文件（volume 挂载），改完立即生效，无需重启容器。Jenkins 也可以追加一行：

```bash
echo "172.31.16.50 | new-svc | ubuntu | tencent/ubuntu_test.pem | -" >> /path/to/.servers
```

### 云之家 Webhook 配置

`$YZJ_ALERT_WEBHOOK` 直接存**完整的 webhook URL**（含 token），不再单独存 token 拼接：

```bash
# .env
YZJ_ALERT_WEBHOOK=https://www.yunzhijia.com/gateway/robot/webhook/send?yzjtype=0&yzjtoken=xxx
```

SKILL.md 中推送命令直接用：
```bash
curl -s -X POST "$YZJ_ALERT_WEBHOOK" -H "Content-Type: application/json" -d '...'
```

### 安全防护体系（5 层纵深防御）

Agent 全程只读，严禁执行修改/删除/重启/安装操作。共有 5 层防护，任意一层都能拦住危险命令：

| 层级 | 位置 | 拦截方式 | 防护范围 |
|-----|------|---------|---------|
| **L1：SSH 只读账户** | 目标服务器 OS | 系统账户权限（如 `ai_reader`） | 即使绕过应用层，OS 也会拒绝危险命令 |
| **L2：settings.json deny 规则** | `agent_cwd/.claude/settings.json` | Claude Code 内置精确模式匹配 | `ssh * rm *`、`git push*`、`systemctl stop*` 等命令直接 deny |
| **L3：SSH 命令白名单** | `hooks/restrict-ssh.py` + `ssh-allowlist.conf` | PreToolUse hook 解析 heredoc/引号内的远程命令，逐行正则匹配，白名单外**SSH 包根本不发** | 仅放行只读命令：`top/ps/df/iostat/docker ps/kubectl get/jstack/git log` 等 |
| **L4：文件写入白名单** | `hooks/restrict-edit-write.py` | PreToolUse hook 拦截 Edit/Write，只允许写 `data/issue-diagnosis/instincts/` | 保护代码、配置、知识库不被 Agent 误改 |
| **L5：SKILL.md 提示约束** | `agent_cwd/.claude/skills/ops-diagnosis/SKILL.md` | 提示词明确列出禁止/允许的命令清单 | LLM 自我审查，减少 99% 的危险尝试 |

**纵深防御示意**（以 `ssh host rm -rf /` 为例）：

```
[L5] SKILL.md 提示       → LLM 通常根本不会生成这种命令
   ↓
[L2] settings.json deny  → "Bash(ssh * rm -rf *)" 命中黑名单
   ↓
[L3] SSH 白名单          → 远程命令 rm 不在 allowlist
   ↓
[L1] OS 账户权限         → ai_reader 无权 rm /
   ↓
执行失败 ❌
```

**维护说明**：
- 新增允许的 SSH 命令 → 编辑 `agent_cwd/.claude/hooks/ssh-allowlist.conf`
- 新增 deny 命令模式 → 编辑 `agent_cwd/.claude/settings.json`
- 修改 hook 即生效，无需重启服务（hook 每次 PreToolUse 重新加载）

### 目标服务器/容器前置条件

诊断流程依赖目标侧已安装相关工具。**Agent 服务本身不需要装这些工具**，它们装在被 SSH 的服务器或被 `docker exec` 进入的业务容器里。

**宿主机层（必须）**

| 工具 | 用途 | 安装方式 |
|------|------|---------|
| `iostat` / `sar` / `mpstat` / `vmstat` / `pidstat` | CPU/IO 采集 | `yum install sysstat` 或 `apt install sysstat` |
| `iotop` | 按进程的 IO 速率 | `yum install iotop` 或 `apt install iotop` |
| `lsof` | 写入文件定位、幽灵文件检测 | 多数发行版自带 |
| `docker` 或 `crictl` | 容器列表/资源/exec | 已部署容器自然有 |

**Java 业务容器（需要）**

JDK 自带 `jstack` / `jstat` / `jcmd` / `jmap`。注意：
- 镜像基于 `openjdk:*-jre-slim` 时**只有 JRE 没有 JDK**，`jstack` 等命令缺失。建议改用 `openjdk:*-jdk-slim` 或在 Dockerfile 里追加：
  ```dockerfile
  RUN apt-get update && apt-get install -y --no-install-recommends openjdk-17-jdk-headless
  ```
- 容器内 Java 进程 PID 不一定是 1（取决于启动方式），诊断脚本会自动按 `ps` 匹配 `java` 关键字定位真实 PID

**Python 业务容器（建议安装 py-spy）**

Python 没有 jstack 那样的内置工具，需要 `py-spy` 才能拿到线程级代码栈。**未安装时只能拿到内核态栈，看不到 Python 代码位置。**

```dockerfile
# 在 Python 服务的 Dockerfile 里加一行
RUN pip install --no-cache-dir py-spy
```

或运行时安装（不推荐，重启后失效）：
```bash
docker exec <container> pip install py-spy
```

**py-spy 权限要求**：

py-spy 需要读取目标进程内存，依赖以下条件之一：
- 容器以 `--cap-add=SYS_PTRACE` 启动（推荐）
- 容器以 `privileged: true` 启动（不推荐，权限过大）
- 宿主机 `/proc/sys/kernel/yama/ptrace_scope` 设为 `0`

docker-compose 示例：
```yaml
services:
  my-python-app:
    cap_add:
      - SYS_PTRACE
```

**未安装 py-spy 时的降级行为**：

诊断脚本会自动回退到读 `/proc/<tid>/stack`（内核栈），同时在输出里提示运维安装 py-spy。能拿到线程是在哪个系统调用上阻塞，但拿不到 Python 业务代码位置。

### 服务器配置文件（`.servers`）

`.servers` 位于项目根目录，与 `.env` 同级，**不提交 git**（`.gitignore` 已忽略）。通过 volume 挂载到容器，修改后**立即生效，无需重启**。

**格式**（一行一台，`|` 分隔，`#` 开头为注释）：

```
IP | 描述 | SSH用户 | 密钥文件(密码登录填-) | 密码(密钥登录填-)
```

**完整示例**：

```
# === tencent 环境 ===
172.31.36.31 | tke-sit-node01  | ubuntu    | tencent/ubuntu_test.pem | -
172.31.16.40 | cosmic-nginx    | ai_reader | -                       | m4B2pY5sHDIW@

# === AWS 环境 ===
10.0.1.100   | prod-web-01     | ec2-user  | aws/prod.pem            | -
```

**两种认证方式**：

| 认证方式 | 密钥文件列 | 密码列 | Agent 连接命令 |
|---------|-----------|--------|--------------|
| 密钥登录 | `tencent/rocky_test.pem` | `-` | `ssh -i agent_cwd/ssh-keys/{密钥文件} {用户}@{IP}` |
| 密码登录 | `-` | 明文密码 | `sshpass -p '{密码}' ssh {用户}@{IP}` |

密钥文件路径相对于 `agent_cwd/ssh-keys/`，实际文件通过 volume 挂载（`./agent_cwd/ssh-keys`）。

**新增服务器**（三种方式任选）：

```bash
# 1. 直接在宿主机编辑
vim /path/to/agent-harness/.servers

# 2. Jenkins Pipeline 追加一行
echo "172.31.16.50 | new-svc | ubuntu | tencent/ubuntu_test.pem | -" >> /path/to/.servers

# 3. 密码登录服务器
echo "172.31.16.51 | new-svc-pwd | root | - | your_password" >> /path/to/.servers
```

**初始化**：首次部署时从 `.servers.example` 复制（如有），或直接创建：

```bash
cp .servers.example .servers   # 如果有示例文件
# 或直接创建并填写
vim .servers
```

---

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

### 云之家机器人配置（@机器人主动对话）

支持在群里 @机器人 触发任意 skill，覆盖运维问诊、客服问答、主动追问等场景。

**整体流程**：

```
群里 @机器人 "帮我看看 172.31.16.40 IO 情况"
   ↓
POST http://your-host:9123/yzj/chat?yzj_token=xxx&skill=ops-diagnosis
   ↓
yzj_chat 立即返回 200（云之家不会重试）
   ↓
后台任务调用 AgentService.process_query(skill=ops-diagnosis)
   ↓
通过 sessionId 查找/创建会话上下文（同一会话延续 30 分钟）
   ↓
SSE 流式响应 → 收集完整结果
   ↓
通过 webhook 推回云之家群（文本 / 图片卡片）
```

#### 步骤 1：云之家后台创建机器人

1. 进入云之家管理后台 → 群机器人管理
2. 机器人类型选 **对话型机器人**（不是"群通知型"）
3. 回调 URL 填：

   ```
   http://42.193.101.189:9123/yzj/chat?yzj_token={机器人 Token}
   ```

4. 不同业务场景可在 URL 加 `?skill=` 参数指定 skill：

   | 场景 | 回调 URL 示例 |
   |------|-------------|
   | 客服群（默认） | `?yzj_token=xxx` |
   | 运维诊断群 | `?yzj_token=xxx&skill=ops-diagnosis` |
   | 数据分析群 | `?yzj_token=xxx&skill=operational-analytics` |

   未传 `skill` 参数时使用 `.env` 中的 `YZJ_DEFAULT_SKILL`（默认 `customer-service`）。

#### 步骤 2：`.env` 关键配置

```bash
# 默认 skill（URL 不带 skill 参数时生效）
YZJ_DEFAULT_SKILL=customer-service

# 会话超时（秒），超时后下次对话开新会话
YZJ_SESSION_TIMEOUT=1800

# 消息详细程度
# true: 详细模式，输出所有中间过程
# false: 简洁模式，只输出最终答案（推荐）
YZJ_VERBOSE=false

# 卡片消息模板 ID（在云之家后台创建后填入）
YZJ_CARD_TEMPLATE_ID=64d08cb4e4b07ba2b112b395

# 服务公网地址（云之家拉取图片时需要能访问到）
SERVICE_BASE_URL=http://42.193.101.189:9123
```

#### 步骤 3：群里 @机器人 使用

```
@机器人 星空旗舰版如何配置开票人员？           # 客服 skill
@机器人 帮我看看 172.31.16.40 现在 IO 怎么样   # ops-diagnosis skill
@机器人 上周订单量同比是多少                     # operational-analytics skill
```

**多轮对话**自动延续上下文（同一 sessionId 30 分钟内）：

```
[运维] @机器人 ZK 写入暴增是什么原因？
[机器人] 经诊断是 RabbitMQ 客户端 172.31.16.50 高频提交 offset 导致...
[运维] @机器人 那继续看下这个客户端的连接数
[机器人] （复用之前会话上下文）该客户端当前 channels=152，明显高于均值...
```

#### 与告警诊断的协同

三种触发方式互补使用：

| 触发方式 | 端点 | 适用场景 |
|---------|------|---------|
| Alertmanager 自动 | `/api/alert-webhook` | Prometheus 告警自动诊断 |
| 文本告警转发 | `/api/alert-text` | 脚本/腾讯云告警，恢复消息原文转发 |
| 云之家 @机器人 | `/yzj/chat` | 运维主动追问、深度排查、跨场景问答 |

**典型协同场景**：
1. Prometheus 触发告警 → `/api/alert-webhook` 自动诊断 → 群里推摘要
2. 运维看到摘要 → 群里 @机器人 继续追问 → Agent 复用上下文给出更深入分析

#### 调试

设置 `YZJ_MOCK_ENABLED=true` 后，访问 `http://host:9123/yzj/debug` 打开调试页面，无需云之家就能模拟群消息测试机器人响应。

#### 查看会话状态

```bash
curl http://host:9123/yzj/stats
```

返回当前活跃会话数、各 token 的会话映射等。

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
PORT=9123
LOG_LEVEL=INFO

# 云之家告警推送（完整 webhook URL，含 token）
YZJ_ALERT_WEBHOOK=https://www.yunzhijia.com/gateway/robot/webhook/send?yzjtype=0&yzjtoken=xxx

# 告警去重与限流
ALERT_COOLDOWN_SECONDS=1800   # 同一告警冷却期，默认 30 分钟
ALERT_MAX_CONCURRENT=5         # 全局并发诊断上限

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
