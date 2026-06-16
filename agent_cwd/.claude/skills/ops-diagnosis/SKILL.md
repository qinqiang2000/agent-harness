

# 运维告警诊断

---
name: ops-diagnosis
description: 
  - 运维告警自动诊断与根因定位。接收 Prometheus 告警上下文（告警类型、目标IP、告警时间），
  - 通过 SSH 远程采集诊断数据，分析根因，推送结论到云之家。
  - 适用场景：CPU使用率高、内存使用率高、磁盘空间不足、磁盘IO利用率高、容器OOMKilled、服务响应慢。
  - 触发词：CPU高、内存高、磁盘满、IO高、告警、alert、诊断、排查。
---

**⚠️ 你只有只读权限。严禁执行任何修改、删除、重启、安装操作。只能执行查询类命令。**

**⚠️ 全程静默执行，不输出步骤标题。只在最后输出结论和推送云之家。**

---

## ⚠️ 安全约束（每步开始前自检）

- **禁止**: rm, kill, reboot, shutdown, systemctl stop/restart, docker stop/rm/restart, kubectl delete, apt, yum, pip, chmod, chown, mv, dd, mkfs
- **允许**: cat, top, ps, free, df, iostat, jstack, docker ps, docker stats, docker logs, kubectl get, kubectl describe, kubectl logs, find, du, ls, uptime, dmesg, netstat, ss, lsof, vmstat, mpstat, pidstat, sar
- **SSH 命令格式**: `ssh -T -i {key_path} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 {user}@{ip}`

---

## Step 1：解析告警上下文

从 prompt 中提取以下信息：

| 字段 | 说明 | 示例 |
|------|------|------|
| alert_type | 告警类型 | CPU / Memory / Disk / IO |
| target_ip | 目标服务器 IP | 172.31.36.31 |
| alert_time | 告警触发时间 | 2026-05-06 14:30:00 |
| yzj_token | 云之家群机器人 Token（从环境变量 `$YZJ_ALERT_WEBHOOK` 获取） | e74c5794... |
| ssh_user | SSH 用户 | ubuntu |
| ssh_key | SSH 密钥文件名 | ubuntu_test.pem |
| server_name | 服务器描述 | tke-sit-node01 |

读取prompt的服务器ip，读取 `../.servers` 文件（即项目根目录的 `.servers`，Agent cwd 的上级目录）根据 服务器IP 查找对应的ssh信息。

`.servers` 文件格式（`|` 分隔，`#` 开头为注释）：
```
IP | 描述 | SSH用户 | 密钥文件(密码登录填-) | 密码(密钥登录填-)
```

如果是密码，则直接使用密码，如果后缀带.pem则是密钥，密钥的路径为： `ssh-keys/{ssh_key}`（相对于当前工作目录 agent_cwd）。

**密码登录服务器使用 sshpass 连接**：
```bash
sshpass -p '{password}' ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  -o ConnectTimeout=10 {ssh_user}@{target_ip} bash -s << 'REMOTE_EOF'
# 采集命令
REMOTE_EOF
```

---

## Step 2：SSH 远程采集

读取 [references/ssh-commands.md](references/ssh-commands.md) 获取对应 `alert_type` 的采集命令模板。

执行 SSH 命令采集数据，使用以下格式：

```bash
timeout 300 ssh -T -i ssh-keys/{ssh_key} \
  -o StrictHostKeyChecking=no \
  -o UserKnownHostsFile=/dev/null \
  -o ConnectTimeout=10 \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  {ssh_user}@{target_ip} bash -s << 'REMOTE_EOF'
# 采集命令（从 ssh-commands.md 获取）
REMOTE_EOF
```

**⚠️ 如果 SSH 连接失败**：直接推送失败通知到云之家，结束流程。

---

## Step 2.5：【最高优先级】备份任务快速识别（强制短路）

在 Step 2 采集数据返回后，**必须第一步**检查是否为备份任务导致的告警。

**判断条件**：
1. 告警类型包含 **CPU** 或 **IO** 或 **Disk**
2. 采集数据中存在以下任一备份相关进程占用高资源：
   - `pigz`（并行 gzip 压缩）
   - `mydumper` / `myloader`（MySQL 多线程备份）
   - `mysqldump`（MySQL 单线程备份）
   - `pg_dump` / `pg_basebackup`（PostgreSQL 备份）
   - `xtrabackup` / `mariabackup`（MySQL 物理备份）
   - `gzip` / `bzip2` / `lz4` / `zstd`（通用压缩，且伴随上述备份工具或写入 backup 相关路径）
   - `rsync`（大量数据同步到备份目录）
   - `tar`（打包备份）

