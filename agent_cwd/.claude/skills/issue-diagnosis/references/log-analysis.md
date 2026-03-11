# 日志查询与分析规则

## 查询策略

- **有 traceId** → 仅传 traceId，不传 searchWordList（精确定位）
- **无 traceId** → 仅用 searchWordList 关键词查询

## 返回格式（标准 JSON）

```json
{
  "success": true,
  "groups": [
    {
      "groupName": "问题类型（10字内）",
      "possibleCause": "基于原始日志的具体原因（40-80字，含参数值/错误码/堆栈）",
      "suggestedSolution": "具体可操作步骤（40-80字）",
      "needKnowledgeQuery": true,
      "logs": [
        {
          "traceId": "xxx",
          "timestamp": "2025-03-05 10:30:45",
          "summary": "[ERROR] 问题简洁描述（50-150字）",
          "duration": "500毫秒",
          "service": "fields.project 的值",
          "callChain": [
            { "ts": "10:30:45.123", "level": "ERROR", "class": "com.xxx.ClassName", "snippet": "日志核心内容（30字内）" }
          ]
        }
      ]
    }
  ]
}
```

查不到日志返回：`{"success": false, "groups": []}`

---

## 第一步：按 traceId 合并

- 同一 traceId 的多条日志合并为一条，取最早 timestamp
- `duration`：最早到最晚时间差（<1s 显示毫秒，<60s 显示秒，≥60s 显示分钟）
- `service`：取该 traceId 任意一条日志的 `fields.project`
- `callChain`：所有日志按时间排序，逐条映射（`class` 用正则 `(com\.[a-zA-Z0-9_.]+)` 提取，去掉 `-数字` 后缀）
- ERROR 级别信息优先反映在 summary 中

**summary 规则**：格式 `[级别] 问题描述`，保留关键业务参数（ID、错误码等），忽略冗长请求体，50-150字

**needKnowledgeQuery**：成功场景（summary 含"成功"且无异常）→ `false`，其余 → `true`

**contextInsufficient**：满足以下任一条件时标记为 `true`，否则 `false`：
- `callChain` 为空
- `callChain` 只有 1 条且不含 ERROR 级别
- `summary` 少于 20 字且无错误码/异常类名

`contextInsufficient == true` 时，`suggestedSolution` 末尾追加："⚠️ 日志上下文有限，建议提供 traceId 以获取完整调用链。"

---

## 第二步：按问题类型分组

分组优先级：**错误码 > 异常类型 > 业务场景 > 错误特征**

相同/相似的错误归为一组，成功记录单独一组。

---

## 第三步：深度分析（必须回到原始日志）

**不能仅依赖 summary**，必须从完整日志中提取细节。

| 关键词 | 需提取 | 示例 |
|---|---|---|
| timeout / 超时 | 实际耗时、超时阈值、接口名 | 调用XX接口耗时5.2s，超过3s阈值 |
| 500 / Internal Error | HTTP 状态码、响应内容 | 接口返回500，响应：'数据库连接失败' |
| 401/403 / 鉴权失败 | clientId、token、错误消息 | clientId为空，实际值：'null' |
| 参数校验 / 不合法 | 参数名、实际值、期望格式 | 字段值含空格导致校验失败 |
| NullPointerException | 堆栈、出错类和方法 | Service.process()中对象为null |
| 连接失败 | 连接目标、地址、错误详情 | 连接Redis失败，地址127.0.0.1:6379 |
| 缓存 key 不匹配 | 带下标 key、不带下标 key、tableIndex | checkData:261420000001211879265 vs checkData:26142000000121187926 |
| 状态不一致 | 缓存状态、DB状态、税局状态、时间差 | 缓存返回正常，税局已红冲，时间差9分钟 |

成功场景：`possibleCause` 填"操作正常完成"，`suggestedSolution` 填"无需处理"
