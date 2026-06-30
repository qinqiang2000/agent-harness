---
name: issue-diagnosis-billing
description: >-
  开票/收票/影像业务的统一入口 skill，覆盖故障诊断、需求分析、代码变更三类场景。
  场景一（故障）：用户提供 traceId、报错信息、异常堆栈时，通过「日志分析 + 源码联合定位」给出根因结论。
  场景二（业务疑问）：用户描述业务问题但无错误线索时，从知识库检索答案并结合源码分析。
  场景三（需求/变更）：用户描述功能需求、配置变更、模型切换、接口升级等开发任务时，通过源码定位给出变更方案。
  适用场景：开票失败、红冲失败、收票异常、查验不通过、影像归档失败、OFD/PDF解析失败、鉴权失败、
  接口超时、连接失败、发票状态异常，以及功能需求、配置变更、模型切换、接口升级等标准版产品相关任务。
  所有标准版产品相关问题或任务，无论是故障排查还是需求变更，都必须使用此 Skill。
---

# 开票/收票/影像业务问题诊断

**全程禁止在任何输出中暴露执行步骤**：不得在任何时候（包括中间过程的文字输出）出现"Step 1"、"Step 2"等步骤标题。所有步骤静默执行，只在 Step 5 输出最终结论。

---

## ⚙️ 路径配置（每次执行第一步）

执行任何步骤前，先读取以下环境变量，确定实际路径：

```bash
echo $BILLING_CODE_BASE_DIR  # 代码根目录（本地已有代码 + clone 目标）
echo $GITLAB_BASE_URL         # GitLab 服务器地址
echo $GITLAB_TOKEN            # GitLab 访问 token（必须设置）
```

| 环境变量 | 用途 | 未设置时的默认值 |
|---|---|---|
| `BILLING_CODE_BASE_DIR` | 代码根目录，本地已有代码优先在此查找，clone 也放到此目录下 | `/Users/panda/Documents/work/project/input/` |
| `GITLAB_BASE_URL` | GitLab 服务器地址 | `http://123.207.158.7:5000/ai-agent/git` |
| `GITLAB_TOKEN` | GitLab 访问 token | （必须设置，否则 clone 失败） |

路径确定后，后续所有步骤中的 `{CODE_BASE}` 均替换为实际代码根目录路径。

---

## ⚠️ 全局查询规范（所有流程强制遵守）

- **参数构建、重试策略、时间范围**：严格按 [references/query-strategy.md](references/query-strategy.md) 执行
- **查询后处理、深度分析**：严格按 [references/log-analysis.md](references/log-analysis.md) 执行
- **所有查询默认设置 `filterSqlLog=false`**，确保返回结果包含实际执行的 SQL 语句
- **日志连接异常时重试一次**，重试时不修改查询参数
- **环境不得自行切换**：查询环境必须来自用户明确描述，未指定时默认"生产"；查不到日志时禁止自行尝试其他环境，必须通过 `AskUserQuestion` 让用户确认环境
- **重试上限强制执行**：累计查询次数超过初次 + 2 次重试后，必须立即停止并反问用户

---

## Step 1：解析输入，判断执行路径

从用户问题中提取：
- `traceId`：服务链路追踪字符串
- `keywords`：错误关键词、异常类名、错误码、报错文本
- `service`：用户提及的服务名（可选）
- `timeRange`：时间范围（可选）；用户只说"X月X日"未提年份时，**默认取当前年份**，禁止使用上一年
- `env`：环境信息，按以下规则识别：
  - 用户提到"生产"或未指明环境 → `生产`
  - 用户提到"测试"、"sit环境" → `测试`
  - 用户提到"演示"、"dev环境" → `演示`
  - 用户提到"at" / "AT环境" → `at`
  - 用户提到"星瀚沙箱" → `星瀚沙箱`
  - 用户提到"星瀚生产" → `星瀚生产`
