---
name: issue-diagnosis
description: >-
  通用服务问题诊断与根因定位，通过「FAQ检索 → 日志分析 → 源码定位」三步流程给出根因结论。
  当用户提供报错信息、异常堆栈、traceId，或描述服务/接口异常时使用此 Skill。
  即使用户只是粘贴了一段错误日志、一个 traceId、或描述了某个接口异常，也应触发此 Skill。
  适用场景：报错排查、问题定位、根因分析、日志分析、异常排查、堆栈分析、服务异常、接口异常、
  登录失败、鉴权失败、token失效、验证码失败、参数校验失败、接口超时、服务超时、连接失败、限流等。
---

# 通用问题诊断

严格按以下步骤执行，不可跳步。

**⚠️ 全局脱敏规则（适用于整个流程的任意输出节点，包括 AskUserQuestion 的问题内容）**：最终回复中禁止出现以下内容：
- 外部供应商（航信、新时代、百旺等）的订单号、合同号、账号（如 `4DLW2D124`）
- 凭证类字段的具体值：clientSecret、entryKey、appSecret、privateKey、password、token（access_token/refresh_token）、secret
- 完整手机号（保留前3后4，中间用 `****` 替换，如 `138****5678`）
- 完整身份证号（保留前6后4）

**⚠️ 脱敏仅限最终回复**：日志查询、数据库查询等工具调用的参数中，必须使用原始值（如完整手机号、完整身份证号），不得使用脱敏后的值，否则将导致查询失败。

---

## Step 0：解析输入

从用户问题中提取：
- `traceId`：服务链路追踪字符串
- `keywords`：错误关键词、异常类名、错误码、报错文本
- `service`：用户提及的服务名（可选）
- `timeRange`：时间范围（可选，如"今天上午"、"2025-03-05 10:00"）
- `env`：环境信息，例如生产、测试、演示。用户没指明环境则默认为生产环境
- `erpSystem`：ERP 系统类型，从以下关键词识别：
  - `星瀚` / `星空旗舰版` / `天梯` / `monitor` → `xinghan`
  - `星空企业版` / `EAS` / `金税连接` → `eas`
  - `发票云公有云` / 未提及 ERP 系统 → `public`
- `taskType`：任务类型，从以下关键词识别：
  - 用户提到"进项发票采集任务"、"任务号"、"批次号"、"batchNo"、"任务状态"、"任务失败"、"任务处理中" → `invoice_collection`
- `batchNo`：任务批次号（当 `taskType=invoice_collection` 时提取）
- `invoiceNo` / `invoiceCode`：发票号码和发票代码，按以下规则识别：
  - 用户明确区分了发票代码和发票号码 → 直接使用
  - 用户只提供一串数字，长度为 **20位** → 数电发票，整串为 `invoiceNo`，无 `invoiceCode`
  - 用户只提供一串数字，长度**不足20位** → 税控发票号码，`invoiceNo` = 该串数字，`invoiceCode` 未知
  - 用户提供两串数字（如"代码 XXXX 号码 YYYY"）→ 税控发票，分别赋值

输入为空（无 traceId 也无关键词）→ 回复"请提供报错信息、traceId 或错误关键词"，终止流程。

**`taskType=invoice_collection`** → 在执行 Step 1 前，**必须**先按 [references/invoice-task-diagnosis.md](references/invoice-task-diagnosis.md) 完成进项任务专项诊断，完成后返回主流程 Step 1。

---

## Step 1：FAQ 快速检索

**第一步：判断涉及领域**，按关键词映射到对应 FAQ 文件（可多选，并行读取）：

