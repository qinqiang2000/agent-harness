---
name: issue-diagnosis-external
description: >-
  面向外部客户的服务问题诊断与根因定位，通过「FAQ检索 → 日志分析 → 源码定位」三步流程给出根因结论。
  当用户提供报错信息、异常堆栈、traceId，或描述服务/接口异常时使用此 Skill。
  即使用户只是粘贴了一段错误日志、一个 traceId、或描述了某个接口异常，也应触发此 Skill。
  适用场景：报错排查、问题定位、根因分析、日志分析、异常排查、堆栈分析、服务异常、接口异常、
  登录失败、鉴权失败、token失效、验证码失败、参数校验失败、接口超时、服务超时、连接失败、限流等。
---

# 通用问题诊断（外部客户版）
**严格按照步骤要求执行**
**⚠️ 全程禁止在任何输出中暴露执行步骤**：不得在任何时候（包括中间过程的文字输出）出现"Step 1"、"Step 2"等步骤标题。所有步骤静默执行，只在 Step 6 输出最终结论。Step 7 在每次收到用户消息时静默判断，触发后直接写入 data/issue-diagnosis/instincts/cases.md，无需告知执行了哪个步骤。

---

## ⚠️ 全局查询规范（所有流程强制遵守）

**无论是主流程、FAQ 内嵌诊断步骤，还是专项流程，所有 ELK 日志查询和日志分析必须遵守以下规范：**

- **参数构建、重试策略、时间范围**：严格按 [../issue-diagnosis/references/query-strategy.md](../issue-diagnosis/references/query-strategy.md) 执行
- **查询后处理、深度分析**：严格按 [../issue-diagnosis/references/log-analysis.md](../issue-diagnosis/references/log-analysis.md) 执行
- **所有查询默认设置 `filterSqlLog=false`**，确保返回结果包含实际执行的 SQL 语句
- **日志连接异常时重试一次**，重试时不修改查询参数

FAQ 条目和专项流程只定义"查什么关键字、提取哪些字段"，不覆盖上述技术规范。

---

## Step 1：解析输入 + 场景识别

从用户问题中提取：
- `traceId`：服务链路追踪字符串
- `keywords`：错误关键词、异常类名、错误码、报错文本
- `service`：用户提及的服务名（可选）
- `timeRange`：时间范围（可选，如"今天上午"、"2025-03-05 10:00"）
- `env`：环境信息，按以下规则识别：
  - 用户提到"生产"或未指明环境 → `prod`
  - 用户提到"测试" → `test`
  - 用户提到"演示" → `demo`
  - 用户提到"at" / "AT环境" → `at`
- `erpSystem`：ERP 系统类型，从以下关键词识别：
  - `星瀚` / `星空旗舰版` / `天梯` / `monitor` → `xinghan`
  - `星空企业版` / `EAS` / `金税连接` → `eas`
  - `发票云公有云` / 未提及 ERP 系统 → `public`
- `invoiceNo` / `invoiceCode`：发票号码和发票代码，按以下规则识别：
  - 用户明确区分了发票代码和发票号码 → 直接使用
  - 用户只提供一串数字，长度为 **20位** → 数电发票，整串为 `invoiceNo`，无 `invoiceCode`
  - 用户只提供一串数字，长度**不足20位** → 税控发票号码，`invoiceNo` = 该串数字，`invoiceCode` 未知
  - 用户提供两串数字（如"代码 XXXX 号码 YYYY"）→ 税控发票，分别赋值

输入为空（无 traceId 也无关键词）→ 回复"请提供报错信息、traceId 或错误关键词"，终止流程。

**专项场景识别**（命中后立即跳转，由专项流程完整处理并输出结论，本主流程结束）：

| 场景 | 识别条件 | 跳转 |
|---|---|---|
| 进项发票采集任务 | 用户提到"进项发票采集任务"、"任务号"、"批次号"、"batchNo"、"任务状态"、"任务失败"、"任务处理中" | [../issue-diagnosis/references/invoice-task-diagnosis.md](../issue-diagnosis/references/invoice-task-diagnosis.md) |
| 接口代码查阅 | 用户询问某接口的处理流程、代码位置，或提到"接口"+"业务名称"（如"查验接口"、"开票接口"），且 `data/kb/接口文档/` 目录存在 | [../issue-diagnosis/references/api-lookup.md](../issue-diagnosis/references/api-lookup.md) |

未命中专项场景 → 继续 Step 1.5。

---

## Step 1.5：Instinct 检索

检查 `data/issue-diagnosis/instincts/cases.md` 是否存在。若存在，读取文件，用用户描述的关键词（报错类型、服务名、关键字段、错误码）与每条 case 的「适用条件」做语义匹配，跳过状态为 `rejected` 的 case。

