# 请求链路性能分析指南

## 日志格式

每个埋点输出一行：

```
[PERF] rid=a3f2c1b0 PROMPT_BUILT step=2.3ms total=2.4ms
```

- `rid` — request_id（HTTP 路径取随机 8 位 hex，云之家/智齿取 session_id 前 8 位）
- `step` — 距上一个节点的耗时
- `total` — 距请求入口的累计耗时

---

## 7 个节点说明

| # | label | 含义 | 所在文件 |
|---|-------|------|---------|
| 1 | `REQUEST_RECEIVED` | HTTP 请求解析完成 | `api/routers/agent.py` |
| 2 | `PROMPT_BUILT` | prompt 组装完成 | `api/services/agent_service.py` |
| 3 | `SDK_CONNECTED` | Claude SDK 连接建立 | `api/services/agent_service.py` |
| 4 | `FIRST_MESSAGE` | SDK 返回首条消息 | `api/core/streaming.py` |
| 5 | `STREAM_DONE` | SDK 流结束（ResultMessage） | `api/core/streaming.py` |
| 6 | `YZJ_SEND_START` / `ZHICHI_SEND_START` | 开始向渠道发送消息 | `plugins/bundled/*/handler.py` |
| 7 | `DONE` | 全链路结束 | `plugins/bundled/*/handler.py` |

云之家还有节点 7b：`YZJ_SEND_DONE`（HTTP 请求到云之家 webhook 的耗时），在 `message_sender.py` 输出，格式略有不同：

```
[PERF] YZJ_SEND_DONE http_ms=87.4ms status=200
```

---

## 抓取数据

```bash
# 抓取所有 PERF 日志
grep '\[PERF\]' log/app.log

# 按 request_id 过滤单次请求
grep '\[PERF\].*rid=a3f2c1b0' log/app.log

# 只看关键节点耗时（去掉 heartbeat 等噪音）
grep '\[PERF\]' log/app.log | grep -E 'SDK_CONNECTED|FIRST_MESSAGE|STREAM_DONE|DONE'

# 提取所有 FIRST_MESSAGE 的 total 值（批量统计 TTFT）
grep '\[PERF\].*FIRST_MESSAGE' log/app.log | grep -oP 'total=\K[\d.]+'
```

---

## 关键指标定义

| 指标 | 计算方式 | 说明 |
|------|---------|------|
| **TTFT**（首 token 延迟） | `FIRST_MESSAGE.total` | 用户感知到第一条回复的等待时间 |
| **SDK 连接耗时** | `SDK_CONNECTED.step` | Claude SDK 进程启动时间 |
| **LLM 推理耗时** | `STREAM_DONE.total - SDK_CONNECTED.total` | SDK 连接后到流结束 |
| **渠道发送耗时** | `DONE.total - STREAM_DONE.total` | 消息推送到云之家/智齿的耗时 |
| **全链路耗时** | `DONE.total` | 端到端总耗时 |

---

## 批量统计脚本

```bash
# 统计 TTFT 的 P50 / P90 / P99（需要 awk）
grep '\[PERF\].*FIRST_MESSAGE' log/app.log \
  | grep -oP 'total=\K[\d.]+' \
  | sort -n \
  | awk '
    BEGIN { n=0 }
    { a[n++]=$1 }
    END {
      p50=a[int(n*0.50)]; p90=a[int(n*0.90)]; p99=a[int(n*0.99)]
      printf "count=%d  P50=%.0fms  P90=%.0fms  P99=%.0fms\n", n, p50, p90, p99
    }'

# 统计全链路耗时 P50/P90/P99
grep '\[PERF\].*\bDONE\b' log/app.log \
  | grep -oP 'total=\K[\d.]+' \
  | sort -n \
  | awk '
    BEGIN { n=0 }
    { a[n++]=$1 }
    END {
      p50=a[int(n*0.50)]; p90=a[int(n*0.90)]; p99=a[int(n*0.99)]
      printf "count=%d  P50=%.0fms  P90=%.0fms  P99=%.0fms\n", n, p50, p90, p99
    }'
```

---

## 优化前后对比表模板

优化后将日志另存（如 `log/app.after.log`），用相同脚本跑一遍，填入下表：

| 指标 | 优化前 P50 | 优化前 P90 | 优化后 P50 | 优化后 P90 | 变化 |
|------|-----------|-----------|-----------|-----------|------|
| TTFT | — ms | — ms | — ms | — ms | — |
| SDK 连接耗时 | — ms | — ms | — ms | — ms | — |
| LLM 推理耗时 | — ms | — ms | — ms | — ms | — |
| 渠道发送耗时 | — ms | — ms | — ms | — ms | — |
| 全链路耗时 | — ms | — ms | — ms | — ms | — |

---

## 典型瓶颈定位

| 现象 | 可能原因 | 排查方向 |
|------|---------|---------|
| `SDK_CONNECTED.step` > 2s | Claude Code CLI 进程冷启动慢 | 检查 ccr 代理、模型路由配置 |
| `FIRST_MESSAGE.step`（即 SDK 连接后到首消息）> 5s | LLM 推理慢 / 网络延迟 | 对比不同模型、检查代理延迟 |
| `DONE.step`（渠道发送）> 500ms | 云之家/智齿 webhook 响应慢 | 检查 `YZJ_SEND_DONE http_ms` |
| `PROMPT_BUILT.step` > 100ms | context 文件 I/O 慢 | 检查 `save_context()` 磁盘写入 |
