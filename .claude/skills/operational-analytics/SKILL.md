---
name: operational-analytics
description: |
  运营分析Agent，负责EOP（Enterprise Operation Platform）数据库查询与分析。支持订单查询、租户统计、营收分析、运营报表。

  触发词：EOP、运营平台、订单查询、租户数据、营收分析、结算单、t_ocm_* 表名
---

# 运营分析 Skill

根据自然语言查询 EOP 数据库，生成 SQL 并返回结果。

> **CRITICAL: 此数据库为 PostgreSQL，禁止使用 MySQL 语法（如 YEAR()、MONTH() 等函数）**
>
> 日期提取使用 `EXTRACT(YEAR FROM field)`，时间过滤使用字符串比较 `>= '2024-01-01'`

---

## 查询工具

```bash
# 执行 SQL 查询（自动安全检查：SELECT-only, 4表白名单, 60秒超时）
source .venv/bin/activate
python .claude/skills/operational-analytics/scripts/query.py "SELECT ..."

# 结果为空时诊断
python .claude/skills/operational-analytics/scripts/diagnose.py --tenant "租户名" --year 2025
```

---

## 查询规划工作流

复制检查清单并跟踪进度：

```
查询进度：
- [ ] 步骤1：识别查询意图
- [ ] 步骤2：选择主表
- [ ] 步骤3：应用业务规则
- [ ] 步骤4：验证并执行
```

### 步骤1：识别查询意图

- **客户/产品查询** → 优先使用 `t_ocm_kbc_order_settle`（结算表）
- **订单详情/时间线** → 使用 `t_ocm_order_header`（订单表）
- **金额查询** → 先确认金额类型（见下文"金额字段映射"）

### 步骤2：选择主表

参考"表快速索引"选择最适合的表。

### 步骤3：应用业务规则

根据查询类型应用过滤规则（见下文"关键业务规则"）。

### 步骤4：验证并执行

执行前检查：时间范围过滤、业务规则、查询逻辑。

---

## 表快速索引

| 表名 | 用途 | 关键字段 |
|------|------|----------|
| **t_ocm_kbc_order_settle** | 结算/收款 | fuse_customer, fprice_tax_amount, fpost_date |
| **t_ocm_order_header** | 订单查询 | fbillno, fap_amount, fcreatetime |
| **t_ocm_order_lines** | 产品明细 | fentryid, famount |
| **t_ocm_tenant** | 租户信息 | fid, fname |

**详细字段说明**：[reference/tables.md](reference/tables.md)

---

## 表关联关系

```
t_ocm_order_header.fid (1) ←→ (N) t_ocm_order_lines.fentryid
t_ocm_order_header.ftenant (N) ←→ (1) t_ocm_tenant.fid
```

**JOIN 建议**：
- 订单 + 产品明细：`INNER JOIN`
- 订单 + 租户：`LEFT JOIN`（租户信息可能缺失）
- 客户查产品：**无需JOIN**，直接查结算表

---

## 金额字段映射

### 业务背景

**金蝶发票云的渠道销售模式**：
- 产品通过多种销售渠道销售（直销、生态伙伴、营销伙伴等），需支付渠道费用
- 因此两个表的金额含义不同：
  - **t_ocm_kbc_order_settle（结算表）**：公司实际收到的金额（扣除渠道费后）
  - **t_ocm_order_header（订单表）**：客户支付的销售价格（产品订阅费/合同金额）

### 金额字段选择

当用户查询"金额"但类型不明确时，**必须用 AskUserQuestion 工具确认**（见"输出规范"）：

| 用户意图 | 查询表 | 字段 |
|---------|--------|------|
| 结算/收款金额 | t_ocm_kbc_order_settle | fprice_tax_amount |
| 订单/合同金额 | t_ocm_order_header | fap_amount |
| 标准报价 | t_ocm_order_header | fstandard_amount |

**收款类型细分**（结算表 fc_contract_type）：
- 订阅收款：`= '租赁服务'`
- 产品收款：`IN ('租赁服务', '软件许可')`
- 考核收款：不过滤

关系：考核收款 ⊇ 产品收款 ⊇ 订阅收款

---

## 关键业务规则

### 营收统计过滤

**订单表 (t_ocm_order_header)**：
```sql
WHERE fbiz_type = 'Standard'           -- 标准付费订单
  AND fbusiness_type != 'Upgradation'  -- 排除升级（不计费）
```

**结算表 (t_ocm_kbc_order_settle)**：
```sql
WHERE fdelivery_status = '已交付'       -- 已交付才可结算
```

**完整枚举值和业务规则**：见 [reference/tables.md](reference/tables.md#枚举值定义)

---

## 查询优化

- 添加时间范围过滤（fpost_date / fcreatetime）
- 客户名搜索使用 `LIKE '%关键字%'`
- 避免不必要的 JOIN

---

## 输出规范

### CRITICAL: 询问用户

**当需要用户确认或选择时（如金额类型不明确），MUST 使用 AskUserQuestion 工具：**

```
Use AskUserQuestion tool with:
question: "请确认您要查询的金额类型"
header: "金额类型"
options:
  - label: "结算/收款金额"
    description: "fprice_tax_amount (结算表)"
  - label: "订单/合同金额"
    description: "fap_amount (订单表)"
  - label: "标准报价"
    description: "fstandard_amount (订单表)"
```

**🛑 调用 AskUserQuestion 后，立即停止执行 🛑**
   - **DO NOT** 调用任何其他工具（Glob、Grep、Read 等）
   - **DO NOT** 继续搜索或准备数据
   - **WAIT** 用户回答会在下一轮对话中返回
   - 用户回答后，再根据答案搜索对应产品的文档

**NEVER**：
- 直接输出问题让用户选择（必须用 AskUserQuestion 工具）
- 在不确定时猜测用户意图

### CRITICAL: 最终输出规范

**直接输出面向用户的内容：**

**MUST**：
- 直接输出最终答案，无需特殊标签包装
- SDK 会自动将你的输出包装到 `ResultMessage.result` 字段中
- 内容会在 Agent 完成时一次性返回给用户
- **任务完成后必须有直接文本输出**，不能以工具调用（如 TodoWrite）结束

**NEVER**：
- 以 TodoWrite 或其他工具调用作为最后一个动作
- 假设用户能从工具调用中获取答案
- 在调用 AskUserQuestion 后继续输出内容

### 输出格式

**直接输出面向用户的内容，无需标签包装。**

#### 1. 展示 SQL

```sql
SELECT ...
```

#### 2. 结构化列表（适配聊天工具）

```
【查询标题】

▪ 项目1
  • 字段1：值1

━━━━━━━━━━━━━━
💰 汇总信息
```

#### 3. 自然语言解释

说明查询思路、数据来源、业务含义。

---

## 故障排查

### 查询结果为空？

1. **运行诊断**：
   ```bash
   python .claude/skills/operational-analytics/scripts/diagnose.py --tenant "租户名" --year 2025
   ```

2. **常见问题**：
   - 客户名拼写（用 `LIKE '%关键字%'`）
   - 日期范围过窄
   - 交付状态过滤
   - 订单类型过滤