记录命中的 case 编号，供 Step 6 和 Step 7 使用。按以下三档决定行为：

**档位 1：`match_confidence >= 0.6` 且 `answer_confidence >= 0.8`**
- 优先验证 case 结论：查日志确认关键字段/错误码是否与 case 描述吻合
- 验证通过 → 跳过 Step 2-4，直接进入 Step 6 输出，注明「参考历史经验 Case #XXX」
- 验证不通过 → 继续 Step 2 标准流程，不强行套用 case 结论

**档位 2：`match_confidence >= 0.6` 且 `answer_confidence < 0.8`**
- 仅作为诊断方向提示：优先查 case 中指向的服务、字段、Redis key 等
- 必须走完整 Step 2→Step 3→Step 4 流程验证
- Step 6 输出时注明「参考历史经验 Case #XXX（已验证）」

**档位 3：未命中（`match_confidence < 0.6`）或文件不存在**
- 继续 Step 2 标准流程，不参考任何 case

---

## Step 2：FAQ 快速检索

**第一步：判断涉及领域**，按关键词映射到对应 FAQ 文件（可多选，并行读取）：

| 领域 | 触发关键词 | 文件 |
|---|---|---|
| 开票 | 开票、开具、红冲、票种 | [../issue-diagnosis/kb/开票-faq.md](../issue-diagnosis/kb/开票-faq.md) |
| 收票 | 收票、查验、OFD、PDF、邮箱取票、邮箱绑定、合规校验、发票助手、台账、重构版、导入发票、重复报销、已被报销、发票已关联、个人发票、个人抬头、个人票、抬头不一致、税号不一致、查验不通过、红冲、作废、超期、跨年、未上传源文件、黑名单、敏感词、连号 | [../issue-diagnosis/kb/收票-faq.md](../issue-diagnosis/kb/收票-faq.md) |
| 鉴权登录 | 登录、鉴权、token、clientId、验证码、二维码 | [../issue-diagnosis/kb/鉴权登录-faq.md](../issue-diagnosis/kb/鉴权登录-faq.md) |
| 接口参数 | 参数、字段、格式、必填、校验、不合法 | [../issue-diagnosis/kb/接口参数-faq.md](../issue-diagnosis/kb/接口参数-faq.md) |
| 进项发票采集 | 进项、采集、下票、全量查询、表头、抵扣勾选、退税勾选、入账、海关缴款书、版式文件下载 | [../issue-diagnosis/kb/进项发票采集-faq.md](../issue-diagnosis/kb/进项发票采集-faq.md) |
| 性能超时 | 超时、timeout、慢、连接失败、积压 | [../issue-diagnosis/kb/性能超时-faq.md](../issue-diagnosis/kb/性能超时-faq.md) |

无法判断领域时 → 并行读取全部文件。

**第二步：在匹配的文件中检索**，优先级：
1. 完全匹配错误文本
2. 关键词命中「> 相似问题:」标签
3. 错误码/异常关键字部分匹配
4. 业务场景匹配

**命中 FAQ 后，根据条目类型决定下一步**：

- **条目含「诊断步骤」或「诊断流程见…」引用** → 完全按条目内的诊断步骤执行（技术规范仍遵守全局查询规范），**跳过 Step 3 和 Step 4**，直接进入 Step 5 数据库辅助查询（如有标注）或 Step 6 输出结论
- **条目不含「诊断步骤」，且有 traceId 或足够关键词** → 输出 FAQ 答案，继续 Step 3 日志验证
- **条目不含「诊断步骤」，且无法查日志**（无 traceId 且关键词过于模糊）→ 直接进入 Step 6 输出 FAQ 答案

**未命中 FAQ**：继续 Step 3。

---

## Step 3：ELK 日志查询与分析

**直接调用 `mcp__elastic__searchTraceOrKeyWordsLog`**（禁止用任何工具搜索该工具名，直接使用），按全局查询规范构建参数，从返回日志的 `project` 字段获取服务名（供源码定位使用）。

查询返回后，若日志条数较多、无法直接分析，先用以下脚本将 tool result 文件转为 JSONL 再处理；日志条数少时直接读取即可：
```bash
python3 .claude/skills/issue-diagnosis/scripts/parse_logs.py \
  --input <tool_result_文件路径> \
  --output <tool_result_文件夹路径>/随机且唯一文件名.jsonl
```

**然后根据以下情况决定下一步**：

