---
name: ontology-update
description: >
  五步 PRD 工作流的第 ③ 步 · 本体更新 Gate。
  基于 ② 单个特性映射报告的覆盖度评估（⬜ 缺失项 + 📝 建议调整项），
  通过本体访问服务检查最新本体是否已补齐缺失项。
  已补齐则放行，未补齐则暂停等待人工介入。
  本 skill 不修改本体，只做 gate 检查。
  每次调用处理一个特性，输出一份检查报告，批量循环由编排层负责。
argument-hint: "<特性ID> <output-path> [--force-pass]"
disable-model-invocation: true
allowed-tools: Bash, Read, Write, Glob, Grep
effort: max
depends-on:
  - skill: 02-ontology-context
    required: true
    condition: "exit-status=DONE_WITH_GAPS OR bug-ontology-result in [PARTIAL, MISS]"
consumes:
  - pattern: "{id}_特性清单.md"
    from: 02-ontology-context
    fields: [coverage-summary, ⬜缺失项清单]
    condition: "完整模式"
  - pattern: "{特性ID}_本体映射报告.md"
    from: 02-ontology-context
    fields: [覆盖度评估]
    condition: "完整模式"
  - pattern: "{id}_本体映射摘要.md"
    from: 02-ontology-context
    fields: [bug-ontology-result]
    condition: "lite模式"
requires-service:
  - name: ontology-access
    type: MCP | script
    description: >
      本体文件读取服务，由技术侧统一提供。
      skill 通过此服务获取最新本体文件内容，不关心底层实现（MCP/API/本地缓存）。
      需支持：按对象名+文件类型获取本体文件内容。
produces:
  - pattern: "{特性ID}_本体检查报告.md"
    fields:
      - coverage-rate   # 整数 0-100，floor(passed/checked*100)
      - coverage-tier   # HIGH(>=80) | MID(60-79) | LOW(<60)
---

# 本体更新 Gate

## 定位

产品工作流第 3 步。不修改本体，只做 gate 检查：② 标记的 ⬜ 缺失项是否已在最新本体中补齐。每次调用处理一个特性。

```
产品工作流
═══════════════════════════════════════════════════════════
  ① 需求分析 → ② 本体查询与映射 → ③ 本体更新 Gate → ④ 页面设计 → ⑤ PRD 生成
                                     （本 skill）

  准入条件（完整模式）：② exit-status = DONE_WITH_GAPS
  准入条件（lite 模式）：② bug-ontology-result in [PARTIAL, MISS]
  跳过条件（完整模式）：② exit-status = DONE（无缺失项，直接进 ④/⑤）
  跳过条件（lite 模式）：② bug-ontology-result = HIT（本体已有定义，直接进 ⑤）
```

**职责边界：**
- **做什么**：读取 ② 缺失项清单 → 通过本体访问服务获取最新本体 → 逐项比对 → 输出检查报告 → 决定放行/暂停
- **不做什么**：不修改本体文件、不管理认证凭据、不生成本体内容、不替代人工审核

## 本体访问方式

本 skill 通过技术侧统一提供的本体访问服务获取本体文件，不直接调用任何外部 API 或管理认证凭据。

具体调用方式由技术侧决定（MCP server / CLI script / 其他），skill 只声明需要的能力：

| 能力 | 说明 |
|------|------|
| `get-ontology-file` | 按对象缩写 + 文件类型获取最新本体文件内容 |
| `check-file-exists` | 检查指定本体文件是否存在 |
| `search-in-file` | 在本体文件中搜索关键标识（属性名/动作ID/函数ID/规则ID） |

> 技术侧实现参考：可通过 MCP server 封装 GitHub API / 本地 clone / CDN 缓存等，
> 对 skill 层透明。认证、token 管理、缓存策略均由服务侧负责。

## 输入参数

| 参数 | 必填 | 说明 |
|------|------|------|
| `$0` | 是 | 当前特性 ID（如 F-I-D04） |
| `$1` | 是 | 输出路径（与 ①② 相同） |
| `--force-pass` | 否 | 强制放行（跳过检查，PRD 中标注待补充） |

## 执行流程

### 阶段 0 · 准入校验

1. 在 `{output-path}/` 下定位 ② 的产物，判断模式：
   - 找到 `{id}_本体映射摘要.md` → **lite 模式**，读取 `bug-ontology-result`
   - 找到 `{id}_特性清单.md` → **完整模式**，读取 `skill-exit-status`
   - 两者都找不到 → exit-status: `BLOCKED`，提示先执行 ②

2. **完整模式准入判断：**
   - `DONE` → 无缺失项，本 skill 无需执行，exit-status: `DONE`，终止
   - `DONE_WITH_GAPS` → 进入阶段 1
   - 缺失 → exit-status: `BLOCKED`，提示先执行 ②

