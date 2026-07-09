---
name: issue-diagnosis-xinghan
description: >-
  星瀚发票云（imc-* 模块）问题定位专项流程。
  本文件由 issue-diagnosis Step 1 跳转调用，不独立触发。
  处理堆栈含 kd.imc.、imc-bdm、imc-sim、imc-invsm、imc-rim 或 erpSystem=xinghan 的问题。
---

# 星瀚问题定位专项流程

**⚠️ 本文件由 issue-diagnosis 的 Step 1 专项场景识别跳转调用，命中后由本流程完整处理并输出结论，主流程不再介入。**
**⚠️ 全程静默执行，只输出最终结论（格式与 issue-diagnosis Step 6 相同）。**
**⚠️ ELK 查询规范与脱敏规则与 issue-diagnosis 完全一致，此处不重复。**

---

## 流程概览

```
Step X0：星瀚 FAQ 快速检索（优先）
    ↓ 未命中或需要深入分析
Step X1：日志分析
    ├── deployMode=private + 用户无法提供日志/堆栈
    │       → 进入 Step X2（仅走路径 A：Product-Wiki）→ Step X4
    └── 其他情况
            ↓
        Step X2：源码定位（双路径：Product-Wiki + 预编译 Java 源码检索）
            ↓
        Step X3：飞书知识库检索（按需）
            ↓
        Step X4：综合输出
```

---

## Step X0：星瀚 FAQ 快速检索

**每次进入本流程，必须先执行本步骤。**

星瀚 FAQ 按模块拆分，均位于 `.claude/skills/issue-diagnosis/kb/` 目录，文件名以 `星瀚-` 为前缀：

| 关键词                                                  | FAQ 文件 |
|------------------------------------------------------|---------|
| 收票、识别、OCR、合规校验、上传发票、权限、全票池、导出、引入、批量打印、增值税勾选、抵扣勾选、成品油 | `星瀚-收票-faq.md` |
| 开票、开票申请单、红冲、导入、自动开票                                  | `星瀚-开票-faq.md` |
| 私有化、补丁、部署、mservice、archive、1011、元数据、字段、属性缺失          | `星瀚-部署运维-faq.md` |

按关键词定位对应文件后读取，匹配条目。

**命中后的处理规则**：

- **FAQ 有明确解决方案**（已知 bug、配置类、浏览器问题）→ 直接输出 FAQ 答案，跳过 Step X1/X2/X3，进入 Step X4
- **FAQ 含诊断步骤** → 记录核心判断条件，带入 Step X1 作为验证目标
- **未命中** → 继续执行 Step X1

---

## Step X1：日志分析

**输入处理**：
- 用户直接粘贴了堆栈或日志文本 → 从对话中提取，不查 ELK
- 用户提供 traceId 或关键词 → 调用 `mcp__elastic__searchTraceOrKeyWordsLog`，按全局查询规范构建参数

同时从用户描述中识别部署模式（供 Step X2 版本选择使用）：
- 用户提到「公有云」、「SaaS」、未提及私有化/本地部署 → `deployMode=saas`
- 用户提到「私有化」、「本地部署」、「自己部署」、「客户现场」 → `deployMode=private`
- 无法判断 → `deployMode=unknown`

**⚠️ `deployMode=private` 时的特殊处理（私有化环境无 ELK，日志查询无效）：**

用 `AskUserQuestion` 询问用户是否能提供日志或堆栈，然后按回答分支处理：

- **能提供日志文本或堆栈** → 用户粘贴后，直接从文本中提取信息，**跳过 ELK 查询**，继续后续步骤（Step X2 源码定位等）
- **无法提供日志或堆栈** → **跳过 Step X1 剩余部分**，直接进入 Step X2，但**仅执行路径 A（Product-Wiki 检索）**，跳过路径 B（源码 KB），在 Step X4 注明「私有化环境无日志，结论基于 Product-Wiki 文档分析，建议结合实际现象验证」

从日志/堆栈中重点提取：
- **异常类名**：如 `kd.imc.bdm.common.helper.BotpHelper`
- **方法名**：如 `calDiscountRowCombineAmt`
- **行号**：如 `BotpHelper.java:292`
- **关键字段值**：异常参数、状态码、枚举值

---

### ⚠️ 跨集群诊断：星瀚调用发票云接口

**识别条件**：日志 message 中含 `api.piaozone.com`（或 sit/演示环境域名），且来自 `HttpUtil.doPost` 或 `HttpUtil.doPostWithStatus` 等 HTTP 调用日志。