- **日志查不到**（重试后仍无结果）→ 用 `AskUserQuestion` 反问用户，告知未找到相关日志，请求更多信息（如 traceId、准确报错文本、发生时间），收到回答后重新执行本步骤
- **日志显示后端处理成功**（无异常、含"成功"字样），但与用户描述的问题不符 → 用 `AskUserQuestion` 反问用户，告知后端正常这一发现，询问具体操作路径/页面/筛选条件，等收到回答后再继续，不直接输出推测性原因
- **多次数据库查询结果矛盾** → 对比两次查询的 WHERE 条件差异，找出导致结果不同的字段；若该字段值来自用户传参，用 `AskUserQuestion` 反问用户确认，不得自行推断

**日志分析完成后，按以下规则决定下一步：**
- **满足以下任意例外条件** → 跳过 Step 4，直接进入 Step 6：
  - 根因是纯外部系统问题：税局/第三方接口返回了明确错误码或错误描述，且日志中无本地服务异常
  - 根因是配置或数据问题：问题可完全归因于字段传错、租户未开通权限、证书过期等，无需了解代码逻辑即可确认
  - 建议仅涉及纯运维或数据修复操作（重启服务、清缓存、联系税局、更新数据库记录、补录配置），不涉及任何代码行为

- **不满足以上例外条件时，默认进入 Step 4 源码定位**，包括但不限于：
  - 日志含异常类名、堆栈信息（含 `at com.` 等）
  - 字段值异常（某字段被置为 0/null/默认值，或处理前后值不一致）
  - 根因指向代码逻辑（字段映射、数据转换、赋值逻辑、枚举转化等）
  - 日志有业务结果或拒绝描述（如"发票已作废"、状态流转记录），但不清楚为何走到该分支
  - **日志含无法理解的枚举值或状态码**：出现形如 `xxxType=N`、`xxxStatus=N`、`errorCode=N`、`xxxSource=N` 的数字型字段，先查 [../issue-diagnosis/references/field-glossary.md](../issue-diagnosis/references/field-glossary.md)，命中则直接理解继续分析；**未命中且该字段含义影响根因判断** → 进入 Step 4，禁止自行猜测

---

## Step 4：源码定位

**⚠️ 严禁在本地工作目录（agent_cwd）用 Grep/Glob 搜索源码。**

必须严格按 [../issue-diagnosis/references/gitlab-lookup.md](../issue-diagnosis/references/gitlab-lookup.md) 的顺序执行：
1. 读 `../issue-diagnosis/references/service-repo-map.md`，用日志中的 `project` 精确匹配，获取 `project_id`
2. 映射表未命中时，跳过源码分析，直接凭日志分析给出结论，不要妄自猜测
3. 获得 `project_id` 后，**必须使用 `../issue-diagnosis/references/gitlab-lookup.md` 中的 clone 模板**，原样替换 `{repo-name}` 和 `{namespace/repo-name}`，**禁止自行简化命令或省略 `token:$GITLAB_TOKEN@`**
4. 在本地 clone 目录用 Grep 搜索目标类

在源码定位完成之前，不输出任何诊断结论。

完成后进入 Step 6 输出结论。

---

## Step 5：数据库辅助查询

仅当 FAQ 命中且条目中标注「数据库验证」时执行，其余情况跳过。

**⚠️ SQL 安全约束（防止慢查询拖垮生产库）**：
- **禁止自行构造任何 SQL 语句**，包括但不限于：`LIKE '%xxx%'` 模糊匹配、查询无索引字段、无 WHERE 条件的全表扫描
- **只能使用 [../issue-diagnosis/references/db-queries.md](../issue-diagnosis/references/db-queries.md) 中的预定义模板**，原样替换占位符后执行
- **没有匹配模板时，直接跳过数据库查询进入 Step 6**，不得尝试自行编写 SQL

**其他严禁行为**：根据日志信号自行推断表名或字段；自行探索数据库表结构（SHOW TABLES、INFORMATION_SCHEMA 等）；日志查不到时用数据库查询替代日志分析；查询结果为空时自行扩展查询其他表、其他字段或其他数据源。**查完即止**。

**数据源选择规则**（参照 `../issue-diagnosis/db/db_config.json`）：
- 用户指明"测试环境" → 选 `env=test`；用户指明"at环境" → 选 `env=at`；未指明或指明"生产环境" → 选 `env=prod`
- 开票/鉴权相关问题 → 选 `database=cms`
- 运营/订单相关问题 → 选 `database=eop`
- 收票合规校验相关问题 → 选 `prod-invoice`（生产）或 `test-invoice`（测试）

**执行步骤**：
1. 读取 [../issue-diagnosis/references/db-queries.md](../issue-diagnosis/references/db-queries.md)，根据 FAQ 条目编号找到对应模板
2. 若无匹配模板 → 跳过，直接进入 Step 6
3. 将模板中的占位符替换为实际参数值后执行：
   ```bash
   python3 .claude/skills/issue-diagnosis/db/db_query.py --source <数据源> \
     --query '{"type":"template","sql":"SELECT ...","evidence":"<模板标题>"}'
   ```
