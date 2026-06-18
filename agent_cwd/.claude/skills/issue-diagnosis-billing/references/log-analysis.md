# 日志查询与分析规则

## 查询后处理（收到查询结果后，分析前必须执行）

统计所有返回日志条目的 traceId，按以下规则处理：

- 返回结果恰好只有 1 条，且有 traceId 并且有报错信息 → 自动用该 traceId 再查一次，分析 traceId 查询结果
- 返回结果的日志 traceId 全部相同，且日志里有报错信息 → 自动用该 traceId 再查一次，分析 traceId 查询结果
- 返回结果存在多个不同 traceId 且最新一条日志有报错信息 → 用最新一条有报错的日志的 traceId 再查一次
- 返回结果只有 1 条，且无 traceId → 继续分析，在输出结论中注明"日志上下文有限，建议提供 traceId 以获取完整调用链"
- 返回结果很多条且 traceId 各不相同 → 直接分析，无需扩展查询

---

## 工具返回格式

`mcp__elastic__searchTraceOrKeyWordsLog` 返回原始日志列表，每条包含：
- `message`：日志内容
- `time`：时间
- `id`（即 traceId）
- `project`（服务名）
- `level`：日志级别（ERROR/WARN/INFO 等）

按时间倒序排序，查不到日志时返回空列表。

---

## 日志读取规则（日志内容过大时执行）

日志条数较多、无法直接分析时，先将 tool result 文件转为 JSONL（每条日志占一行）再处理；日志条数少时直接读取即可。转换命令：

```bash
python3 {SKILL目录}/scripts/parse_logs.py \
  --input <tool_result_文件路径> \
  --output <tool_result_文件夹路径>/<随机唯一文件名>.jsonl
```

转换完成后自行决定如何检索分析。关键搜索词参考：`timeout`、`超时`、`Exception`、`Error`、`500`、`401`、`403`、`NullPointer`、`连接失败`、`校验失败`

---

## 深度分析

**分析前必须做的事**：日志中每出现一次数据库查询（SELECT），必须找到对应的查询结果行数（通常紧跟在 SQL 之后，如 `Total: 0`、`查询结果: []`），明确记录"第N次查询返回X条"，再进行后续分析。

**日志含无法理解的枚举值或状态码**：出现形如 `xxxType=N`、`xxxStatus=N`、`errorCode=N`、`xxxSource=N` 的字段，先查 [field-glossary.md](field-glossary.md)，命中则直接理解继续分析；**未命中** → 进入源码定位查枚举定义，禁止自行猜测。

从返回的日志列表中，按 `time` 排序，优先关注 `level=ERROR` 条目，其次 `level=WARN`，逐条读取 `message`、`level`、`project`，提取关键信息：

| 关键词 | 需提取 |
|---|---|
| timeout / 超时 | 实际耗时、超时阈值、接口名 |
| 500 / Internal Error | HTTP 状态码、响应内容 |
| 401/403 / 鉴权失败 | 完整请求 URL（含所有查询参数名和值）、token 参数名、clientId、错误消息 |
| 参数校验 / 不合法 | 参数名、实际值、期望格式 |
| NullPointerException | 堆栈、出错类和方法 |
| 连接失败 | 连接目标、地址、错误详情 |
| 状态不一致 | 缓存状态、DB状态、税局状态、时间差 |
| 多次 SELECT 结果不一致 | 各次查询的 WHERE 条件差异、参数值、返回行数 |

---

## 开票/收票/影像场景：通过发票号码定位 traceId

用户反馈合规校验或收票问题时，通常只提供发票号码（invoiceNo），需先定位 traceId 再查完整链路。

### 搜索策略（按优先级）

**策略1：搜索合规校验结果**
- 数电发票（invoiceNo 为20位）：searchWordList = `["InvoiceVerifyService - 发票", "<invoiceNo>"]`
- 税控发票（有 invoiceCode）：searchWordList = `["InvoiceVerifyService - 发票", "<invoiceCode>", "<invoiceNo>"]`

**策略2：搜索合规校验入口**
- 数电发票：searchWordList = `["根据流水号校验发票", "<invoiceNo>"]`
- 税控发票：searchWordList = `["根据流水号校验发票", "<invoiceCode>", "<invoiceNo>"]`

**策略3：搜索合规管控入口**（策略1无结果时使用）
- searchWordList = `["合规管控配置", "<发票流水号或clientId>"]`

### 日志流转路径

```
api-fpzs（入口）
  → FpzsExpenseUploadController  "[uploadFileNew]查验结果"
  → FpzsExpenseImportController  "发票数据通用查询请求流水号"
  → FpzsExpenseImportService     "根据流水号校验发票"
      ↓ RPC 调用
api-expense（校验）
  → ExpenseVerifyController  "合规管控配置"
  → ExpenseVerifyService     "根据发票流水号数组查询发票信息"
```

### 影像场景关键搜索词

| 场景 | searchWordList |
|---|---|
| 影像归档失败 | `["归档失败", "<发票号码或业务单号>"]` |
| 扫描任务异常 | `["扫描任务", "<任务编号>"]` |
| 影像上传失败 | `["影像上传", "<clientId>"]` |
| OCR 识别失败 | `["OCR识别", "<文件名或发票号码>"]` |
