---
name: ops-diagnosis
description: >-
  运维告警自动诊断与根因定位。接收 Prometheus 告警上下文（告警类型、目标IP、告警时间），
  通过 SSH 远程采集诊断数据，关联 GitLab 近期部署变更，分析根因代码，推送结论到云之家。
  适用场景：CPU使用率高、内存使用率高、磁盘空间不足、磁盘IO利用率高、容器OOMKilled、服务响应慢。
  触发词：CPU高、内存高、磁盘满、IO高、告警、alert、诊断、排查。
---

# 运维告警诊断

**⚠️ 你只有只读权限。严禁执行任何修改、删除、重启、安装操作。只能执行查询类命令。**

**⚠️ 全程静默执行，不输出步骤标题。只在最后输出结论和推送云之家。**

---

## ⚠️ 安全约束（每步开始前自检）

- **禁止**: rm, kill, reboot, shutdown, systemctl stop/restart, docker stop/rm/restart, kubectl delete, apt, yum, pip, chmod, chown, mv, dd, mkfs
- **允许**: cat, top, ps, free, df, iostat, jstack, docker ps, docker stats, docker logs, kubectl get, kubectl describe, kubectl logs, git log, git diff, git show, find, du, ls, uptime, dmesg, netstat, ss, lsof, vmstat, mpstat, pidstat, sar
- **SSH 命令格式**: `ssh -T -i {key_path} -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 {user}@{ip}`
- **GitLab 操作**: 只允许 clone/pull 和 read，禁止 push/commit/edit

---

## Step 1：解析告警上下文

从 prompt 中提取以下信息：

| 字段 | 说明 | 示例 |
|------|------|------|
| alert_type | 告警类型 | CPU / Memory / Disk / IO |
| target_ip | 目标服务器 IP | 172.31.36.31 |
| alert_time | 告警触发时间 | 2026-05-06 14:30:00 |
| yzj_token | 云之家群机器人 Token | token_for_test_46_xxx |
| ssh_user | SSH 用户 | ubuntu |
| ssh_key | SSH 密钥文件名 | ubuntu_test.pem |
| server_name | 服务器描述 | tke-sit-node01 |

如果 prompt 中未提供 SSH 信息，读取 [references/server-mapping.md](references/server-mapping.md) 根据 IP 查找。

SSH 密钥路径固定为: `/datadisk/rundeck/ssh/{ssh_key}`

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
1. 告警类型包含 **CPU** 或 **IO**
2. 采集数据中存在 `pigz` 进程占用高资源

**🚨 强制阻断指令（必须严格遵守）**：
**只要命中上述条件，不管系统中是否还存在其他严重问题（如几千个数据库连接、高内存等），都必须无条件触发短路！绝对禁止执行 Step 3、4、5！**

请直接（且只能）推送以下单行文本到云之家，**然后立刻结束整个输出流程，不准附加任何其他分析或建议**：

服务器[{server_name}]({target_ip}) 当前正在进行后台数据备份（pigz压缩），请忽略本次{alert_type}告警。

---

## Step 3：识别可疑服务

从 Step 2 采集数据中提取高资源消耗的进程/服务：

1. **Java 进程**: 从 `ps aux` 中提取 `-jar xxx.jar` 或 Spring Boot 应用名
2. **Docker 容器**: 从 `docker ps` 或 `crictl ps` 中提取容器名
3. **K8s Pod**: 如果是 TKE 节点，用 `kubectl get pods --field-selector spec.nodeName={node} -A` 获取 Pod 列表

提取出的服务名列表，在 `data/kb/issue-diagnosis/references/service-repo-map.md` 中查找对应的 GitLab 仓库路径（`project_id`）。

**⚠️ 如果 service-repo-map.md 中未找到匹配**：跳过 Step 4，直接进入 Step 5 基于采集数据给出分析。

---

## Step 4：GitLab 部署关联

对 Step 3 中匹配到的每个服务仓库：

### 4.1 Clone 仓库

**必须原样使用以下模板，禁止修改 URL 格式**：