| 领域 | 触发关键词 | 文件 |
|---|---|---|
| 开票 | 开票、开具、红冲、票种 | [kb/开票-faq.md](kb/开票-faq.md) |
| 收票 | 收票、查验、OFD、PDF、邮箱取票、邮箱绑定、合规校验、发票助手、台账、重构版、导入发票、重复报销、已被报销、发票已关联、个人发票、个人抬头、个人票、抬头不一致、税号不一致、查验不通过、红冲、作废、超期、跨年、未上传源文件、黑名单、敏感词、连号 | [kb/收票-faq.md](kb/收票-faq.md) |
| 鉴权登录 | 登录、鉴权、token、clientId、验证码、二维码 | [kb/鉴权登录-faq.md](kb/鉴权登录-faq.md) |
| 接口参数 | 参数、字段、格式、必填、校验、不合法 | [kb/接口参数-faq.md](kb/接口参数-faq.md) |
| 进项发票采集 | 进项、采集、下票、全量查询、表头、抵扣勾选、退税勾选、入账、海关缴款书、版式文件下载 | [kb/进项发票采集-faq.md](kb/进项发票采集-faq.md) |
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

按 [references/query-strategy.md](references/query-strategy.md) 构建参数，调用 `mcp__elastic__searchTraceOrKeyWordsLog`，从返回日志的 `fields.project` 字段获取服务名（供源码定位使用）。

**合规校验场景（Q5～Q14）无 traceId 时**：用户通常只提供发票号码，需先定位 traceId，详见 [references/log-analysis.md](references/log-analysis.md) 的「合规校验：通过发票号码定位 traceId」章节。找到含发票信息的日志后，提取该条日志的 traceId，再用 traceId 查完整链路。

查询返回后，若日志条数较多、无法直接分析，先用以下脚本将 tool result 文件转为 JSONL（每条日志占一行）再处理；日志条数少时直接读取即可：
```bash
python3 .claude/skills/issue-diagnosis/scripts/parse_logs.py \
  --input <tool_result_文件路径> \
  --output <tool_result_文件夹路径>/随机且唯一文件名.jsonl (文件名不能固定)
```

转换后按 [references/log-analysis.md](references/log-analysis.md) 的"查询后处理"规则决定是否扩展查询，再按"深度分析"规则分析日志内容。

日志连接异常时重试一次，重试时不要修改查询参数。

**所有查询默认设置 `filterSqlLog=false`**，确保返回结果包含实际执行的 SQL 语句，纳入后续分析。SQL 日志分析重点：实际执行的 SQL 语句、查询参数是否正确、是否存在全表扫描或缺少索引。若发现 SQL 层面问题，结论在【根因分析】中加 `[SQL]` 前缀。

**然后根据以下情况决定下一步**：

- **日志查不到**（重试后仍无结果）→ 用 `AskUserQuestion` 反问用户，告知未找到相关日志，请求更多信息（如 traceId、准确报错文本、发生时间），收到回答后重新执行本步骤
- **日志显示后端处理成功**（无异常、含"成功"字样），但与用户描述的问题不符 → 用 `AskUserQuestion` 反问用户，告知后端正常这一发现，询问具体操作路径/页面/筛选条件，等收到回答后再继续，不直接输出推测性原因
- **多次数据库查询结果矛盾**（如：按条件 A 查到记录，按条件 A+B 查不到）→ 对比两次查询的 WHERE 条件差异，找出导致结果不同的字段：
  - 若该字段值来自用户传参（如税号、发票代码等），用 `AskUserQuestion` 反问用户确认该参数是否正确，不得自行推断
  - 不得在未经数据库验证的情况下断言"该记录存在于数据库中"
- **日志含以下任意一项** → 执行 Step 3 源码定位，完成后再输出结论：
  - 异常类名（含 Exception、Error 等）
  - 具体类名+行号（如 `HoliTaxDownloadService.java:87`）
  - 字段值异常（某字段被置为 0/null/默认值，或处理前后值不一致）
  - 根因指向代码逻辑（字段映射、数据转换、赋值逻辑，枚举转化等）
- **日志无异常信号** → 直接进入 Step 4 输出结论

---

## Step 3：源码定位

按 [references/gitlab-lookup.md](references/gitlab-lookup.md) 执行源码定位。在源码定位完成之前，不输出任何诊断结论。

收票服务源码定位时，先查 [references/invoice-collection-context.md](references/invoice-collection-context.md) 中的调用链速查和错误码表，再定位目标类。

完成后进入 Step 4 输出结论。

---

## Step 4：数据库辅助查询