**🚨 强制阻断指令（必须严格遵守）**：
**只要命中上述条件（备份进程 + 对应告警类型），不管系统中是否还存在其他严重问题（如几千个数据库连接、高内存等），都必须无条件触发短路！绝对禁止执行 Step 3、4、5！**

请直接（且只能）推送以下单行文本到云之家，**然后立刻结束整个输出流程，不准附加任何其他分析或建议**：

服务器[{server_name}]({target_ip}) 当前正在进行后台数据备份（{备份工具名}），请忽略本次{alert_type}告警。

---

## Step 3：识别可疑服务

从 Step 2 采集数据中提取高资源消耗的进程/服务：

1. **Java 进程**: 从 `ps aux` 中提取 `-jar xxx.jar` 或 Spring Boot 应用名
2. **Docker 容器**: 从 `docker ps` 或 `crictl ps` 中提取容器名
3. **K8s Pod**: 如果是 TKE 节点，用 `kubectl get pods --field-selector spec.nodeName={node} -A` 获取 Pod 列表

---

## Step 4：根因分析

(自检：如果在 Step 2.5 已经发现了 pigz 备份任务，严禁输出本步骤的任何内容！)

综合采集数据进行关联分析，**必须严格过滤正常指标，只输出异常核心信息**：

**分析与精简逻辑（核心约束）**：

1. **只显示异常对象**：磁盘告警只输出使用率超过阈值（如 ≥80%）的挂载点，**严禁输出正常的挂载点（禁止出现 ✅ 状态的分区）**。CPU/内存告警只输出 Top 3 的异常进程。
2. **限定分析范围**：根因分析必须限定在触发告警的特定对象内。例如：如果 `/datadisk` 告警，只分析 `/datadisk` 目录下的超大文件或目录，**绝对忽略**其他分区（如 `/root` 或 `/var`）下的大文件。

**输出结论格式**（纯文本）：

```text
【{alert_type}告警诊断】
{server_name} ({target_ip})
时间: {alert_time}

状态: 
🚨 {异常对象名称} -> {当前使用率/数值} (例如: /datadisk -> 96% (1.7T/1.8T))

根因:
{一句话概括核心原因，例如：/datadisk 空间不足，主要由 PG 数据目录 pg12 (1.7T) 占用导致。}

建议:
{1-2条最直接的恢复建议，例如：评估 /datadisk 扩容或归档冷数据。}
```

**状态行（status 字段）按告警类型展示对应核心指标，严禁混用：**

| alert_type | 状态行展示内容 | 示例 |
|-----------|---------------|------|
| CPU | 异常进程 -> CPU 使用率% | `🚨 java(PID 1234) -> 187% (4 核机器)` |
| Memory | 异常进程/容器 -> 内存使用 | `🚨 java(PID 1234) -> RES 12G / 总 16G (75%)` |
| Disk（空间） | 挂载点 -> 使用率% (已用/总量) | `🚨 /dev/vdb -> 82% (381G/492G)` |
| **IO（读写速度）** | **磁盘设备 -> 写入/读取速度 + %util，并补充 Top 写入目录** | **`🚨 vdb -> w:120MB/s, r:5MB/s, %util:98%; Top 写入: /var/log/nginx/sandbox_access.log (持续追加 3MB/s)`** |
| 容器 OOM | 容器名 -> OOMKilled 次数 + 最近时间 | `🚨 nginx-pod -> OOMKilled x3 (last: 17:55:23)` |
| 服务响应慢 | 服务名 -> P99 延迟 + QPS | `🚨 order-service -> P99: 2.3s, QPS: 450` |

**IO 告警状态行的强制要求：**
- **必须**使用 `iostat -xdm 1 3` 输出中的 `wMB/s`、`rMB/s`、`%util` 数值
- **必须**通过 `iotop -bon1` 或 `lsof +L1` 等命令定位**当前写入速率最高的具体目录或文件**
- **严禁**用磁盘空间使用率代替 IO 速率（空间是 Disk 告警，不是 IO 告警）



## Step 5：推送结论到云之家

将分析结论与建议直接推送到云之家。完整诊断过程仅在日志中保留，不再持久化为任务单。

### 推送格式