日志格式：
```
HttpUtil.doPost:{URL} 耗时：{ms}，结果：{发票云返回JSON}
```

**环境域名映射**：

| 域名 | 对应发票云 ELK 环境 |
|------|-------------------|
| `api.piaozone.com` | `生产` |
| `api-sit.piaozone.com` | `测试` |
| `api-dev.piaozone.com` | `演示` |

**处理步骤**：

1. 从 URL 提取关键参数：接口路径、`taxNo`、`reqid` 等
2. 从返回 JSON 提取：`traceId`（发票云侧）、`errcode`、`description`
3. 判断根因归属：
   - **发票云返回正常，但星瀚侧处理异常** → 根因在星瀚，继续走 Step X2 定位星瀚源码，无需深入发票云侧
   - **发票云返回错误**（errcode 非正常、description 含报错）→ 根因在发票云侧，执行第4步
4. 根因在发票云侧时，以提取到的参数为输入，**从 `issue-diagnosis` Step 2 开始执行**（跳过 Step 1 场景识别，直接进入 FAQ 检索），完整走完 Step 2→3→4→5→6 的发票云诊断流程：
   - 传入参数：发票云侧 `traceId`（优先）或 `taxNo` + 时间范围 + 接口路径（备用），环境按上方域名映射表确定
   - `issue-diagnosis` 后续新增的任何诊断步骤自动覆盖，无需在此同步
   - 发票云侧诊断结论返回后，与星瀚侧调用上下文（接口路径、errcode、taxNo）合并，进入 Step X4 输出，注明「跨集群调用，根因在发票云侧」

---

**决定是否进入 Step X2**：

进入 Step X2（出现任意一条即进入）：
- 含异常类名或堆栈（含 `at kd.imc.` 等）
- 字段值异常（某字段被置为 0/null 或前后不一致）
- 根因指向代码逻辑
- 出现无法理解的枚举值/状态码

跳过 Step X2，直接进入 Step X3（须同时满足）：
- 根因是纯外部系统问题（税局返回明确错误码，无本地异常）
- 根因是纯配置/数据问题（字段传错、证书过期等）

---

## Step X2：星瀚源码定位

先读取本目录下的 references/xinghan-jar-index.md 获取预编译 KB 路径、Wiki 路径、源码分析要点。

两条路径**并行判断**，根据输入情况选择执行策略：

| 输入情况 | 执行策略 |
|---------|---------|
| 堆栈含 `kd.imc.` 类名 | **B 为主**（定位 Java 源码）→ A 补充业务语义 |
| 仅有业务描述，无堆栈 | **A 为主**（从 Wiki 找类名）→ 用找到的类名走 B 确认 |
| Wiki 目录下无匹配文件（Glob 返回空） | 仅走 B |
| KB 未建（Glob 无结果） | 仅走 A，结论标注「（推测，未经源码确认）」 |
| 两路径均无结果 | 凭日志分析给出结论，标注「（推测）」 |

---

### 路径 A：Product-Wiki 检索（业务语义层）

**目的**：从已整理的文档快速获取调用链、关键类名、字段含义。

1. 按 `references/xinghan-jar-index.md` 中的「业务关键词 → Wiki 文件映射」定位文档
2. 若无命中，用 Glob 搜索：
   ```
   Glob(pattern="data/Product-Wiki/wiki/entities/*{关键词}*.md")
   Glob(pattern="data/Product-Wiki/raw/**/*{关键词}*.md")
   ```
3. 读取命中的实体文档，提取：
   - 入口类名（推单方式表格中的「入口类」列）
   - 调用链（如 BOTP 匹配步骤列表）
   - 关键 Helper/Strategy 类名
4. 若实体文档有「Raw 来源」指引，继续读取对应 raw 文档

**路径 A 产出**：目标类名列表，用于路径 B 源码确认。

---

### 路径 B：预编译 KB 检索（Java 源码层）

**目的**：在预先反编译好的 Java 源码中定位具体分支逻辑、越界/空指针根因。

**源码已预先反编译，禁止实时运行任何反编译命令。**

**步骤 1：确认版本**

用 Glob 列出已有的 KB 版本：
```
Glob(pattern="data/source/xinghan/*/index.md")
```

版本号格式为 `X.Y.Z`，数字越大越新。无任何版本时（KB 未建）→ 告知用户「源码 KB 尚未构建，请运行 `issue-diagnosis-xinghan/scripts/build_xinghan_kb.sh --from-patch <补丁包路径>` 生成后重试」，仅凭路径 A 和日志输出结论，标注「（推测，未经源码确认）」。

