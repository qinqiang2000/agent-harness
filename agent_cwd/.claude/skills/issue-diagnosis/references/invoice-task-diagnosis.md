# 进项发票采集任务专项诊断流程

当主流程识别到进项发票采集任务场景时执行本流程，由本流程完整处理并输出结论，主流程不再介入。

**⚠️ 本流程 ELK 查询全局约束（覆盖 query-strategy.md 通用规则）：**
- 所有查询只有两种合法形式：
  1. `searchWordList = [操作类型关键字, batchNo]`
  2. `traceId = 入口日志的 id 字段值`
- 用户未提供 batchNo 或 traceId 时，必须用 `AskUserQuestion` 反问用户提供，**禁止用税号、账号、类名、接口名等其他参数替代**
- 查不到结果时**禁止换词重试**，直接反问用户或进入下一步

---

## Task-Step 1：查询任务状态

### 1a. 查数据库

若有 `batchNo`，立即执行：

```bash
python3 .claude/skills/issue-diagnosis/db/db_query.py --source prod-invoice --sql "SELECT fbatch_no, ftask_status, ferr_desc, fcreate_time, fupdate_time FROM t_elc_sync_task WHERE fbatch_no = '{batchNo}'"
```

`ftask_status` 含义：
- 1=待处理，2=已入队列，3=处理中，4=处理完成
- 5=处理失败，6=处理失败待重试，7=部分成功，8=全部失败
- 9=未登录等待重试，-1=异常请求不入队列，-2=文件下载单独处理任务

`ferr_desc`：最新结果描述，失败时包含具体错误信息。

若无 `batchNo` → 用 `AskUserQuestion` 询问："请提供任务批次号（batchNo），以便查询任务状态。"

### 1b. 查日志关键字 `etaxbill callback params`

在 ELK 中搜索关键字 `etaxbill callback params` + `{batchNo}`，找到**最新一条**记录，即可获取任务处理结果。

日志示例：
```
# 成功示例
etaxbill callback params{"errcode":"0000","data":{"batchNo":"2041785801885925376","fileList":[{"resCount":486,"resFile":"https://..."}]},"description":"成功"}

# 失败示例
etaxbill callback params{"errcode":"3367","data":{"batchNo":"2041785801885925376"},"description":"登录超时，请重新登录"}
```

`errcode` 为 `"0000"` 表示成功，其他值表示失败，`description` 为具体原因。

**查不到回调日志时**：禁止更换关键词重试，直接进入 Task-Step 2。

---

## Task-Step 1 结论判断

- **任务处理成功**（`ftask_status=4` 或 `errcode="0000"`）→ 直接跳至 **Task-Step 4** 输出结论，**不再执行 Step 2/3**，除非用户追问中间处理细节。
- **任务处理未成功** → 继续执行 **Task-Step 2/3** 定位根因。

---

## Task-Step 2：匹配日志关键字

读取 [invoice-task-log-keywords.md](invoice-task-log-keywords.md)，根据用户描述的操作类型匹配对应关键字。

- 用户未提及操作类型 → **必须**用 `AskUserQuestion` 询问："请问是哪种操作的任务？（如：全量查询、抵扣勾选、版式文件下载、退税勾选、入账等）"，收到回答后再继续
- 能匹配到操作类型 → 按全局查询规范构建 `searchWordList`（关键字 + batchNo 或 taxNo），执行 ELK 查询
- 描述模糊无法匹配 → 同上，反问用户

---

## Task-Step 3：二次 traceId 查询与分析

查到入口日志后：
1. 提取该条日志的 `id`（即 traceId）
2. 用 traceId 再次调用 `mcp__elastic__searchTraceOrKeyWordsLog` 查完整调用链
3. 按全局查询规范的 log-analysis.md 规则分析完整链路，定位根因

---

## Task-Step 4：输出结论

在报告开头追加任务状态，再输出根因和建议。格式：

【任务状态】
批次号: {batchNo}，状态: {ftask_status 对应描述}
{ferr_desc}（若有错误描述）

【根因分析】
{possibleCause}（含源码定位时加 [源码] 前缀）

【解决建议】
{suggestedSolution}

回答简洁明了，不超过 500 字。
