---
name: ops-diagnosis
description: >-
  运维告警自动诊断与根因定位。接收 Prometheus 告警上下文（告警类型、目标IP、告警时间），
  通过 SSH 远程采集诊断数据，分析根因，推送结论到云之家。
  适用场景：CPU使用率高、内存使用率高、磁盘空间不足、磁盘IO利用率高、容器OOMKilled、服务响应慢。
  触发词：CPU高、内存高、磁盘满、IO高、告警、alert、诊断、排查。
---

# 运维告警诊断

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

读取prompt的服务器ip，读取项目根目录的 `.servers` 文件根据 服务器IP 查找对应的ssh信息。

`.servers` 文件格式（`|` 分隔，`#` 开头为注释）：
```
IP | 描述 | SSH用户 | 密钥文件(密码登录填-) | 密码(密钥登录填-)
```

如果是密码，则直接使用密码，如果后缀带.pem则是密钥，密钥的路径为： `./agent_cwd/ssh-keys/tencent或aws/{ssh_key}`。

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
timeout 300 ssh -T -i /datadisk/rundeck/ssh/{ssh_key} \
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



## Step 5：推送云之家

**🚨 强制执行顺序：必须先 5.1 保存报告拿到 report_id，再 5.2 推送摘要。严禁跳过 5.1 直接推送完整内容到云之家！**

### 5.1 保存完整报告（必须执行，不可跳过）

通过 HTTP 接口保存完整诊断报告（包含采集的原始数据和分析过程），获取 report_id：

```bash
curl -s -X POST "http://127.0.0.1:9123/api/reports/" \
  -H "Content-Type: application/json" \
  -d '{
    "server_name": "{server_name}",
    "ip": "{target_ip}",
    "alert_type": "{alert_type}",
    "alert_time": "{alert_time}",
    "summary": "{Step 5 结论的一句话摘要}",
    "full_report": "{完整诊断内容，包含采集数据和分析过程}"
  }'
```

接口返回 `{"report_id": "xxxx"}`，**必须提取 report_id 用于下一步**。

### 5.2 推送摘要到云之家（严禁推送完整分析内容）

**⚠️ 云之家消息只允许推送精简摘要 + 报告链接，严禁将完整根因分析、建议等内容直接推送！**

推送格式（控制在 150 字以内）：

```bash
curl -s -X POST "$YZJ_ALERT_WEBHOOK" \
  -H "Content-Type: application/json" \
  -d '{"msgType": 0, "content": "【{alert_type}告警】{server_name}({target_ip})\n时间: {alert_time}\n状态: 🚨 {异常对象} -> {使用率}\n\n{一句话根因，不超过50字}\n\n详情: http://42.193.101.189:9123/api/reports/{report_id}"}'
```

**⚠️ content 中的换行用 `\n`，双引号用 `\"`，确保 JSON 合法。**
**⚠️ `$YZJ_ALERT_WEBHOOK` 从环境变量获取，值为完整的云之家群机器人 webhook URL。**
**⚠️ SERVICE_BASE_URL 固定为 `http://42.193.101.189:9123`，直接硬编码到 URL 中。**
**⚠️ 云之家推送内容禁止包含"建议"、"详细分析"等段落，这些内容只存在于报告页面中。**

推送完成后，将同样的摘要作为最终回复输出。

---

## 异常处理

| 场景 | 处理方式 |
|------|---------|
| SSH 连接失败 | 推送失败通知到云之家，说明连接失败原因 |
| 目标 IP 不在 .servers 中 | 使用默认 SSH 配置（root + rocky_test.pem）尝试连接 |
| 采集数据为空 | 推送失败通知，建议人工检查 |