- `invoiceNo` / `invoiceCode`：
  - 用户明确区分了发票代码和发票号码 → 直接使用
  - 用户只提供一串数字，长度为 **20位** → 数电发票，整串为 `invoiceNo`，无 `invoiceCode`
  - 用户只提供一串数字，长度**不足20位** → 税控发票，`invoiceNo` = 该串数字，`invoiceCode` 未知
  - 用户提供两串数字 → 税控发票，分别赋值

### 判断执行路径（关键分叉）

**路径 A — 有可查线索**（满足以下任意一条）：
- 用户提供了 `traceId`
- 用户提供了报错文本、异常信息、错误码等关键字

→ **直接进入 Step 3（日志查询）**，跳过 Step 2

**路径 B+ — 有业务标识符**（无 traceId/报错，但描述中包含以下任意一种可查询的业务标识符）：
- 报销单号：匹配 `BX-` 开头的字符串（如 `BX-2605-0478`）
- 工单号：匹配 `IWO` 开头的字符串
- 发票号：20位纯数字
- clientId：用户明确描述为"客户ID"、"clientId"、"租户"等

→ **先进入 Step 3（日志查询）**，用业务标识符作为关键词查询；查不到日志则降级到路径 B（知识库检索）

**路径 C — 需求/变更任务**（满足以下任意一条，且无报错/traceId）：
- 描述中包含"切换"、"升级"、"新增功能"、"改为"、"接入"、"迁移"、"替换"、"配置变更"等变更动作
- issue label 包含 Feature / Enhancement / Task
- 描述中明确说明了目标状态（如"将 X 改为 Y"、"新增 Z 功能"）

→ **直接进入 Step 2C（需求源码定位）**，跳过知识库检索和日志查询

**路径 B — 无可查线索**（无 traceId，也无任何报错/关键字，无业务标识符，仅描述业务疑问，且非需求/变更）：

→ **进入 Step 2（知识库检索）**

**输入为空**（既无线索，也无任何描述）→ 回复"请提供报错信息、traceId 或描述具体问题"，终止流程。

---

## Step 2：知识库检索 + 本地源码联合分析（仅路径 B 执行）

读取 [references/knowledge-base.md](references/knowledge-base.md)，用用户描述的关键词在「三、关键词 → 上下文映射」中做语义匹配。

### 匹配策略（按优先级）

1. 用户描述的关键词与映射条目标题完全匹配（如"合规校验"、"发票查验"）
2. 用户描述的业务场景与条目内容语义匹配（如"发票上传后查不到"→ 台账/fdelete 条目）
3. 用户提到的类名、接口名、表名与条目中的技术关键词匹配

### 命中后的处理

知识库命中后，**不直接输出**，必须进一步读本地源码验证和深化结论：

1. 从命中条目中提取涉及的服务名和核心类名
2. 根据 knowledge-base.md「一、项目地图」中的本地路径，用 Grep 在对应服务目录下搜索核心类：
   ```bash
   grep -r "class {ClassName}" {本地服务路径} --include="*.java" -l
   ```
3. Read 找到的源码文件，重点关注用户问题涉及的逻辑（缓存策略、判断条件、字段赋值等）
4. 若条目有「深入」指针，一并 Read 对应文档
5. 综合知识库描述 + 实际源码，进入 Step 5 输出结论

**本地源码路径规则**（统一查代码入口，Step 4 同样遵守）：

1. 从 service-repo-map.md 获取服务的 `repo-name`（即仓库名，如 `api-expense`）
2. **必须按以下固定顺序**用 `ls` 逐一检查本地路径，禁止自行推断路径：
   ```bash
   CODE_BASE="${BILLING_CODE_BASE_DIR:-/Users/panda/Documents/work/project/input}"
   ls "$CODE_BASE/input-project/standard/input/{repo-name}" 2>/dev/null && echo "EXISTS_STANDARD"
   ls "$CODE_BASE/input-project/refactor/{repo-name}" 2>/dev/null && echo "EXISTS_REFACTOR"
   ls "$CODE_BASE/{repo-name}" 2>/dev/null && echo "EXISTS_DIRECT"
   ```
