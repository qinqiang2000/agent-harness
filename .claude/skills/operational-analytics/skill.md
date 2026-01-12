---
name: operational-analytics
description: |
  运营分析Agent，负责EOP（Enterprise Operation Platform，运营平台）数据库查询与分析。支持订单查询、租户数据统计、营收趋势分析、运营报表生成。

  触发词：EOP、运营平台、Enterprise operation platform、订单查询、租户数据、销售数据、营收分析、运营报表、数据统计、交易订单、产品订单、结算单、销售出库单、t_ocm_kbc_order_settle、t_ocm_order_header、t_ocm_order_lines、t_ocm_tenant
---

# 运营分析 Skill

根据自然语言查询 EOP 数据库，生成 SQL 并返回结果。

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

复制下面的检查清单并跟踪进度：

```
查询进度：
- [ ] 步骤1：识别查询意图（客户查询 / 订单统计 / 营收分析等）
- [ ] 步骤2：选择主表并根据需要关联其他表
- [ ] 步骤3：应用业务规则过滤
- [ ] 步骤4：验证并执行查询
```

### 步骤1：识别查询意图

- **客户/产品查询** → 优先使用 `t_ocm_kbc_order_settle`（结算表）
- **订单详情/时间线** → 使用 `t_ocm_order_header`（订单表）
- **营收统计** → 检查业务规则，选择合适的表

### 步骤2：选择主表并根据需要关联其他表

参考下面的"表快速索引"和"表关联关系"选择最适合的表，根据表结构和查询需求判断是否需要JOIN。

### 步骤3：应用业务规则过滤

根据查询类型应用相应的过滤规则（见下文"关键业务规则"）。

### 步骤4：验证并执行查询

执行前检查：
- 是否包含时间范围过滤
- 是否应用了必要的业务规则
- 查询逻辑是否正确

---

## 表快速索引

**详细字段说明**：见 [reference/tables.md](reference/tables.md)

| 表名 | 用途 | 关键字段 | 时间字段 | 记录数 |
|------|------|----------|----------|--------|
| **t_ocm_kbc_order_settle** | 结算/收款查询| fuse_customer, fsign_customer<br>fsale_product_name<br>fprice_tax_amount<br>fdelivery_status | fpost_date | 107K+ |
| **t_ocm_order_header** | 订单查询<br>时间线分析 | fbillno, ftenant<br>fbiz_type, fbusiness_type<br>fcompany_name<br>fap_amount | fcreatetime | 109K+ |
| **t_ocm_order_lines** | 产品订单明细 | fentryid (关联订单ID)<br>fproduct_billno<br>famount | fbenefit_start_date<br>fbenefit_end_date | 114K+ |
| **t_ocm_tenant** | 租户基本信息 | fid (关联订单)<br>fnumber (租户编码)<br>fname (租户名称) | - | 35K+ |

**查找详细字段**：当需要了解字段含义、业务逻辑或关联关系时，使用：
```bash
grep -i "字段名" .claude/skills/operational-analytics/reference/tables.md
```

或直接阅读 [reference/tables.md](reference/tables.md) 中的对应表章节。

---

## 核心字段速查

### t_ocm_kbc_order_settle（结算表）

| 字段 | 含义 | 说明 |
|------|------|------|
| **fuse_customer** / **fsign_customer** | 使用客户 / 签约客户 | 客户名搜索 |
| **fsale_product_name** | 销售产品 | 产品名称 |
| **fprice_tax_amount** | 金额（含税） | 结算金额 |
| **fdelivery_status** | 交付状态 | '已交付' / '待交付' |
| **fpost_date** | 记账日期 | 时间轴 |

### t_ocm_order_header（订单表）

| 字段 | 含义 | 说明 |
|------|------|------|
| **fbillno** | 订单号 | - |
| **fcreatetime** | 创建时间 | 时间轴 |
| **ftenant** | 租户编码 | 关联 t_ocm_tenant.fid |
| **fbiz_type** | 订单类别 | Standard / Special / Free |
| **fbusiness_type** | 业务类型 | New / Renew / Add / Upgradation / Return |
| **fap_amount** | 实际结算价 | 订单金额 |

### t_ocm_order_lines（产品明细）

| 字段 | 含义 | 说明 |
|------|------|------|
| **fentryid** | 关联订单ID | 关联 t_ocm_order_header.fid |
| **famount** | 金额 | 产品金额 |
| **fbenefit_start_date** / **fbenefit_end_date** | 权益时间 | 开始/结束 |

