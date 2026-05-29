---
name: validate-upstream
description: >
  上游产物校验协议。每个 skill 在阶段 0 执行此协议，
  根据 frontmatter 中的 consumes 声明，校验上游产物的存在性和格式完整性。
---

# 上游产物校验协议（validate-upstream）

## 用途

本协议供各 skill 在阶段 0 统一引用，替代各自零散的上游检查逻辑。
编排器在调用每个 skill 前也可执行此协议做预检。

## 校验流程

### Step 1 · 产物存在性检查

读取当前 skill 的 `consumes` 声明，对每个条目：

1. 在 `{output-path}/` 下按 `pattern` 匹配文件
2. `multiplicity: "per-feature"` 的条目 → 读取 特性清单 获取子需求数量，逐个匹配
3. 记录结果：

| 条目 | pattern | 来源 skill | 匹配结果 |
|------|---------|-----------|---------|
| 1 | {pattern} | {from} | ✅ 找到 / ⬜ 缺失 |

### Step 2 · 必填字段检查

对每个找到的产物文件：

1. 读取 YAML header
2. 检查 `consumes[].fields` 中声明的字段是否存在且非空
3. 检查 `lane` 和 `priority` 字段是否存在（所有产物通用）
4. 若产物的 `lane=fast` 且需求分类为 Bug → 还需检查 `bug-subtype` 字段存在且值为 `rule | ux | tech`
5. 记录结果：

| 文件 | 字段 | 状态 |
|------|------|------|
| {文件名} | lane | ✅ / ⬜ |
| {文件名} | priority | ✅ / ⬜ |
| {文件名} | {field} | ✅ / ⬜ |

### Step 3 · exit-status 检查

对上游 skill 的主产物（特性清单 / 需求分析报告等）：

1. 读取 `skill-exit-status` 字段
2. 与当前 skill 的 `depends-on[].condition` 比对
3. 不满足条件 → 标记为 BLOCKED

### Step 3.5 · 覆盖度阈值检查

仅当当前 skill 的 `depends-on` 中包含 `coverage-check: true` 时执行本步骤。

1. 从 ③ 本体检查报告（`*_本体检查报告.md`）读取 `coverage-rate` 和 `coverage-tier`
   - ③ 未执行（② exit-status=`DONE`，无缺失项）→ 视为 `coverage-tier=HIGH`，跳过本步骤
   - ③ 产物存在但缺少 `coverage-rate` 字段 → 回退读取 ② 特性清单的 `coverage-summary` 自行计算：
     `coverage-rate = floor(passed / checked * 100)`

2. 阈值判定：

| coverage-tier | coverage-rate | 判定结果 | 处理 |
|--------------|--------------|---------|------|
| HIGH | >= 80% | PASS | 继续执行 skill |
| MID | 60-79% | PASS_WITH_WARNINGS | 继续执行，产物中标注待补充 |
| LOW | < 60% | FAIL | 终止，报告覆盖度不足 |

3. 记录判定结果，进入 Step 4 汇总

---

### Step 4 · 汇总判定

| 情况 | 判定 | 处理 |
|------|------|------|
| 全部 ✅ | PASS | 继续执行 skill |
| 有 ⬜ 但对应 consumes 标记 `condition: "optional"` | PASS_WITH_WARNINGS | 继续执行，跳过缺失的可选输入 |
| 有 ⬜ 且对应 consumes 无 optional 标记 | FAIL | 终止，报告缺失项 |
| exit-status 不满足 depends-on condition | FAIL | 终止，报告前置条件不满足 |
| coverage-tier=LOW（Step 3.5 判定） | FAIL | 终止，覆盖度不足，必须先补本体 |

### Step 5 · 报告格式

**PASS 时**（静默，不输出）

**PASS_WITH_WARNINGS 时（可选项缺失）：**
```
⚠️ 上游产物校验通过（有可选项缺失）：
  · {pattern} ({from}) — 缺失，已跳过
继续执行 {当前 skill 名称}...
```

**PASS_WITH_WARNINGS 时（覆盖度中等，MID 档）：**
```
⚠️ 上游产物校验通过（覆盖度中等，将标注待补充）：
  · coverage-rate: {n}%（MID，60-79%）
  · 仍缺失项数: {gaps-remaining}
  · 本 skill 产物中将标注「⚠️ 本体待补充」
继续执行 {当前 skill 名称}...
```

**FAIL 时（产物缺失或前置条件不满足）：**
```
❌ 上游产物校验失败，无法执行 {当前 skill 名称}：

  缺失的必须产物：
  · {pattern} ({from}) — 请先执行 {from skill}

  前置条件不满足：
  · {depends-on skill} exit-status={actual}，需要 {expected}

建议操作：
  · 按顺序执行前置 skill，或使用 /product-workflow 自动编排
```

**FAIL 时（覆盖度不足，LOW 档）：**
```
❌ 上游产物校验失败，无法执行 {当前 skill 名称}：

  本体覆盖度不足：
  · coverage-rate: {n}%（阈值要求 ≥ 60%）
  · coverage-tier: LOW
  · 仍缺失项数: {gaps-remaining}

建议操作：
  · 补充本体缺失项，使覆盖度达到 60% 以上
  · 补充后重新执行 ③ 本体更新 Gate
  · 或使用 /product-workflow 重新编排
```

## 各 skill 引用方式

在 SKILL.md 的阶段 0 中加入：

```
### 阶段 0 · 上游产物校验

按 [validate-upstream 协议](../commands/validate-upstream.md) 执行：
1. 读取本 skill frontmatter 中的 consumes 声明
2. 在 {output-path}/ 下逐项校验存在性 + 必填字段 + exit-status
3. PASS → 继续；FAIL → 终止并报告
```