3. **本地存在**（任意一条输出 `EXISTS_*`）→ 使用对应路径，执行 `git pull` 拉最新，**禁止 clone**
4. **本地均不存在** → 按 service-repo-map.md 找到 `project_id`，clone 到 `$CODE_BASE/{repo-name}`：
   ```bash
   LOCAL_DIR="${BILLING_CODE_BASE_DIR:-/Users/panda/Documents/work/project/input}/{repo-name}" && \
   GITLAB_BASE="${GITLAB_BASE_URL:-http://123.207.158.7:5000/ai-agent/git}" && \
   git clone "$(echo $GITLAB_BASE | sed 's|://|://token:'"$GITLAB_TOKEN"'@|')/{namespace/repo-name}.git" "$LOCAL_DIR"
   ```
5. clone 失败 → 跳过源码分析，直接凭已有信息给出结论

**可跳过源码直接输出的例外**（须同时满足）：
- 条目内容是纯配置/纯运维建议（如"重启服务"、"清缓存"），无需理解代码逻辑
- 本地不存在且 service-repo-map 未命中（无法获取代码）

**未命中知识库** → 用 `AskUserQuestion` 告知用户知识库中未找到相关答案，请求补充 traceId 或报错关键字，收到后转入路径 A 执行 Step 3

### 注意

- 开票、影像业务知识（knowledge-base.md 四、五节）暂为占位，未命中时直接提示用户补充线索
- 知识库不覆盖的场景，不要凭主观猜测给答案，诚实告知并引导用户提供可查的线索

---

## Step 2C：需求/变更源码定位（路径 C 执行）

**目标：通过知识库项目地图确定涉及服务，再通过源码找到需要改动的位置，给出变更方案，为 code-fix 提供充分上下文。**

### 2C.1 提取变更要素

从需求描述中提取：
- `targetFunction`：需要变更的功能名称（如"获取省市区"、"开票接口"）
- `changeType`：变更类型（配置变更 / 接口替换 / 模型切换 / 新增功能 / 逻辑调整）
- `targetValue`：变更目标值（如新的 URL、新的模型名、新的参数值）
- `service`：涉及的服务名（如用户已指明则直接使用，否则通过 2C.2 确定）

### 2C.2 读知识库确定涉及服务

读取 [references/knowledge-base.md](references/knowledge-base.md)，重点看：
- **一、项目地图**：各服务职责说明，用 `targetFunction` 关键词匹配找到涉及的服务名和本地路径
- **命中** → 确认 `service` 和本地代码路径，进入 2C.3
- **未命中** → 在本地代码目录全局 Grep `targetFunction` 关键词，确认涉及服务后进入 2C.3

### 2C.3 源码定位

按「本地源码路径规则」获取代码（同 Step 2），然后搜索：

```bash
grep -r "{targetFunction关键词}" {代码目录} --include="*.java" --include="*.yml" --include="*.yaml" -l
```

读取命中文件，定位需变更的具体行号、方法名、配置键名。

### 2C.4 输出变更方案

找到源码后，输出以下内容：

```
【结论类型】REQUIREMENT

【变更分析】
{变更目标一句话描述}

【定位】
- 源码：{ClassName}.java:{行号}，{当前逻辑描述}
- 配置：{配置文件}:{行号}，{当前配置键值}（如涉及配置变更）

【变更方案】
{具体可操作的改动说明，包括需修改的文件、行号、改法}
```

输出后**不自动触发 code-fix**，等待用户确认后续操作。

---

## Step 3：ELK 日志查询（路径 A 执行）

**直接调用 `mcp__elastic__searchTraceOrKeyWordsLog`**（禁止用任何工具搜索该工具名，直接使用），按全局查询规范构建参数。

查询返回后，严格按 [references/log-analysis.md](references/log-analysis.md) 中的「查询后处理」和「日志读取规则」执行，从返回日志的 `project` 字段提取服务名。

