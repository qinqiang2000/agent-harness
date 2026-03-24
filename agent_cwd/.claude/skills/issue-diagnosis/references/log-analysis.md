# 日志查询与分析规则

## 查询后处理（收到查询结果后，分析前必须执行）

统计所有返回日志条目的 traceId，按以下规则处理：

- 返回结果恰好只有 1 条，且有 traceId 并且有报错信息 → 自动用该 traceId 再查一次，直接分析 traceId 查询结果
- 返回结果的日志的 traceId 全部相同，且日志里有报错信息 → 自动用该 traceId 再查一次，直接分析 traceId 查询结果
- 返回结果的日志存在多个不同 traceId 且最新一条日志有报错信息 → 用最新一条有报错的日志的 traceId 再查一次，直接分析 traceId 查询结果
- 返回结果只有 1 条，且无 traceId → 继续分析，在输出结论中注明"日志上下文有限，建议提供 traceId 以获取完整调用链"
- 返回结果很多条且 traceId 各不相同 → 直接分析，无需扩展查询

---

## 查询策略

- **有 traceId** → 仅传 traceId，不传 searchWordList（精确定位）
- **无 traceId** → 仅用 searchWordList 关键词查询
- **searchWordList 是 AND 关系**：数组中每个元素必须同时出现在同一条日志中才会命中
  - 正确用法：只放最核心的 1-2 个词，避免过度限制
  - 错误用法：把多个不相关关键词都塞进数组（会导致查不到结果）
  - 如需 OR 效果：分多次调用，每次传不同关键词组合，合并结果

## 工具返回格式

`mcp__elastic__searchTraceOrKeyWordsLog` 返回原始日志列表，每条包含：
- `message`：日志内容
- `time`：时间
- `id`（即 traceId）
- `fields.project`（即 project/服务名）
- `level`：日志级别（ERROR/WARN/INFO 等）
按时间生序排序
查不到日志时返回空列表。

---

## 日志读取规则（日志内容过大时执行）

工具返回的日志按时间升序排列，报错通常集中在末尾。

**日志条数较多、无法直接分析时，先将 tool result 文件转为 JSONL（每条日志占一行）再处理**；日志条数少时直接读取即可。转换命令：

```bash
python3 .claude/skills/issue-diagnosis/scripts/parse_logs.py \
  --input <tool_result_文件路径> \
  --output /tmp/issue_logs.jsonl
```

转换完成后，自行决定如何检索分析。关键搜索词参考：`timeout`、`超时`、`Exception`、`Error`、`500`、`401`、`403`、`NullPointer`、`连接失败`、`校验失败`

---

## 深度分析（直接基于原始日志）

**分析前必须做的事**：日志中每出现一次数据库查询（SELECT），必须找到对应的查询结果行数（通常紧跟在 SQL 之后，如 `Total: 0`、`查询结果: []`、返回空列表等），明确记录"第N次查询返回X条"，再进行后续分析。不得在未确认返回行数的情况下对查询结果下结论。

从返回的日志列表中，按 `time` 排序，优先关注 `level=ERROR` 条目，其次 `level=WARN`，逐条读取 `message`、`level`、`fields.project`，提取关键信息：

