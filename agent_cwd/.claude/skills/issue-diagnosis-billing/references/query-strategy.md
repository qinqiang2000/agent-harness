# 查询策略

## 参数构建规则

- 有 traceId → 仅传 `traceId` 字段，**禁止**将 traceId 放入 `searchWordList`，**禁止**同时传 `searchWordList`
  - traceId 查询返回结果后，必须先完整分析返回的所有日志条目，再决定下一步
  - **严禁**在未充分分析 traceId 查询结果的情况下发起扩展查询或关键词查询
  - traceId 查询返回空结果 → **立即停止，禁止改用关键词查询**，直接用 `AskUserQuestion` 反问用户："未找到 traceId `{traceId}` 对应的日志，请提供问题发生的准确时间（精确到分钟）及确认环境是否正确（生产/测试/演示）"，收到回答后重新查询 traceId
- 无 traceId → 仅传 `searchWordList` 关键词，不传 `traceId`
- **严禁自行添加 `projectList` 参数**：即使能从上下文推断出服务名，也绝对不允许自行传 `projectList`
- **时间范围（必须传）**：每次查询都必须传 `startTime` 和 `endTime`，不得省略：
  - 用户提供了时间 → 理解并传入用户说的时间范围
  - 用户未提供时间 → 默认 `startTime` = 当前时间 - 7天，`endTime` = 当前时间
  - 查不到结果时 → 自动扩展到最近 30 天再查一次（`startTime` = 当前时间 - 30天）

## 无 traceId 时的关键字引导流程

1. 根据问题场景匹配最合适的关键字模板，优先使用用户提供的唯一标识符（如发票号码、流水号、bxd_key 等）
2. 检查模板所需的"必需信息"是否已从用户输入中获取：
   - **已知** → 将信息填入模板关键字，构建 searchWordList 执行查询
   - **缺失** → 用 `AskUserQuestion` 反问用户，例如：
     - "请提供发票号码，以便查询开票记录"
     - "请提供 traceId 或准确报错文本，以便定位问题"
   - 收到用户回答后，将信息填入模板，再执行查询
3. **用户输入包含 URL 时**：如果有类似 userKey、riqId 等全局唯一的 query 参数，使用该唯一参数作为搜索词。
   例：用户输入 `https://api.example.com/expense/invoice/list?userKey=6e6ad24d331f4bf207a3ce385ccc11eb`
   → searchWordList 应为 `["6e6ad24d331f4bf207a3ce385ccc11eb"]`
4. 无法匹配任何场景模板 → 直接用 `keywords` 构建 searchWordList

## 查不到日志时的重试策略

最多重试 3 次，超过立即停止：

1. 检查 searchWordList 是否包含 2 个以上关键词 → 若是，保留最核心的 1 个词重新查询
2. 若仍查不到，截取核心词（去掉修饰词、保留异常类名/错误码/核心业务词）重新构建 searchWordList，再查一次
3. 仍查不到 → **立即停止查询**，用 `AskUserQuestion` 反问用户

**严禁**：
- 自行猜测同义词、英文翻译、缩写等变体反复查询
- 将完整关键词拆分成子串单独查询
- 自行切换环境（环境必须由用户明确指定，未指定时只查用户原始描述的环境）
- 超过 3 次重试后继续发起任何新查询