```bash
curl -s -X POST "$YZJ_ALERT_WEBHOOK" \
  -H "Content-Type: application/json" \
  -d '{"msgType": 0, "content": "【{alert_type}告警】\n主机：{server_name}({target_ip})\n时间: {alert_time}\n状态: 🚨 {异常对象} -> {使用率}\n\n【AI分析结果】\n{一句话根因，不超过150字}\n\n【AI建议】\n{1-2条核心建议，每条一行，控制在150字内}"}'
```

**模板结构**（严格按这个分段输出，不可合并、不可省略）：

```
【{alert_type}告警】
主机：{server_name}({target_ip})
时间: {alert_time}
状态: 🚨 {异常对象} -> {核心指标值}

【AI分析结果】
{根因一句话，最多 150 字}

【AI建议】
1. [{风险等级}] {第一条恢复/优化建议}
2. [{风险等级}] {可选第二条建议}
```

---

### 5.2.1 建议命令风险评估（必读）

**生成建议命令前必须做的风险评估**，每条建议的开头必须标注 **[🟢低风险] / [🟡中风险] / [🔴高风险]**：

| 风险等级 | 标识 | 适用命令类型 | 推送策略 |
|---------|------|------------|---------|
| **🟢 低风险** | 只读、可逆、影响范围明确 | 配置查看、阈值调整、日志切换、新增监控、扩容评估 | 直接推送命令 |
| **🟡 中风险** | 影响单服务/单容器，重启或修改可恢复 | 单容器 logrotate、调整服务参数（需重启）、清理已知日志文件 | 推送但加 ⚠️ 备注，要求人工确认后执行 |
| **🔴 高风险** | 影响范围大、不可逆、可能误删 | `docker system prune -a`、`docker image prune -a`、`rm -rf` 数据目录、删除 K8s 资源、重启节点 | **不推送具体命令**，只描述方向，强调"需人工评估" |


**Build Cache 相关**：
- 单独执行 `docker builder prune --filter "until=72h"`（保留近 3 天）是 🟡 中风险，可推送
- `docker builder prune -af`（清空所有）在 K8s 节点上是 🔴 高风险，仅能描述方向不给命令


**示例 — 同样是磁盘空间不足，正确的建议**：

```
【AI建议】
1. [🟡中风险] 清理 nginx access.log（已 12GB，路径 /var/log/nginx/access.log）：执行 cp /dev/null 后建议配置 logrotate
2. [🔴高风险] Build Cache 占用 29GB，建议人工评估后执行 docker builder prune --filter "until=168h" 保留近一周缓存，禁用 prune -af
```

**反例 — 禁止生成的建议**：

```
❌ docker system prune -a       # K8s 节点会误删镜像
❌ docker image prune -a         # 同上
❌ rm -rf /var/lib/docker/...   # 直接破坏 docker 数据
❌ kubectl delete pod xxx        # 不解决根因，反而扰乱集群
```

---

**示例完整推送**：

```
【磁盘空间不足告警】
主机：cicd(172.31.16.100)
时间: 2026-06-16 10:23:46
状态: 🚨 /datadisk -> 93% (277G/300G)

【AI分析结果】
Docker 容器日志无上限膨胀，3 个日志文件累计 58GB，Build Cache 占 29GB。

【AI建议】
1. [🟡中风险] 配置 docker daemon log-opts: max-size=100M,max-file=3，重启 docker 后逐步生效
2. [🔴高风险] Build Cache 29GB 建议人工评估后执行 docker builder prune --filter "until=168h"，禁止使用 -af
```

---

**⚠️ content 中的换行用 `\n`，双引号用 `\"`，确保 JSON 合法。**
**⚠️ `$YZJ_ALERT_WEBHOOK` 从环境变量获取，值为完整的云之家群机器人 webhook URL。**
**⚠️ 两大段落（AI分析结果、AI建议）必须保留，建议简短直接，不要展开"详细分析"。**
**⚠️ 任何 🔴 高风险建议必须明确写"建议人工评估后执行"，禁止给出可直接复制粘贴执行的高风险命令。**

推送完成后，将同样的摘要作为最终回复输出。

---

## 异常处理

| 场景 | 处理方式 |
|------|---------|
| SSH 连接失败 | 推送失败通知到云之家，说明连接失败原因 |
| 目标 IP 不在 .servers 中 | 使用默认 SSH 配置（root + rocky_test.pem）尝试连接 |
| 采集数据为空 | 推送失败通知，建议人工检查 |