```bash
LOCAL_DIR="/tmp/gitlab/src/{repo-name}" && ([ -d "$LOCAL_DIR/.git" ] && git -C "$LOCAL_DIR" pull || git clone --depth 50 "https://token:$GITLAB_TOKEN@test-master.piaozone.com/git/{project_id}.git" "$LOCAL_DIR")
```

### 4.2 查最近部署

```bash
git -C /tmp/gitlab/src/{repo-name} log --since="3 hours ago" --format="%H %ai %s" --all
```

### 4.3 获取可疑 commit 的 diff

如果告警时间前 1-2 小时内有提交，获取 diff：

```bash
git -C /tmp/gitlab/src/{repo-name} diff {commit}~1 {commit} --stat
git -C /tmp/gitlab/src/{repo-name} show {commit} --format="%H %an %ai%n%s%n%b" --stat
git -C /tmp/gitlab/src/{repo-name} diff {commit}~1 {commit} -- "*.java" "*.py" "*.go" "*.js" "*.ts"
```

重点关注代码 diff 中的：
- 新增循环、递归调用
- 大对象创建、内存分配
- 数据库查询变更（缺少索引、全表扫描）
- 线程/连接池配置变更
- IO 密集操作（文件读写、网络调用）

---

## Step 5：根因分析

(自检：如果在 Step 2.5 已经发现了 pigz 备份任务，严禁输出本步骤的任何内容！)

综合采集数据进行关联分析，**必须严格过滤正常指标，只输出异常核心信息**：

**分析与精简逻辑（核心约束）**：

1. **只显示异常对象**：磁盘告警只输出使用率超过阈值（如 ≥80%）的挂载点，**严禁输出正常的挂载点（禁止出现 ✅ 状态的分区）**。CPU/内存告警只输出 Top 3 的异常进程。
2. **限定分析范围**：根因分析必须限定在触发告警的特定对象内。例如：如果 `/datadisk` 告警，只分析 `/datadisk` 目录下的超大文件或目录，**绝对忽略**其他分区（如 `/root` 或 `/var`）下的大文件。
3. 关联代码变更：如果告警时间与某次部署时间高度吻合（部署后 0-60 分钟内）且找到代码匹配，才输出可疑代码变更。否则不输出代码部分。

**输出结论格式**（纯文本，严格控制在 300 字以内）：

**【强制格式规则】**：
如果是磁盘 IO 告警，必须结合采集数据（如 df 或 lsblk），将块设备名（如 vdb）映射为对应的挂载点路径（如 /datadisk）。**禁止仅输出设备名**。

```text
【{alert_type}告警诊断】{server_name} ({target_ip})
时间: {alert_time}

状态: 
🚨 {挂载点} ({设备名}) -> {当前使用率/读写速率} 
(例如: 🚨 /datadisk (vdb) -> IO利用率 100% (读取 56MB/s, 3597 r/s))

根因:
{一句话概括核心原因，例如包含具体的 PID、进程名及异常行为。}

建议:
{1-2条最直接的恢复建议。}
```


## Step 6：推送云之家

将 Step 5 的结论推送到云之家群：

```bash
curl -s -X POST "https://www.yunzhijia.com/gateway/robot/webhook/send?yzjtype=0&yzjtoken={yzj_token}" \
  -H "Content-Type: application/json" \
  -d '{"msgType": 0, "content": "{结论文本，注意转义双引号和换行符}"'
```

**⚠️ content 中的换行用 `\n`，双引号用 `\"`，确保 JSON 合法。**

推送完成后，将同样的结论作为最终回复输出。

---

## 异常处理

| 场景 | 处理方式 |
|------|---------|
| SSH 连接失败 | 推送失败通知到云之家，说明连接失败原因 |
| GitLab clone 失败 | 跳过代码关联，仅基于采集数据分析 |
| 无近期部署 | 说明"近3小时无代码变更"，给出当前状态分析 |
| 目标 IP 不在 server-mapping 中 | 使用默认 SSH 配置（root + rocky_test.pem）尝试连接 |
| 采集数据为空 | 推送失败通知，建议人工检查 |