### t_ocm_tenant（租户表）

| 字段 | 含义 | 说明 |
|------|------|------|
| **fid** | 主键ID | 订单表的 ftenant 字段关联此字段 |
| **fname** | 租户名称 | 搜索租户 |

**完整字段列表**：见 [reference/tables.md](reference/tables.md)

---

## 表关联关系

```
t_ocm_order_header.fid (1) ←→ (N) t_ocm_order_lines.fentryid
t_ocm_order_header.ftenant (N) ←→ (1) t_ocm_tenant.fid
t_ocm_kbc_order_settle ← (复杂，不推荐) → t_ocm_order_header
```

**JOIN 建议**：
- 订单 + 产品明细：`INNER JOIN`（如果明细表有数据）
- 订单 + 租户：`LEFT JOIN`（租户信息可能缺失）
- 客户查产品：**无需JOIN**，直接查结算表

**详细关联说明**：见 [reference/tables.md](reference/tables.md#表关联关系)

---

## 枚举值

### fbiz_type（订单类别）

| 值 | 含义 | 是否付费 |
|----|------|---------|
| **Standard** | 标准订单 | ✅ 付费 |
| Special | 特批订单 | ❌ 免费 |
| Free | 试用订单 | ❌ 免费 |

### fbusiness_type（业务类型）

| 值 | 含义 | 是否计入营收 |
|----|------|-------------|
| New | 新购 | ✅ 是 |
| Renew | 续费 | ✅ 是 |
| Add | 加购 | ✅ 是 |
| Return | 退货 | ❌ 否（负数） |
| **Upgradation** | 升级 | ❌ **否（必须排除）** |

### fdelivery_status（交付状态）

| 值 | 含义 | 是否可结算 |
|----|------|----------|
| **已交付** | 已完成交付 | ✅ 是 |
| 待交付 | 尚未交付 | ❌ 否 |

### fbill_source（订单来源）

| 值 | 渠道 |
|----|------|
| 1 | 发票云直销 |
| 2 | 生态伙伴 |
| 3 | 营销伙伴 |
| 4 | 金蝶中国直销 |
| 5 | 金蝶中国分销 |
| 6 | 个人伙伴 |
| 7 | 发票云特批 |

---

## 关键业务规则

### 营收统计标准过滤

**订单表查询：**
```sql
WHERE fbiz_type = 'Standard'              -- 只统计标准付费订单
  AND fbusiness_type != 'Upgradation'     -- 排除升级订单（不计费）
  AND fbusiness_type != 'Return'          -- 排除退货（或单独统计）
```

**结算表查询：**
```sql
WHERE fdelivery_status = '已交付'          -- 只统计已交付订单
  AND fpost_date >= '开始时间'
```

**详细业务规则**：见 [reference/tables.md](reference/tables.md)（包含物料过滤、合同业务类型过滤等）

---

### 查询优化

- 添加时间范围过滤（fpost_date / fcreatetime）
- 客户名搜索使用 `LIKE '%关键字%'`（支持模糊匹配）
- 避免不必要的 JOIN（尤其是 t_ocm_order_lines）

---

## 输出格式要求

### 1. 展示生成的 SQL

```sql
-- 示例
SELECT ...
FROM ...
WHERE ...
```

### 2. 结构化列表展示结果

使用清晰的列表格式（适配微信、云之家等聊天工具）：

```
【查询标题】

▪ 项目1
  • 字段1：值1
  • 字段2：值2

▪ 项目2
  • 字段1：值1
  • 字段2：值2

━━━━━━━━━━━━━━
💰 汇总信息
```

### 3. 自然语言解释

说明查询思路、数据来源、业务含义。

### 4. 复杂查询时说明过程

如果经历多步探索、尝试多个查询或遇到问题，简要说明查询路径（审计用）。

---

## 故障排查

### 查询结果为空？

1. **运行诊断脚本：**
   ```bash
   python .claude/skills/operational-analytics/scripts/diagnose.py --tenant "租户名" --year 2025
   ```

2. **检查常见问题：**
   - 客户名拼写（使用 `LIKE '%关键字%'` 模糊匹配）
   - 日期过滤范围过窄
   - 交付状态过滤（'已交付' vs '待交付'）
   - 订单类型过滤（Standard vs Special/Free）
   - 业务类型过滤（检查是否误过滤了有效订单）
