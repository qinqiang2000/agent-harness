---
name: issue-diagnosis
description: >-
  通用服务问题诊断与根因定位。通过「FAQ检索 → 日志分析 → 源码定位」三步流程给出定位结论。
  当用户提供报错信息、异常堆栈、traceId，或询问服务/接口报错原因时，必须使用此 Skill，不要自行猜测原因。
  即使用户只是粘贴了一段错误日志、一个 traceId、或描述了某个接口异常，也应立即触发此 Skill。
  触发词：报错排查、问题定位、根因分析、traceId查询、日志分析、异常排查、堆栈分析、NullPointerException、服务异常、接口异常、rpa收票报错、查验失败、影像识别失败、OFD下载失败、PDF下载失败、登录失败、鉴权失败、token失效、clientId错误、验证码失败、二维码异常、参数校验失败、参数格式错误、接口调用失败、字段不合法、接口超时、服务超时、连接失败、响应慢、限流
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
- `env`: 环境信息，例如生产，测试，演示。用户没指明环境则默认为生产环境
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

参照 [references/log-analysis.md](references/log-analysis.md) 执行查询与分析。

**构建查询参数**：
- 有 traceId → 仅用 traceId
- 无 traceId → 用 keywords 构建 searchWordList
- 时间范围：优先使用用户提供的 `timeRange`；未提供时默认查最近 7 天，若查不到结果则自动扩展到最近 30 天再查一次

调用 `mcp__elastic__searchTraceOrKeyWordsLog`，从返回结果提取 `fields.project`（供 Step 2b 使用）。

**关键词查询后的扩展策略**（仅适用于无 traceId 的关键词查询）：
- 返回结果恰好只有 1 条，且该条日志有 traceId → 自动用该 traceId 再查一次，将两次结果合并后再分析
- 返回结果只有 1 条，且无 traceId → 继续分析，在输出结论中注明"日志上下文有限，建议提供 traceId 以获取完整调用链"
- 返回结果 ≥ 2 条 → 直接分析，无需扩展查询

**日志查不到**：
1. 尝试截取核心词（去掉修饰词、保留异常类名/错误码/核心业务词）重新构建 searchWordList，再查一次
2. 仍查不到 → 用原始问题重新检索 FAQ，输出结论后终止

**日志连接异常**：重试一次。

---

## Step 2a：数据库辅助查询（条件触发）

**触发条件**（必须同时满足）：
- FAQ 条目中明确标注「数据库验证」标签

**不触发的情况**：
- FAQ 未命中
- FAQ 命中但无「数据库验证」标签
- 仅凭日志信号（如 clientId 无效、租户不存在）自行推断 → 跳过，不猜测表名

**数据源选择规则**（参照 `db/db_config.json` 中各数据源的 `env` 和 `domain` 字段）：
- 用户指明"测试环境" → 选 `env=test`；未指明或指明"生产环境" → 选 `env=prod`
- 开票/鉴权相关问题 → 选 `domain=开票/鉴权`（cms 库）
- 运营/订单相关问题 → 选 `domain=运营/订单`（eop 库）

**执行步骤**：
1. 读取 FAQ 中「数据库验证」标注的数据源和表，从 [references/db-queries.md](references/db-queries.md) 获取对应 SQL 模板
2. 按数据源选择规则确定实际数据源，按模板依次执行查询：
   ```bash
   python3 .claude/skills/issue-diagnosis/db/db_query.py --source <数据源> --sql "SELECT ..."
   ```
   - 首次运行会自动创建虚拟环境并安装依赖，无需手动操作
   - 不确定字段名时先执行 `--describe <table>` 确认
3. 将查询结果纳入最终诊断报告

**注意**：无法从 FAQ 找到对应 SQL 模板时，跳过此步骤，不猜测表名/字段。

---

## Step 2b：GitLab 源码定位（条件触发）

**触发条件**（同时满足）：
1. 日志分析结果中存在任意一组 `needKnowledgeQuery == true`（该字段由 log-analysis.md 的分析流程生成，表示该问题组需要进一步定位）
2. 该组至少一条日志的 `callChain` 不为空

**callChain 为空时直接跳过此步骤**，不尝试 GitLab 查询，直接进入 Step 3 输出结论。

参照 [references/gitlab-lookup.md](references/gitlab-lookup.md) 的定位策略，完成：
1. 从 callChain 识别**报错类**（最后一条 ERROR）、**调用者类**（其前一步）
2. 用 `fields.project` 动态查找 GitLab 仓库（最多 3 个类并行拉取）
3. 结合源码还原调用链，补充 `possibleCause`（加 `[源码]` 前缀）

---

## Step 3：综合输出

**重要**：最终回复中不暴露 Step 0/1/2 的执行过程，只输出结论。格式由"是否命中 FAQ"决定，与是否有 traceId 无关。

**情况 A：FAQ 命中**（无论是否有 traceId）

【FAQ 已知方案】
{faq_result}

（若有日志验证结果，追加：）
【日志验证】
TraceId: {traceId}，时间: {timestamp}
结论: {与FAQ吻合 / 发现新信息}

---

**情况 B：FAQ 未命中，纯日志+源码分析**

【问题诊断报告】
服务: {fields.project}，时间: {timestamp}

【根因分析】
{possibleCause}（含源码定位时加 [源码] 前缀）

【解决建议】
{suggestedSolution}

---

**情况 C：多个分组**

每组独立输出上述格式，最终拼接：

共发现 N 类问题：

【{groupName}】（N 条记录）
TraceId: xxx ...
{该组诊断报告}

回答简洁明了，不超过 300 字（多组时每组不超过 200 字）。
