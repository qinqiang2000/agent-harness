# 进项发票采集任务专项诊断流程

当 `taskType=invoice_collection` 时执行本流程。

---

## Task-Step 1：查询任务状态（数据库）

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

---

## Task-Step 2：匹配日志关键字

读取 [invoice-task-log-keywords.md](invoice-task-log-keywords.md)，根据用户描述的操作类型匹配对应关键字。

- 用户未提及操作类型 → **必须**用 `AskUserQuestion` 询问："请问是哪种操作的任务？（如：全量查询、抵扣勾选、版式文件下载、退税勾选、入账等）"，收到回答后再继续
- 能匹配到操作类型 → 构建 `searchWordList`（关键字 + batchNo 或 taxNo），执行 ELK 查询
- 描述模糊无法匹配 → 同上，反问用户

---

## Task-Step 3：二次 traceId 查询

查到入口日志后：
1. 提取该条日志的 `id`（即 traceId）
2. 用 traceId 再次调用 `mcp__elastic__searchTraceOrKeyWordsLog` 查完整调用链
3. 按 `log-analysis.md` 的规则分析完整链路，定位根因

完成后继续主流程 Step 1 FAQ 检索（补充已知方案）。
