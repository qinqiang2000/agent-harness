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

alert_time 优先取当前的中国上海的时间。
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

## Step 2.5：备份任务快速识别（短路判断）

在 Step 2 采集数据返回后，**优先检查是否为备份任务导致的告警**：

**判断条件**（同时满足以下任一组合即命中）：
1. 告警类型为 **CPU使用率高** 或 **磁盘IO利用率高**
2. 采集数据中 `ps aux` 或 `top` 输出存在 `pigz` 进程占用高 CPU

**如果命中备份任务**：
- 跳过 Step 3、4、5 的完整诊断流程
- 直接推送以下简短提示到云之家，然后结束：

```
服务器[{server_name}]({target_ip}) 当前正在进行后台数据备份（pigz压缩），请忽略本次{alert_type}告警。
```

推送方式同 Step 6 的云之家 curl 命令。

**如果未命中**：继续执行 Step 3。

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

综合以下信息进行关联分析：

| 数据源 | 分析重点 |
|--------|---------|
| 线程栈/top 输出 | 哪些函数/方法占用最多 CPU 时间 |
| 进程内存 | 哪个进程内存增长异常 |
| 代码 diff | 最近变更是否引入性能问题 |
| 时间线 | 告警时间 vs 最近部署时间的关联性 |

**分析逻辑**：
1. 如果告警时间与某次部署时间高度吻合（部署后 0-60 分钟内告警）→ 大概率是该次部署引起
2. 将线程栈中的热点函数/类名与 diff 中变更的文件/方法交叉比对
3. 如果找到匹配 → 定位到具体 commit + 文件 + 代码段
4. 如果无匹配或无近期部署 → 基于采集数据给出当前状态分析和建议

**输出结论格式**（纯文本，不用 Markdown，500字以内）：

**磁盘告警的"状态"字段必须按挂载点展示**，格式如下：
```
[分区使用详情]
🚨 /datadisk -> 96% (238G/250G)
✅ /backup_test_data -> 46% (562G/1.3T)
✅ / -> 32% (12G/40G)
```
（🚨 表示使用率 ≥ 70%，✅ 表示正常）

```
【{alert_type}告警诊断】{server_name} ({target_ip})

时间: {alert_time}
状态: {当前资源使用概况，磁盘告警用上述挂载点格式}

根因分析:
{分析结论，包含具体进程/服务名}

{如果定位到代码变更}
可疑变更:
- Commit: {hash前8位} {message}
- 作者: {author}
- 时间: {commit_time}
- 文件: {changed_file}
- 问题: {具体代码问题描述}

建议:
{修复建议，1-3条}
```

---

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
