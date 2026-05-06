# 查询策略

## 参数构建规则

- 有 traceId → 仅传 `traceId` 字段，**禁止**将 traceId 放入 `searchWordList`，**禁止**同时传 `searchWordList`
  - traceId 查询返回结果后，必须先完整分析返回的所有日志条目，再决定下一步
  - **严禁**在未充分分析 traceId 查询结果的情况下发起扩展查询或关键词查询
  - traceId 查询返回空结果 → **立即停止，禁止改用关键词查询**，直接用 `AskUserQuestion` 反问用户："未找到 traceId `{traceId}` 对应的日志，请提供问题发生的准确时间（精确到分钟）及确认环境是否正确（生产/测试/演示）"，收到回答后重新查询 traceId
- 无 traceId → 仅传 `searchWordList` 关键词，不传 `traceId`
- **FAQ 命中且标注了「日志关键字」时（最高优先级）**：必须将 FAQ 中的关键字数组原样复制到 searchWordList，将 `<占位符>` 替换为用户提供的实际值，**严禁替换、增删或自行猜测关键词**。例：FAQ 写 `["发送邮件验证码sendVerifyCode param", "<邮箱地址>"]`，则 searchWordList 必须是 `["发送邮件验证码sendVerifyCode param", "qwe@163.com"]`，不得改为 `["sendVerifyCode", "邮箱绑定"]` 等变体
- **严禁自行添加 `projectList` 参数**：即使你能从上下文推断出服务名，也绝对不允许自行传 `projectList`。`projectList` 仅在 [invoice-task-log-keywords.md](invoice-task-log-keywords.md) 中明确指定时才可使用，其他所有场景一律不传
- **时间范围（必须传）**：每次查询都必须传 `startTime` 和 `endTime`，不得省略：
  - 用户提供了时间 → 理解并传入用户说的时间范围
  - 用户未提供时间 → 默认 `startTime` = 当前时间 - 7天，`endTime` = 当前时间
  - 查不到结果时 → 自动扩展到最近 30 天再查一次（更新 `startTime` = 当前时间 - 30天）

## 无 traceId 时的关键字引导流程

1. 读取 [elk-search-guide.md](elk-search-guide.md)，根据 `erpSystem` 选择对应分类（A/B/C），再根据问题场景匹配最合适的模板
2. 检查模板所需的"必需信息"是否已从用户输入中获取：
   - **已知** → 将信息填入模板关键字，构建 searchWordList 执行查询
   - **缺失** → 用 `AskUserQuestion` 反问用户，例如：
     - "请提供税号，以便查询短信验证码记录"
     - "请提供 bxd_key，以便查询报销单附件入库记录"
     - "请提供发票号码或流水号，以便定位开票请求"
   - 收到用户回答后，将信息填入模板，再执行查询
3. **B/C 类系统（`xinghan`/`eas`）且无 traceId**：优先引导用户去 ERP 系统获取 traceId：
   - `xinghan`：进入 ERP → 相关模块日志 → 找到对应记录 → 复制 traceId
   - `eas`：财务会计 → 发票管理 → 金税连接设置 → 请求日志 → 筛选"请求返回" → 复制 traceId
   - 若用户无法获取 traceId，则退回步骤 1 用关键字模板查询
4. 无法匹配任何场景模板 → 直接用 `keywords` 构建 searchWordList

## 查不到日志时的重试策略

最多重试 3 次，超过立即停止：

1. 检查 searchWordList 是否包含 2 个以上关键词 → 若是，保留最核心的 1 个词重新查询（**禁止**拆成多次查询）
2. 若仍查不到，截取核心词（去掉修饰词、保留异常类名/错误码/核心业务词）重新构建 searchWordList，再查一次
3. 仍查不到 → **立即停止查询**，用 `AskUserQuestion` 反问用户："日志中未找到相关记录，请提供更多信息（如 traceId、准确报错文本、发生时间）"，收到回答后重新执行 Step 3

**严禁**：
- 自行猜测同义词、英文翻译、缩写等变体反复查询
- 将完整关键词拆分成子串（如将 `DOWN-20260409-2453396293041523712` 拆成 `2453396293041523712`）单独查询
- 自行切换环境（如从"生产"切换到"星瀚生产"、"at"、"星瀚沙箱"等）——环境必须由用户明确指定，未指定时只查用户原始描述的环境
- 超过 3 次重试后继续发起任何新查询，无论换了什么关键词或环境