4. 将查询结论纳入最终诊断报告

---

## Step 6：综合输出

**⚠️ 外部客户版输出限制（严格执行）**

以下内容**禁止出现在任何输出中**：
- traceId、timestamp 等系统追踪标识
- 日志原文、日志片段、日志字段值
- SQL 语句、数据库表名、字段名、查询结论（如"查询 t_xxx 表结果为..."）
- Java 类名、方法名、行号（如 `com.xxx.XxxService:123`）
- 内部服务名（如 `invoice-service`、`cms-gateway`）
- 内部 IP 地址、域名、端口

**⚠️ 脱敏规则（仅适用于最终输出，工具调用参数必须使用原始值）**：
- 外部供应商订单号、合同号、账号（如 `4DLW2D124`）→ 脱敏
- 凭证类字段值：clientSecret、entryKey、appSecret、privateKey、password、token、secret → 脱敏
- 完整手机号 → 保留前3后4，中间用 `****` 替换（如 `138****5678`）
- 完整身份证号 → 保留前6后4
- 税号（纳税人识别号）→ 保留前4后2，中间脱敏
- 发票号码 → 脱敏
- 发票代码 → 脱敏

**输出格式**（只输出有内容的模块）：

```
【问题原因】
{一句话说清楚是什么问题，用客户能理解的语言，不涉及内部系统细节}

【解决建议】
{具体可操作的步骤，面向客户操作，不涉及代码/数据库/服务器操作}

【需要您提供】
{仅当无法定位时，引导用户提供更多信息}
```

不超过 300 字。

### 确认请求

输出结论后追加：
> 以上分析是否帮助您解决了问题？请回复 1 解决  2 未解决。

### 输出原则

**有证据才下结论**：没有直接证据的推断必须标注「（推测）」并建议用户进一步验证。

**无法定位时反问**，不妄自猜测：

- **日志查不到** → 用 `AskUserQuestion` 反问：
  > 暂时未能找到相关记录。请提供以下信息以便进一步排查：
  > 1. 准确的报错文本或错误码
  > 2. 问题发生的时间（精确到分钟）
  > 3. 涉及的功能或操作步骤

- **日志显示后端正常，但与用户描述不符** → 用 `AskUserQuestion` 反问，告知后端正常这一发现，再询问操作路径/页面/筛选条件。

---

## Step 7：反馈监听与学习

输出 Step 6 结论后，保持监听用户反馈：

**触发学习的信号**：

| 信号类型 | 识别条件 | 操作 |
|---------|------------------------------------------------------------|------|
| 显式确认 | 用户回复「✓ 解决」、"对了"、"解决了"、"就是这个" | 若本次命中了 case X：`answer_confidence` +0.1（上限 0.95）；未命中则不写文件 |
| 显式否定 | 用户回复「✗ 未解决」、"不对"、"不是这个原因"、"你说错了"、"建议有问题"、"你漏了XXX"、"应该是XXX" | 若本次命中了 case X：`answer_confidence` -0.2，降至 0.1 以下则标记 `状态: rejected`；重新诊断后创建新 case |
| 隐式纠正 | 用户补充了与上一轮结论矛盾的新信息 | 重新诊断后创建新 case，不修改旧 case |

**创建新 case 的格式**（⚠️ 禁止写入任何用户数据）：

```markdown
## Case #XXX
- 触发场景: {问题类型描述，含关键词/报错类型/场景，不含具体用户值、traceId、clientId}
- 初次诊断: {第一次给出的错误方向，若无则填"（无）"}
- 正确路径: {正确根因和解决方向，不含 traceId、字段值、用户标识、IP、服务名}
- 适用条件: {下次匹配时用的关键词，如"报错含 'xxx' 且场景为 yyy"}
- match_confidence: {根据适用条件的具体程度评估，0.6-0.9}
- answer_confidence: {用户主动录入→0.9；显式纠正+完整路径→0.8；显式纠正+方向→0.5；隐式纠正→0.3}
- 状态: pending_review
- 创建时间: {YYYY-MM-DD}
```

**写入规则**：
- 新 case 追加到 `data/issue-diagnosis/instincts/cases.md` 末尾（文件不存在则创建）
- 更新旧 case 时，只修改 `answer_confidence`、`状态` 两个字段
- **严格禁止**：修改 FAQ 文件（`kb/` 目录）和 `SKILL.md`
- **严格禁止写入**：traceId、clientId、具体字段值、用户标识、IP 地址、内部服务名

写入完成后告知用户："已记录本次经验，感谢反馈。"