3. **lite 模式准入判断：**
   - `bug-ontology-result: HIT` → 本体已有定义，本 skill 无需执行，exit-status: `DONE`，终止
   - `bug-ontology-result: PARTIAL` → 进入阶段 1（仅检查缺口部分）
   - `bug-ontology-result: MISS` → 进入阶段 1（全量缺失检查）
   - 缺失 → exit-status: `BLOCKED`，提示先执行 ②

4. 读取 `coverage-summary` 中的 `checked`、`passed`、`missing` 数量（完整模式）
5. 计算 `coverage-rate = floor(passed / checked * 100)`，`checked=0` 时视为 100
6. 判定 `coverage-tier`：`>= 80` → HIGH / `60-79` → MID / `< 60` → LOW
7. 将 `coverage-rate` 和 `coverage-tier` 写入本 skill 产物头部

### 阶段 1 · 提取缺失项清单

1. 读取 特性清单 中的覆盖度汇总，提取所有 ⬜ 标记项
2. 读取各动作映射报告，提取逐项 ⬜ 缺失的具体内容：
   - 缺失的 Property（属性）
   - 缺失的 ActionType（动作）
   - 缺失的 Function（函数）
   - 缺失的 Rule（规则）
   - 缺失的 ValueSet（状态）
   - 缺失的 LinkType（链接）
3. 汇总为结构化缺失项清单：

| # | 对象 | 缺失类型 | 缺失路径 | 期望内容 | 对应本体文件 |
|---|------|---------|---------|---------|-----------|
| 1 | invoice-data | Property | invd_01_Properties.md | [描述] | {abbr}_01_Properties.md |

### 阶段 2 · 获取最新本体并比对

通过本体访问服务，对缺失项清单中涉及的每个本体文件：

1. 调用 `get-ontology-file`，获取最新版本内容
2. 调用 `search-in-file`，逐项搜索缺失项的关键标识：
   - 找到 → 标记 ✅ 已补齐
   - 未找到 → 标记 ⬜ 仍缺失
3. 对 📝 建议调整项，检查本体中对应定义是否已变更（可选，不阻断）
4. 若本体访问服务不可用 → exit-status: `BLOCKED`，提示检查服务配置

### 阶段 3 · 输出检查报告

**⚠️ 文件命名强制约束（不可违反）：**
输出文件名必须为 `{output-path}/{特性ID}_本体检查报告.md`，禁止使用 `check-report.md`、`ontology-check.md` 等其他名称。

**⚠️ 产物数量强制约束（不可违反）：**
单次执行单份产出。本 skill 每次调用只写入 1 个文件：`{特性ID}_本体检查报告.md`，禁止创建任何其他文件。

写入 `{output-path}/{特性ID}_本体检查报告.md`：

```markdown
---
lane: {透传}
priority: {透传}
skill-exit-status: DONE | DONE_PARTIAL | NEEDS_HUMAN | BLOCKED
skill-exit-detail: {说明}
gaps-remaining: {n}
coverage-rate: {n}
coverage-tier: HIGH | MID | LOW
check-date: {ISO日期}
---

# {特性ID} 本体检查报告

## 检查摘要

| 指标 | 数量 |
|------|------|
| ② 标记缺失项总数 | {n} |
| 已补齐（✅） | {n} |
| 仍缺失（⬜） | {n} |
| 建议调整项（📝） | {n} |

## 逐项检查结果

| # | 对象 | 缺失类型 | 缺失路径 | 检查结果 | 说明 |
|---|------|---------|---------|---------|------|
| 1 | ... | ... | ... | ✅ 已补齐 / ⬜ 仍缺失 | ... |

## 建议调整项检查（参考，不阻断）

| # | 对象 | 调整路径 | 当前定义 | 建议调整 | 是否已变更 |
|---|------|---------|---------|---------|----------|
| 1 | ... | ... | ... | ... | 是/否 |
```

### 阶段 4 · 路由决策

基于 `coverage-tier` 和 `gaps-remaining` 三档分支：

| coverage-tier | gaps-remaining | exit-status | 编排器行为 |
|--------------|---------------|-------------|----------|
| HIGH（>= 80%） | 0 | `DONE` | 放行，继续 ④/⑤ |
| HIGH（>= 80%） | > 0 | `NEEDS_HUMAN` | 暂停，HIGH 档文案，提供 [a][b][c] |
| MID（60-79%） | 任意 | `NEEDS_HUMAN` | 暂停，MID 档文案，提供 [a][b][c] |
| LOW（< 60%） | 任意 | `NEEDS_HUMAN` | 强制阻断，LOW 档文案，仅提供 [a][c] |
| 任意 + `--force-pass` | 任意 | `DONE_PARTIAL` | 强制放行，PRD 6.4 节标注待补充 |
| 本体访问服务不可用 | — | `BLOCKED` | 暂停，提示检查服务配置 |
| ② 产物缺失 | — | `BLOCKED` | 暂停，提示先执行 ② |

