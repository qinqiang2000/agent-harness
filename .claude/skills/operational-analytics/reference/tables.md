# EOP 数据库表详细参考

本文档提供 EOP（Enterprise Operation Platform，运营平台）四个核心表的详细字段说明和关联关系。

## 目录

- [t_ocm_kbc_order_settle（销售出库单/结算表）](#t_ocm_kbc_order_settle)
- [t_ocm_order_header（交易订单主表）](#t_ocm_order_header)
- [t_ocm_order_lines（产品订单明细）](#t_ocm_order_lines)
- [t_ocm_tenant（租户表）](#t_ocm_tenant)
- [表关联关系](#表关联关系)
- [枚举值定义](#枚举值定义)

---

## t_ocm_kbc_order_settle

**用途**：结算、收款等信息。按客户名搜索最直接。

**记录数**：107,000+

### 字段详细说明

| 字段名                    | 字段备注     | 补充描述                                                     |
| ------------------------- | ------------ | ------------------------------------------------------------ |
| fbillno                   | 单据编号     |                                                              |
| fmodifytime               | 更新时间     |                                                              |
| fcreatetime               | 创建时间     |                                                              |
| fkbc_settle_billno        | 关联单据编号 |  |
| fproduct_serial_no        | 产品序列号   |                                                              |
| **fsale_product_name**    | 销售产品     | 产品名称字段                                                 |
| fversion_no               | 版本号       |                                                              |
| fsale_product_code        | 销售产品编码 |                                                              |
| **fpost_date**            | 记账日期     | **默认用此字段作为时间轴，表示订单创建时间**                 |
| **fdelivery_status**      | 交付状态     | 表示订单是否已经交付，**只有状态为"已交付"的才能结算**，计算收款时需要过滤 |
| frenew_status             | 续费状态     |                                                              |
| fcontract_no              | 合同编号     |                                                              |
| fbusiness_date            | 业务日期     |                                                              |
| fsale_org                 | 销售组织     |                                                              |
| fsale_department          | 销售部门     |                                                              |
| fsaler                    | 销售员       |                                                              |
| **fuse_customer**         | 使用客户     | **客户名搜索首选字段**                                       |
| **fsign_customer**        | 签约客户     | **客户名搜索备选字段**                                       |
| fproduct_name             | 产品名称     |                                                              |
| fmaterial_code            | 物料编码     |                                                              |
| fmaterial_name            | 物料名称     | **查询收款时需要过滤掉物料"售前、产品对接及实施支持服务"、"电子发票基础服务（标准版）"** |
| fdelivery_method          | 交付方式     |                                                              |
| fcontract_biz_type        | 合同业务类型 | **查询收款时需要过滤掉合同业务类型"升级"、"升级延期续签"**   |
| funit                     | 计量单位     |                                                              |
| fbatch_no                 | 批号         |                                                              |
| **fprice_tax_amount**     | 结算金额     | **用于计算收款**                                             |
| **famount**               | 金额（不含税） |                                                            |
| ftax_amount               | 税额         |                                                              |
| fsubscription_end_date    | 订阅截止日期 |                                                              |
| fdatetimefield            | 订阅起始日期 |                                                              |
| fenv_start_date           | 环境开始时间 |                                                              |
| fenv_end_date             | 环境截止时间 |                                                              |
| fdirect_distribution_sale | 直销分销     | **默认用此字段区分直销/分销**                                |
| fc_contract_type          | 子合同类型   | 用此字段判断收款类型：<br>**订阅收款**：fc_contract_type = '租赁服务'<br>**产品收款**：fc_contract_type IN ('租赁服务', '软件许可')<br>**考核收款**：不过滤（包含所有类型）<br><br>关系（集合包含）：考核收款 ⊇ 产品收款 ⊇ 订阅收款 |
| **fclassification**       | 产品分类     | 1: 开票 / 2: 收票 / 3: 影像 / 4: 增值服务 / 5: 收单机器人 / 6: 研发 / 7: 实施 |
| fcustomer_code            | 客户编码     |                                                              |
| fnew_or_renew             | 新购续费     | new: 新购 / renew: 续费                                      |
| **forder_source**         | 来源         | 查询订单来自哪个下单渠道。枚举值：KBC / 运营后台 / 官网下单 / 我家云 / 爱普生 / 华盟 / ICRM |
| ftotal_quantity           | 总订购数量   |                                                              |
| fbatchno_materialcode     | 批号物料编码 |                                                              |
| fkbc_createdate           | KBC创建时间  |                                                              |
| fcity                     | 城市         |                                                              |
| fduty_area_config         | 区域小组配置 |                                                              |
| ftenant                   | 租户         |                                                              |

### 业务规则

**收款统计时必须过滤：**
1. `fdelivery_status = '已交付'` - 只统计已交付订单
2. **排除物料**：
   - "售前、产品对接及实施支持服务"
   - "电子发票基础服务（标准版）"
3. **排除合同业务类型**：
   - "升级"
   - "升级延期续签"

---

## t_ocm_order_header

**用途**：查询订单的销售金额及相关订单信息，销售金额表示客户支付的金额。

**记录数**：109,000+

### 字段详细说明

| 字段名                    | 字段备注               | 补充描述                                                     |
| ------------------------- | ---------------------- | ------------------------------------------------------------ |
| **fid**                   | 主键                   | **关联 t_ocm_order_lines.fentryid**                          |
| **fbillno**               | 交易订单编号           |                                                              |
| fbillstatus               | 单据状态               |                                                              |
| fauditdate                | 审核日期               |                                                              |
| fmodifytime               | 修改时间               |                                                              |
| **fcreatetime**           | 创建时间               | **默认用这个字段作为时间轴**                                 |
| **fbusiness_type**        | 购买类型               | **Add**: 加购<br>**New**: 新购<br>**Renew**: 续费<br>**Return**: 退货<br>**Upgradation**: 升级，**升级订单不属于有效订单，计算订单收款时要过滤** |
| **fbiz_type**             | 订单类别               | **Standard**: 标准订单，表示付费的正式订单<br>**Special**: 特批订单，是不付费的经过审批的免费订单<br>**Free**: 免费的试用订单 |
| fcontract                 | 关联合同号             |                                                              |
| **ftenant**               | 租户                   | **租户编码，可以用这个编码去租户表查询[t_ocm_tenant]租户名称** |
| fcontact_name             | 联系人姓名             |                                                              |
| fcontact_phone            | 联系人电话             |                                                              |
| **fbill_source**          | 订单来源名称           | 1: 发票云直销 / 2: 生态伙伴 / 3: 营销伙伴 / 4: 金蝶中国直销 / 5: 金蝶中国分销 / 6: 个人伙伴 / 7: 发票云特批 |
| fsubscription_method      | 订阅方式               |                                                              |
| ftotal_amount             | 累计标准报价           |                                                              |
| fagreed_start_time        | 约定产品启用时间       |                                                              |
| fthird_party_billno       | 第三方平台交易订单编号 |                                                              |
| ftotal_quantity           | 订阅合计数量           |                                                              |
| fsettlement_method        | 结算方式               |                                                              |
| fcontact_email            | 联系邮箱               |                                                              |
| fpayment_methods          | 付费方式               |                                                              |
| fsource_channel           | 来源名称               |                                                              |
| fsale_name                | 跟进销售名称           |                                                              |
| fsale_phone               | 跟进销售电话           |                                                              |
| fadd_days                 | 启用时间增加天数       |                                                              |
| fpartner_name             | 交付伙伴名称           |                                                              |
| femail_status             | 邮件发送状态           |                                                              |
| fpayment_company_name     | 付款企业名称           |                                                              |
| fthird_party_serialid     | 第三方平台序列号       |                                                              |
| fparent_billno            | 主交易订单编号         |                                                              |
| ftax_no                   | 签约企业税号           |                                                              |
| forder_rate               | 订单折扣%              |                                                              |
| **fap_amount**            | 实际结算价             | **计算订单销售金额时默认用此字段**                           |
| finner_order_no           | 内部订单号             |                                                              |
| **fsale_org**             | 销售组织               | **用于查询是哪个分公司/机构销售**                            |
| forder_source             | 下单渠道               |                                                              |
| forder_desc               | 订单描述               |                                                              |
| **fcompany_name**         | 签约企业名称           | **默认用本字段表示客户**                                     |
| fproduct_num              | 订单产品数量           |                                                              |
| fproduct_enable_status    | 产品订单许可分配状态   |                                                              |
| finvoice_status           | 开票状态               |                                                              |
| factivate_code            | 全电票/数电票激活码    |                                                              |
| factivate_code_time       | 激活码截止时间         |                                                              |
| forder_activate_pwd       | 订单激活密钥           |                                                              |
| fbak_field                | 前端系统地址           |                                                              |
| fold_serial_no            | 合并后序列号           |                                                              |
| fallocation_status        | 产品启用状态           |                                                              |
| fbus_activate_code        | 订单/业务激活码        |                                                              |
| fout_stock_time           | 出库时间               |                                                              |
| forder_allocate_firsttime | 开始分配许可时间       |                                                              |
| forder_creator            | 订单创建人             |                                                              |
| forder_createor_phone     | 订单创建人电话         |                                                              |
| forder_createtime         | 订单DJ时间             |                                                              |
| freturn_ap_amount         | 累计退款金额           |                                                              |
| fcollection_status        | 收款状态               |                                                              |
| freconciliation_bill      | 是否生产对账单         |                                                              |
| fis_apply_openinvoice     | 是否可申请开票         |                                                              |
| fis_apply_payment         | 是否可申请核款         |                                                              |
| ftotal_actual_quotation   | 累计实际报价           |                                                              |
| fcash_out_amount          | 返佣金额               |                                                              |
| fnewadd_type              | 新增方式               |                                                              |

### 业务规则

**订单统计标准过滤：**
```sql
WHERE fbiz_type = 'Standard'              -- 只统计标准付费订单
  AND fbusiness_type != 'Upgradation'     -- 排除升级订单（不计费）
  AND fbusiness_type != 'Return'          -- 排除退货（或单独统计）
```

---

## t_ocm_order_lines

**用途**：交易订单的明细，用于记录交易订单涉及的具体产品/权益信息。

**记录数**：114,000+

**⚠️ 重要提示**：此表数据经常不完整，查询产品信息时优先使用 `t_ocm_kbc_order_settle` 表。

### 字段详细说明

| 字段名                    | 字段备注           | 补充描述                                 |
| ------------------------- | ------------------ | ---------------------------------------- |
| fid                       | 主键               |                                          |
| **fentryid**              | 关联交易订单ID     | **关联 t_ocm_order_header.fid**          |
| fproduct                  | 产品编码           |                                          |
| funit                     | 单位               |                                          |
| fsubscription_duration    | 订阅权益时长       |                                          |
| fproduct_billno           | 产品订单编号       |                                          |
| fprepaid_period           | 订阅周期           |                                          |
| fquantity                 | 订购数量           |                                          |
| fnote                     | 备注               |                                          |
| funit_price               | 单价               |                                          |
| ftax_price                | 含税单价           |                                          |
| fdiscount_rate            | 折扣率(%)          |                                          |
| fdiscount_amount          | 折扣额             |                                          |
| **famount**               | 金额               | **计算产品销售额时默认用这个字段**       |
| ftax_rate                 | 税率(%)            |                                          |
| ftax_amount               | 税额               |                                          |
| ftotal_tax_amount         | 价税合计           |                                          |
| fline_status              | 产品单据状态       |                                          |
| fbuy_type                 | 购买类型           |                                          |
| fallocated_quantity       | 已分配数量         |                                          |
| funallocated_quantity     | 未分配数量         |                                          |
| **fbenefit_start_date**   | 权益开始时间       | **用于查询订购产品的开始日期或时间**     |
| **fbenefit_end_date**     | 权益结束时间       | **用于查询订购产品的截止日期或时间**     |
| **fline_quantity**        | 总订购数量         | **查询产品购买数量**                     |
| fupdate_user              | 修改人             |                                          |
| fcreated_user             | 创建人             |                                          |
| fupdate_date              | 修改时间           |                                          |
| fcreate_date              | 创建日期           |                                          |
| frights_num               | 权益票量           |                                          |
| finner_order_no           | 内部订单编号       |                                          |
| fproduct_enable_date      | 产品约定启用时间   |                                          |
| fparent_product_billno    | 主产品订单编号     |                                          |
| factual_enable_date       | 实际启用时间       |                                          |
| **fproduct_serial_no**    | 产品序列号         | **所购买产品的唯一识别码**               |
| frigths_dispatch_status   | 权益分配状态       |                                          |
| fdeployment_method        | 部署方式           |                                          |
| factivate_method          | 激活入口           |                                          |
| flines_allocation_status  | 许可状态           |                                          |
| fstdmount                 | 标准金额（打折前） |                                          |
| fline_allocate_firsttime  | 开始分配许可时间   |                                          |
| fline_subscription_method | 订购方式           |                                          |
| freturn_quantity          | 退货数量           |                                          |
| freturn_amount            | 退款金额           |                                          |
| fbecome_stats             | 特批订单转正状态   |                                          |
| fbecome_note              | 转正备注           |                                          |
| fbecome_num               | 转正产品订购数     |                                          |
| frel_num                  | 转正关联订单数     |                                          |
| ffirst_use_date           | 第一次使用业务时间 |                                          |
| fis_auto_allocated        | 是否自动分配过     |                                          |
| fbecome_type_stats        | 同类转正状态       |                                          |
| fbecome_type_num          | 同类转正产品订购数 |                                          |
| ftype_rel_num             | 同类转正关联订单数 |                                          |

---

## t_ocm_tenant

**用途**：租户基本信息。

**记录数**：35,000+

### 字段详细说明

| 字段名              | 字段备注           | 补充描述                                   |
| ------------------- | ------------------ | ------------------------------------------ |
| **fid**             | 主键               | **关联 t_ocm_order_header.ftenant**        |
| **fnumber**         | 租户编码           | **用于关联其他表单的租户编码**             |
| **fname**           | 租户名称           | **一般问租户时默认查询这个字段**           |
| fenable             | 使用状态           | 0: 禁用 / 1: 可用                          |
| fcontact_phone      | 联系人电话         |                                            |
| fcontact_name       | 联系人名字         |                                            |
| fcontact_email      | 联系人email        |                                            |
| fclient_id          | fclient_id         |                                            |
| fclient_secret      | fclient_secret     |                                            |
| fenc_key_aes128     | fenc_key_aes128    |                                            |
| factivate_code      | 全电客户端激活码   |                                            |
| factivate_code_time | 全电客户端激活时间 |                                            |

---

## 表关联关系

### 概述

- **交易订单跟产品订单**主要展示客户的下单信息
- 交易订单跟产品订单是**主表跟子表的关系**，包含了发票云所有的订单数据
- 交易订单包含了所有的交易信息
- 产品订单则进一步展示不同产品的订单情况
- 交易订单产生时系统会根据指定逻辑创建或者关联租户
- 租户信息会储存在租户表，与交易订单进行关联
- **销售出库单**包含所有与发票云结算的订单数据，主要用于查询给发票云结算的款项金额及关联订单信息

### 关系图

```
t_ocm_order_header.fid (1) ←→ (N) t_ocm_order_lines.fentryid
t_ocm_order_header.ftenant (N) ←→ (1) t_ocm_tenant.fid
```

---

## 枚举值定义

### fbiz_type（订单类别）- t_ocm_order_header

| 值 | 含义 | 是否付费 |
|----|------|---------|
| **Standard** | 标准订单 | ✅ 付费 |
| Special | 特批订单 | ❌ 免费 |
| Free | 试用订单 | ❌ 免费 |

### fbusiness_type（业务类型）- t_ocm_order_header

| 值 | 含义 | 是否计入营收 |
|----|------|-------------|
| New | 新购 | ✅ |
| Renew | 续费 | ✅ |
| Add | 加购 | ✅ |
| Return | 退货 | ❌（负数）|
| **Upgradation** | 升级 | ❌ **必须排除** |

### fdelivery_status（交付状态）- t_ocm_kbc_order_settle

| 值 | 含义 | 是否可结算 |
|----|------|----------|
| **已交付** | 已完成交付 | ✅ |
| 待交付 | 尚未交付 | ❌ |

### fbill_source（订单来源）- t_ocm_order_header

| 值 | 渠道 |
|----|------|
| 1 | 发票云直销 |
| 2 | 生态伙伴 |
| 3 | 营销伙伴 |
| 4 | 金蝶中国直销 |
| 5 | 金蝶中国分销 |
| 6 | 个人伙伴 |
| 7 | 发票云特批 |

### forder_source（订单来源）- t_ocm_kbc_order_settle

| 值 | 渠道 |
|----|------|
| 金蝶中国 | KBC |
| 运营后台 | 运营后台 |
| 官网下单 | 官网下单 |
| 我家云 | 我家云 |
| 爱普生 | 爱普生 |
| 华盟 | 华盟 |
| ICRM | ICRM |
