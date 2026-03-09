---
name: issue-diagnosis
description: 通用服务问题诊断与根因定位。处理任意服务的报错排查，通过「FAQ检索 → 日志分析 → 源码定位」三步流程给出定位结论。当用户提供报错信息、异常堆栈、traceId，或询问服务/接口报错原因时使用。
  触发词：报错排查、问题定位、根因分析、traceId查询、日志分析、异常排查、堆栈分析、NullPointerException、服务异常、接口异常、
  rpa收票报错、查验失败、影像识别失败、OFD下载失败、PDF下载失败、
  登录失败、鉴权失败、token失效、clientId错误、验证码失败、二维码异常、
  参数校验失败、参数格式错误、接口调用失败、字段不合法、
  接口超时、服务超时、连接失败、响应慢、限流
---

# 通用问题诊断

严格按以下步骤执行，不可跳步。

---

## Step 0：解析输入

从用户问题中提取：
- `traceId`：服务常用的链接追踪的字符串
- `keywords`：错误关键词、异常类名、错误码、报错文本
- `service`：用户提及的服务名（可选）
- `timeRange`：时间范围（可选，如"今天上午"、"2025-03-05 10:00"）
-- `env`: 环境信息，例如生产，测试，演示。用户没指明环境则默认为生产环境
输入为空（无 traceId 也无关键词）→ 回复"请提供报错信息、traceId 或错误关键词"，终止流程。

---

## Step 1：FAQ 快速检索

**第一步：判断涉及领域**，按关键词映射到对应 FAQ 文件（可多选，并行读取）：

| 领域 | 触发关键词 | 文件 |
|---|---|---|
| 开票 | 开票、开具、发票、红冲、票种 | [kb/开票-faq.md](kb/开票-faq.md) |
| 收票 | 收票、查验、影像、OFD、PDF | [kb/收票-faq.md](kb/收票-faq.md) |
| 鉴权登录 | 登录、鉴权、token、clientId、验证码、二维码 | [kb/鉴权登录-faq.md](kb/鉴权登录-faq.md) |
| 接口参数 | 参数、字段、格式、必填、校验、不合法 | [kb/接口参数-faq.md](kb/接口参数-faq.md) |
| 性能超时 | 超时、timeout、慢、连接失败、积压 | [kb/性能超时-faq.md](kb/性能超时-faq.md) |

无法判断领域时 → 并行读取全部文件。

**第二步：在匹配的文件中检索**，优先级：
1. 完全匹配错误文本
2. 关键词命中「> 相似问题:」标签
3. 错误码/异常关键字部分匹配
4. 业务场景匹配

**命中 FAQ**：
- 立即输出匹配的解决方案
- 若有 traceId 或足够关键词 → 继续 Step 2 用日志验证
- 若无法查日志（无 traceId 且关键词过于模糊）→ 直接返回 FAQ 结果，结束

**未命中 FAQ**：继续 Step 2

---

## Step 2：ELK 日志查询与分析

参照 [references/log-analysis.md](references/log-analysis.md) 的查询策略和分组规则。

**构建查询参数**：
- 有 traceId → 仅用 traceId，不传 searchWordList
- 无 traceId → 用 keywords 构建 searchWordList，自动追加 `"AI_KEYWORD ISSUE"`
优先使用traceid查询

调用 `mcp__elastic__searchTraceOrKeyWordsLog` 查询，完成：
1. 按 traceId 合并，生成 callChain 时间线
2. 按问题类型智能分组（错误码 > 异常类型 > 业务场景 > 错误特征）
3. 深度分析每组的 `possibleCause` 和 `suggestedSolution`

从日志中提取 `fields.project` 作为服务标识（供 Step 3 使用）。

**日志查不到**：用用户原始问题重新检索 FAQ，输出结论后终止。

---

## Step 2.3：数据库辅助查询（条件触发）

**触发条件**（满足任一）：
- FAQ 建议"查询数据库确认配置"
- FAQ 条目中标注「数据库验证」→ 命中后自动触发
- 需确认用户数据、权益配置、租户信息

**执行步骤**：
1. 读取 FAQ 中「数据库验证」标注的数据源和表，从 [references/db-queries.md](references/db-queries.md) 获取对应 SQL 模板
2. 按模板依次执行查询：
   ```bash
   python3 agent_cwd/.claude/skills/issue-diagnosis/db/db_query.py --source <数据源> --sql "SELECT ..."
   ```
   - 首次运行会自动创建虚拟环境并安装依赖，无需手动操作
   - 不确定字段名时先执行 `--describe <table>` 确认
3. 将查询结果纳入最终诊断报告

**注意**：无法确定表名/字段时，跳过此步骤，勿猜测。

---

## Step 2.5：GitLab 源码定位（条件触发）

**触发条件**（同时满足）：
1. 存在任意一组 `needKnowledgeQuery == true`
2. 该组至少一条日志的 `callChain` 不为空

参照 [references/gitlab-lookup.md](references/gitlab-lookup.md) 的定位策略，完成：
1. 从 callChain 识别**报错类**（最后一条 ERROR）、**调用者类**（其前一步）
2. 用 `fields.project` 动态查找 GitLab 仓库（最多 3 个类并行拉取）
3. 结合源码还原调用链，补充 `possibleCause`（加 `[源码]` 前缀）

---

## Step 3：综合输出

**情况 A：FAQ 命中 + 日志验证**
```
【FAQ 已知方案】
{faq_result}

【日志验证】
TraceId: {traceId}，时间: {timestamp}
结论: {与FAQ吻合 / 发现新信息}
```

**情况 B：FAQ 未命中，纯日志+源码分析**
```
【问题诊断报告】
服务: {fields.project}，时间: {timestamp}

【根因分析】
{possibleCause}（含源码定位时加 [源码] 前缀）

【解决建议】
{suggestedSolution}
```

**情况 C：多个分组**
每组独立输出上述格式，最终拼接：
```
共发现 N 类问题：

【{groupName}】（N 条记录）
TraceId: xxx ...
{该组诊断报告}
```

回答简洁明了，不超过 300 字（多组时每组不超过 200 字）。