**版本选择规则**：

| 情况 | 行为 |
|------|------|
| 用户明确说了版本号（如"8.0.9"） | 直接使用该版本 |
| `deployMode=saas` 或 `deployMode=unknown` | 默认使用版本号最大的版本，不反问 |
| `deployMode=private` | 用 `AskUserQuestion` 反问：「您的星瀚版本号是？已有版本：{列出版本号}」 |
| 已用最大版本定位，但源码逻辑与用户描述的现象不符 | 用 `AskUserQuestion` 反问：「当前使用的是 {版本号} 版本源码，您的实际版本是否不同？」 |

**步骤 2：定位类文件**

用类名搜索（加 `class` 限定避免误匹配注释）：
```
Grep(pattern="class {ClassName}", path="data/source/xinghan/{版本号}/", glob="*.java")
```

**步骤 3：读取目标方法**

```
Grep(pattern="(public|private|protected).*{methodName}\(", path="{找到的.java文件路径}")
```
获取行号后截取（方法体通常 30-100 行，limit 设 120 足够）：
```
Read: {java文件路径} offset={方法起始行-2} limit=120
```

**Java 源码分析要点**（详见 `references/xinghan-jar-index.md`）：
- `collection.get(i - 1)` 模式：`i=0` 时越界，看 for 循环起始值
- 枚举 `getCode().equals(xxx)` 分支：直接读枚举常量名理解业务含义
- 跨类调用（静态 Helper）：找对应类的源文件继续读

---

## Step X3：飞书知识库检索（按需）

**触发条件**：Step X2 完成后，根因属于以下任一类型时执行：
- 配置错误（参数设置不当、规则未配置）
- 操作不当（用户侧流程问题）
- 功能限制（产品不支持某操作）
- 已知常见问题（有对应 FAQ）

**根因属于纯代码 bug（空指针/越界/枚举逻辑错误）且不涉及用户操作时，跳过本步骤。**

**执行步骤**：

1. 读取 `.claude/skills/customer-service-feishu/DIRECTORY_MAP.md`，获取飞书目录映射
2. 根据根因类型，从 DIRECTORY_MAP.md 中定位旗舰版（星瀚）相关目录：
   - 常见报错/已知问题 → `07｜常见问题与FAQ/旗舰版发票云/` 下对应 FAQ 文件
   - 功能操作说明 → `01 产品功能说明手册/` 下旗舰版子目录
   - 配置类 → `03｜测试环境配置/` 或 `05｜生产环境准备/`
   - 私有化运维 → `07｜常见问题与FAQ/私有化部署运维FAQ/`
   - 通道问题 → `07｜常见问题与FAQ/通道问题/`
3. 用根因关键词并行 Grep 1-2 个目标目录，命中后 Read 文件
4. 校验文档主题与根因一致（关键词命中 ≠ 意图命中），不一致直接丢弃
5. 无命中时静默跳过，不影响 Step X4 输出

**Step X3 产出**：操作建议文本片段 + 文档相对路径（用于 Step X4 来源标注）。

---

## Step X4：综合输出

输出格式与 issue-diagnosis Step 6 完全相同，证据块增加以下来源类型：

```
【根因分析】
{根因结论，一句话说清楚是什么问题、在哪里出的问题}

【证据】
- 日志：TraceId {traceId}，时间 {timestamp}，服务 {project}
  关键日志行：{直接支撑根因的日志内容}
- Wiki：{文档相对路径}，{关键描述}
- 源码：{ClassName}.java，方法 {methodName}（源码版本 {版本号}）
  关键逻辑：{用自然语言描述根因所在的代码逻辑，不输出代码块}

【解决建议】
{具体可操作的建议}
{若 Step X3 命中飞书文档，在建议末尾追加：参考操作手册：{文档相对路径}}
```

输出约束（同 issue-diagnosis Step 6）：
- 总字数不超过 500 字
- 没有证据的模块不输出
- 推测性结论标注「（推测）」
- 禁止输出完整 SQL 语句
- 禁止输出源码片段
- **源码证据必须标注版本号**，格式固定为 `（源码版本 {版本号}）`，不可省略
- 每次结论后追加确认请求：
  > 以上分析是否帮助您解决了问题？请回复 1 解决  2 未解决。

---

## 反馈学习

与 issue-diagnosis Step 7 完全相同：监听用户反馈，命中/否定时写入 `data/issue-diagnosis/instincts/cases.md`，格式不变。静默执行，不告知用户。