仅当 FAQ 命中且条目中标注「数据库验证」标签时执行，其余情况跳过。
**严禁**：根据日志信号自行推断表名或字段；自行探索数据库表结构（SHOW TABLES、INFORMATION_SCHEMA 等）；执行 FAQ 未指定的 SQL；日志查不到时用数据库查询替代日志分析。

**数据源选择规则**（参照 `db/db_config.json` 中各数据源的 `env` 和 `database` 字段）：
- 用户指明"测试环境" → 选 `env=test`；未指明或指明"生产环境" → 选 `env=prod`
- 开票/鉴权相关问题 → 选 `database=cms`
- 运营/订单相关问题 → 选 `database=eop`
- 收票合规校验相关问题（重复报销、个人发票等）→ 选 `prod-invoice`（生产）或 `test-invoice`（测试）

**执行步骤**：
1. 读取 FAQ 中「数据库验证」标注的数据源和表，从 [references/db-queries.md](references/db-queries.md) 获取对应 SQL 模板
2. 按数据源选择规则确定实际数据源，按模板依次执行查询：
   ```bash
   python3 .claude/skills/issue-diagnosis/db/db_query.py --source <数据源> --sql "SELECT ..."
   ```
   - 首次运行会自动创建虚拟环境并安装依赖，无需手动操作
   - 不确定字段名时先执行 `--describe <table>` 确认
3. 将查询结果纳入最终诊断报告

无法从 FAQ 找到对应 SQL 模板时，跳过此步骤。

---

## Step 5：综合输出

最终回复中不暴露 Step 0～4 的执行过程（不出现"Step 0"、"Step 1"等标题），只输出结论。格式由"是否命中 FAQ"决定，与是否有 traceId 无关。

**输出约束**：根因结论必须有明确的日志行或源码行作为证据支撑。若某个结论依赖推断而非直接证据，必须明确标注"（推测）"，并建议用户进一步验证，不得以确定性语气陈述未经验证的事实。

**解密辅助**：若日志中存在加密参数且解密有助于验证根因，可用 `AskUserQuestion` 询问用户："是否需要解密该参数以进一步验证？如需要，请提供加密算法（如 AES-128-ECB）和加密密钥。"收到用户确认和密钥后，用 Bash 执行解密并将结果纳入诊断报告。

---

**情况 A：FAQ 命中**（无论是否有 traceId）

【FAQ 已知方案】
{faq_result}

（若有日志验证结果，追加：）
【日志验证】
TraceId: {traceId}，时间: {timestamp}
结论: {与FAQ吻合 / 发现新信息}

（若有数据库查询结果，追加：）
【数据库验证】
{db_query_result}

---

**情况 B：FAQ 未命中，纯日志+源码分析**

【问题诊断报告】
服务: {fields.project}，时间: {timestamp}

【根因分析】
{possibleCause}（含源码定位时加 [源码] 前缀）

【解决建议】
{suggestedSolution}

---

**情况 C：日志显示后端正常，但与用户描述的问题不符**

先用 `AskUserQuestion` 反问用户，告知后端数据正常这一关键发现，再询问具体操作路径/页面/筛选条件等，收到回答后再输出结论。不在收到用户补充信息之前列出推测性原因。

示例格式：
后端日志显示数据已正常处理（{关键发现}），但您反映取不到数据。请问：
1. 您是在哪个页面/功能查看的？
2. 使用了哪些筛选条件？

---

**情况 D：日志查不到**

先用 `AskUserQuestion` 反问用户，告知未找到相关日志记录，请求补充信息。

示例格式：
日志中未找到相关记录。请提供以下信息以便进一步排查：
1. traceId 或准确的报错文本
2. 问题发生的时间（精确到分钟）
3. 涉及的服务名或接口名（如已知）

---

**情况 F：进项发票采集任务（taskType=invoice_collection）**

在情况 A 或 B 的基础上，在报告开头追加任务状态信息：

【任务状态】
批次号: {batchNo}，状态: {ftask_status_desc}
{ferr_desc}（若有错误描述）

回答简洁明了，不超过 500 字。