| 关键词 | 需提取 | 示例 |
|---|---|---|
| 税局登陆超时| 超时，短信，登陆，失败 | 获取短信验证码失败 |
| timeout / 超时 | 实际耗时、超时阈值、接口名 | 调用XX接口耗时5.2s，超过3s阈值 |
| 500 / Internal Error | HTTP 状态码、响应内容 | 接口返回500，响应：'数据库连接失败' |
| 401/403 / 鉴权失败 | clientId、token、错误消息 | clientId为空，实际值：'null' |
| 参数校验 / 不合法 | 参数名、实际值、期望格式 | 字段值含空格导致校验失败 |
| NullPointerException | 堆栈、出错类和方法 | Service.process()中对象为null |
| 连接失败 | 连接目标、地址、错误详情 | 连接Redis失败，地址127.0.0.1:6379 |
| 缓存 key 不匹配 | 带下标 key、不带下标 key、tableIndex | checkData:261420000001211879265 vs checkData:26142000000121187926 |
| 状态不一致 | 缓存状态、DB状态、税局状态、时间差 | 缓存返回正常，税局已红冲，时间差9分钟 |
| RepeatImpl / verifyBySerialNo | fserial_no（发票流水号）、fexpense_num（报销单号）、fclient_id | 重复报销校验，提取流水号后查 t_bill_expense_relation |
| PersonInvoiceImpl / isPersonInvoice | buyerName（购方名称）、buyerTaxNo（购方税号）、invoiceType（票种） | 个人发票判断，提取字段后逐条核查判断条件 |
| 校验购方抬头--不通过 | buyerName（票面购方名称）、ghfmc（企业配置名称）、buyerTaxNo | 购方抬头不一致 |
| 校验购方税号--不通过 | buyerTaxNo（发票税号）、taxNo（企业税号）、ghfmc | 购方税号不一致 |
| errKey: / checkDescription: | errKey（错误码）、checkDescription（错误描述） | 查验不通过，说明具体错误码和描述 |
| 覆写后的合规性校验 config（errorLevel=7/8/26/27） | invoiceStatus（从 verifyResult 提取）| 红冲/作废状态，根据 errorLevel 确认类型 |
| 覆写后的合规性校验 config（errorLevel=14/15） | invoiceDate（开票日期）、twoYearMon、expenseDeadline | 超过报销期限，计算超出天数 |
| 标记新逻辑，非原件 state / 标记旧逻辑，非原件 | state（originalState）、serialNo、fileType | 电子发票未上传源文件 |
| 销方名称黑名单发票校验- | salerName | 销方名称黑名单 |
| 校验敏感词--不通过 | filterKey（匹配的敏感词）、goodsName | 发票明细敏感词 |
| 校验销方黑名单 | salerTaxNo | 税局违法纳税人 |
| 校验票种[ / 同批次连号情况： / 发票连号[ | invoiceNo、invoiceCode、invoiceType、连号范围列表 | 发票连号，说明哪两张发票构成连号 |
| 多次 SELECT 结果不一致（一次有结果、一次无结果） | 各次查询的 WHERE 条件差异、参数值、返回行数 | 第一次按 serialNum 查到1条，第二次按 invoiceCode+invoiceNo+taxNo 查到0条 → 对比两次 WHERE 条件，定位导致差异的字段，判断该字段值是否来自用户传参 |

---

## 合规校验：通过发票号码定位 traceId

用户反馈合规校验问题时，通常只提供发票号码（invoiceNo）或发票代码+号码，而非 traceId。需先通过以下策略定位 traceId，再查完整链路。

### 搜索策略（按优先级）

**策略1：搜索合规校验结果**（最精准，必须同时传至少两个词）
- 数电发票（invoiceNo 为20位，无 invoiceCode）：searchWordList：`["InvoiceVerifyService - 发票", "<invoiceNo>"]`
- 税控发票（有 invoiceCode）：searchWordList：`["InvoiceVerifyService - 发票", "<invoiceCode>","<invoiceNo>"]`
- 出现位置：`api-expense` 服务

**策略2：搜索合规校验入口**（必须同时传至少两个词）
- 数电发票（invoiceNo 为20位，无 invoiceCode）：searchWordList：`["根据流水号校验发票", "<invoiceNo>"]`
- 税控发票（有 invoiceCode）：searchWordList：`["根据流水号校验发票", "<invoiceCode>","<invoiceNo>"]`
- 出现位置：`api-fpzs` 服务

**策略3：搜索合规管控入口**（策略1无结果时使用，必须同时传两个词）
- searchWordList：`["合规管控配置", "<发票流水号或clientId>"]`（两个词必须同时出现）
- 出现位置：`api-expense` 服务

### 日志流转路径

```
api-fpzs（入口）
  → FpzsExpenseUploadController:321  "[uploadFileNew]查验结果" (含 invoiceCode+invoiceNo)
  → FpzsExpenseImportController:443  "发票数据通用查询请求流水号" (含 serialNos)
  → FpzsExpenseImportService:122/752/959  "根据流水号校验发票" (含 serialNoList)
      ↓ RPC 调用
api-expense（校验）
  → ExpenseVerifyController:191  "合规管控配置" (含 serialNoList)
  → ExpenseVerifyService:387/389  "根据发票流水号数组查询发票信息" (含 serialNo+invoiceNo)
```

### 关键字段说明

| 字段名 | 含义 | 备注 |
|--------|------|------|
| `serialNo` / `fplsh` | 发票流水号 | 合规校验的核心标识 |
| `invoiceNo` / `fphm` | 发票号码 | 用户通常提供此字段 |
| `invoiceCode` / `fpdm` | 发票代码 | 配合发票号码唯一定位 |
| `expenseId` | 报销单ID | 关联报销单 |
| `clientId` | 企业/租户ID | 区分企业 |

成功场景（日志无异常、含"成功"等字样）：直接说明操作正常完成，无需处理。

多条日志存在不同问题时，在分析结论中自然描述各个问题，无需强制分组。