**查询结果处理：**

- **日志查不到**（重试后仍无结果）→ 用 `AskUserQuestion` 告知未找到相关日志，请求补充信息后重新执行本步骤：
  > 日志中未找到相关记录，请提供以下信息以便进一步排查：
  > 1. traceId 或准确的报错文本
  > 2. 问题发生的时间（精确到分钟）
  > 3. 涉及的服务名或接口名（如已知）

- **查到日志** → 完整分析所有日志条目，提取 `project`、错误信息、关键字段值，然后**无论日志是否有异常，统一进入 Step 4 结合源码分析**

  唯一例外——满足以下**全部**条件时，可跳过 Step 4 直接进入 Step 5：
  - 根因明确是**纯外部系统问题**：税局/第三方接口返回了明确错误码或错误描述
  - 日志中**无任何本地服务异常**（无 ERROR、无堆栈、无字段异常）
  - service-repo-map 未命中该 `project`（无法 clone 对应代码）

  三条必须同时满足，缺任何一条都进入 Step 4。

---

## Step 4：源码定位与日志联合分析

**目标：不只是找到报错行，而是结合日志中的实际数据，回答"是什么数据/条件导致走到这里"。**

### 4.1 获取源码

1. 读取 `references/service-repo-map.md`，用日志中的 `project` 精确匹配，获取 `project_id` 和 `repo-name`
2. **映射表未命中** → 跳过源码分析，仅凭日志给出结论，不猜测仓库路径
3. 映射表命中 → 按以下**固定顺序**获取代码（禁止跳步）：

   **第一步：检查本地是否存在（必须按此顺序逐一检查，不得跳过）**
   ```bash
   # 标准版收票路径（优先检查）
   ls ${BILLING_CODE_BASE_DIR:-/Users/panda/Documents/work/project/input}/input-project/standard/input/{repo-name} 2>/dev/null && echo "EXISTS_STANDARD"
   # 重构版路径
   ls ${BILLING_CODE_BASE_DIR:-/Users/panda/Documents/work/project/input}/input-project/refactor/{repo-name} 2>/dev/null && echo "EXISTS_REFACTOR"
   # 直接子目录（兜底）
   ls ${BILLING_CODE_BASE_DIR:-/Users/panda/Documents/work/project/input}/{repo-name} 2>/dev/null && echo "EXISTS_DIRECT"
   ```
   输出 `EXISTS_*` → 本地存在，使用对应路径，执行 `git pull` 拉最新代码，**禁止 clone**

   **第二步：本地均不存在时才 clone** → clone 到 `{CODE_BASE}/{repo-name}`

唯一例外——满足以下**全部**条件时，可跳过 Step 4 直接进入 Step 5：
- 根因明确是**纯外部系统问题**：税局/第三方接口返回了明确错误码或错误描述
- 日志中**无任何本地服务异常**（无 ERROR、无堆栈、无字段异常）
- service-repo-map 未命中该 `project`（无法获取代码）

三条必须同时满足，缺任何一条都必须读源码。

### 4.2 源码检索

在代码目录中搜索目标类（路径为 Step 4.1 确定的本地路径或 clone 目标路径）：

```bash
# 按类名搜索
grep -r "class {ClassName}" {代码目录} --include="*.java" -l

# 按方法名搜索
grep -r "{methodName}" {代码目录} --include="*.java" -l
```

优先级：**报错类（最后一条 ERROR/WARN）> 调用者类 > 入口类**

遇到无法理解的枚举值或状态码时，先查 [references/field-glossary.md](references/field-glossary.md)；未命中则查源码枚举定义，**禁止自行猜测**。

### 4.3 联合分析要求

找到源码后，必须回答以下四个问题，才算完成根因定位：

1. 报错行在做什么操作（如 substring、类型转换、空值访问）？
2. 这个操作依赖什么输入数据（方法参数、外部返回值、配置值）？
3. 结合日志中的实际数据，是哪个具体的输入值触发了异常？
4. 根因是调用方传了非预期数据，还是被调用方返回了非预期格式，还是代码本身缺少防御？