**HIGH 档（coverage-rate >= 80%，gaps-remaining > 0）向用户报告：**

```
③ Gate 检查完成。
· 本体覆盖度：{n}%（HIGH ✅）· 仍缺失项：{gaps-remaining} 项

以下本体缺失项尚未补齐：
  ⬜ {对象}.{缺失类型}: {缺失路径} — {期望内容}
  ⬜ ...

覆盖度已达 80% 以上，可以继续，缺失项将在 PRD 6.4 节标注。

请选择：
  [a] 人工补齐后重新检查（我会等待你的指令后重新执行 ③）
  [b] 继续生成 PRD（PRD 6.4 节将标注 {gaps-remaining} 项待补充）
  [c] 终止工作流
```

**MID 档（60% <= coverage-rate < 80%）向用户报告：**

```
③ Gate 检查完成。
· 本体覆盖度：{n}%（MID ⚠️）· 仍缺失项：{gaps-remaining} 项

以下本体缺失项尚未补齐：
  ⬜ {对象}.{缺失类型}: {缺失路径} — {期望内容}
  ⬜ ...

覆盖度在 60%-80% 之间，允许继续，但 PRD 和原型中将标注待补充内容，
建议事后补充本体后重新生成。

请选择：
  [a] 人工补齐后重新检查（我会等待你的指令后重新执行 ③）
  [b] 继续生成 PRD（PRD/原型将标注 {gaps-remaining} 项待补充，建议事后补本体）
  [c] 终止工作流
```

**LOW 档（coverage-rate < 60%）向用户报告（强制阻断，无 [b] 选项）：**

```
③ Gate 检查完成。
· 本体覆盖度：{n}%（LOW ❌）· 仍缺失项：{gaps-remaining} 项

覆盖度低于 60%，无法继续生成 PRD 和原型。
本体基础不足时生成的 PRD 可靠性极低，强制阻断以避免产出无效文档。

必须先补充以下本体缺失项，使覆盖度达到 60% 以上：
  ⬜ {对象}.{缺失类型}: {缺失路径} — {期望内容}
  ⬜ ...

请选择：
  [a] 人工补齐后重新检查（我会等待你的指令后重新执行 ③）
  [c] 终止工作流
```

**各选项后续行为：**

| 选项 | HIGH 档 | MID 档 | LOW 档 |
|------|--------|--------|--------|
| [a] | 等待，用户说"继续"后重新执行 ③ | 同左 | 同左 |
| [b] | exit-status → `DONE`，编排器继续 | exit-status → `DONE_PARTIAL`，编排器继续 | 不提供 |
| [c] | 编排器输出执行摘要并终止 | 同左 | 同左 |

## 重要约束

1. **只读不写**：本 skill 不修改本体文件
2. **不管理认证**：token、API key 等凭据由本体访问服务管理，skill 不接触
3. **不生成本体内容**：不替代人工或独立 agent 的本体编写工作
4. **比对基于关键标识**：搜索属性名/动作ID/函数ID/规则ID，不做语义级比对
5. **📝 不阻断**：建议调整项仅记录，不影响 exit-status 判定
6. **lane/priority 透传**：检查报告头部必须继承上游的 lane 和 priority
7. **force-pass 需显式**：默认不放行有缺失的情况，必须用户主动选择
8. **服务不可用时 BLOCKED**：不尝试 fallback 到直接 API 调用
9. **禁止产出额外文件**：本 skill 每次调用只写入 1 个文件（`{特性ID}_本体检查报告.md`），禁止创建任何其他文件

## skill-exit-status 规范

```yaml
skill-exit-status: DONE | DONE_PARTIAL | NEEDS_HUMAN | BLOCKED
skill-exit-detail: {补充说明}
gaps-remaining: {n}
coverage-rate: {n}      # 整数 0-100
coverage-tier: HIGH | MID | LOW
```

| 状态 | 含义 | 触发条件 |
|------|------|---------|
| `DONE` | 缺失项已全部补齐 | gaps-remaining=0，coverage-tier=HIGH |
| `DONE_PARTIAL` | 覆盖度中等，允许继续但需标注 | 用户选 [b] 跳过，coverage-tier=MID；或 `--force-pass` |
| `NEEDS_HUMAN` | 需人工介入 | 仍有缺失项未补齐（HIGH/MID 档），或 LOW 档强制阻断 |
| `BLOCKED` | 无法执行检查 | 本体访问服务不可用、② 产物缺失 |