**只有回答了这四个问题，才能进入 Step 5 输出结论。**

---

## Step 5：综合输出

**⚠️ 输出约束：**
- 总字数不超过 500 字
- 没有证据的模块不输出
- 推测性结论必须标注「（推测）」并建议用户进一步验证
- 只输出结论，禁止出现任何步骤标题
- 结论中涉及的所有枚举值必须已查过 field-glossary.md 或源码确认含义

**⚠️ 脱敏规则（仅适用于最终输出，工具调用参数必须使用原始值）：**
- 凭证类字段：clientSecret、entryKey、appSecret、privateKey、password、token、secret → 脱敏
- 完整手机号 → 保留前3后4，中间用 `****` 替换
- 完整身份证号 → 保留前6后4
- 禁止在最终输出中包含完整 SQL 语句，改用自然语言描述

### 输出格式

```
【结论类型】{枚举值，见下表}

【根因分析】
{根因结论，一句话说清楚是什么问题、在哪里出的问题}

【证据】
- 日志：TraceId {traceId}，时间 {timestamp}，服务 {project}
  关键日志行：{直接支撑根因的日志内容}
- 源码：{ClassName}.java:{行号}，{关键逻辑描述}

【解决建议】
{具体可操作的建议}
```

**【结论类型】枚举值说明（必须从以下六个值中选一个，不得自造）：**

| 枚举值 | 适用场景 | 后续动作 |
|---|---|---|
| `CODE_BUG` | 代码逻辑缺陷：有异常堆栈/报错行/NPE/Feign未传参/枚举映射缺失等 | 自动触发 code-fix |
| `CONFIG_CHANGE` | 需修改配置项（Nacos/yml/数据库配置表），无代码改动 | 输出结论，等用户确认 |
| `REQUIREMENT` | 需求/变更任务（路径 C），需新增或调整功能 | 输出变更方案，等用户确认 |
| `BUSINESS_FAQ` | 业务疑问，知识库/源码给出解答，无需改动 | 输出结论，等用户确认 |
| `EXTERNAL_ISSUE` | 纯外部系统问题（税局/第三方返回错误），本地代码无异常 | 输出结论，等用户确认 |
| `NEED_MORE_INFO` | 信息不足，无法定论 | 反问用户补充 |

**判断 `CODE_BUG` 的严格标准（须同时满足）：**
- 有具体异常堆栈或明确的报错行（`源码: {ClassName}.java:{行号}`）
- 根因是代码逻辑缺陷（未判空、未传参、枚举映射缺失、逻辑错误等），而非配置/数据/外部系统问题

**只有满足 CODE_BUG 标准时**，才在输出结论后紧接着调用 `Skill("code-fix", "{服务名}:{根因一句话摘要}")`；其他类型一律不触发，等待用户确认。

### 确认请求

每次输出结论后，根据结论类型追加不同提示：

**CODE_BUG 类型**（已自动触发 code-fix，无需追加编码提示）：
> 以上分析是否帮助您解决了问题？请回复 1 解决  2 未解决。

**REQUIREMENT / CONFIG_CHANGE / BUSINESS_FAQ / EXTERNAL_ISSUE 类型**（方案已输出，等待用户确认）：
> 以上分析是否帮助您解决了问题？请回复 1 解决  2 未解决。
> 如需根据以上方案进行编码落地，请回复「编码」。

### 编码意图检测

当用户在多轮对话中回复以下任意内容时，视为编码意图：
- 「编码」、「按方案编码」、「帮我写代码」、「开始编码」、「落地」、「写代码」、「code」、「fix」、「修复」

检测到编码意图后，**必须立即调用** `Skill("code-fix", "{服务名}:{变更方案一句话摘要}")`，将当前完整的变更方案作为上下文传入，不得直接在对话中输出代码。
