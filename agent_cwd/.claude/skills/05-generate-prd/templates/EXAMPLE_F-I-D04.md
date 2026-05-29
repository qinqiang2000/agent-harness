# F-I-D04 · 增值税合规校验
> **文档类型：** 产品规格说明书
> **版本：** v1.4 · 正式
> **最后更新：** 2026-03-24
> **所属模块：** 对内平台原子接口 / invoice-data

**版本记录**

| 版本   | 日期         | 变更说明                                                                                           |
| ---- | ---------- | ---------------------------------------------------------------------------------------------- |
| v1.0 | 2026-03-16 | 初始版本                                                                                           |
| v1.3 | 2026-03-20 | 对齐本体 v2.0.3-beta：规则包恢复14条规则（CN-VL1-008/024、CN-VL2-012、CN-VL3-001~010/015）；CN-VL1-010 升级为 Fatal |
| v1.4 | 2026-03-24 | 对齐本体 v2.0.4-beta：ProfileSelectionRules 输入新增 Party(AccountingSupplierParty).PostalAddress.Country 与 Party(AccountingSupplierParty).Extension.CN.ChannelType 两个路由键；InvoiceContext 字段名统一更正为 SpecialBusinessType |

---

## 一、特性概述

> **What：** 在发票进入开具流程之前，平台自动对 invoice-data 执行增值税合规校验，覆盖字段必填/格式、金额封闭性、税制规则、接口合规及行业专项规则，拦截不合规数据，保护开票方合规风险。

| 维度   | 内容                                                                                                               |
| ---- | ---------------------------------------------------------------------------------------------------------------- |
| 特性类型 | 对内平台原子接口（由 ACT-01 创建草稿后串联调用）                                                                            |
| 覆盖对象 | invoice-data（销项发票数据）                                                                                             |
| 覆盖动作 | ACT-04（提交合规校验 / OutInv_Validate_Content）                                                                         |
| 用户价值 | 在发票提交开具前，自动验证发票数据是否满足中国增值税法规要求，拦截不合规数据，避免税局退票、罚款                                                                 |
| 适用范围 | 数电普票（028）/ 数电专票（081）；正数蓝票（380）/ 负数红票（381）；含不动产租赁场景                                                               |
| 适用地区 | CN（乐企联用）                                                                                                         |
| 成功指标 | **Primary**：合规拦截准确率 ≥ 99.9%<br>**Secondary**：字段级错误定位率 100%；校验响应 P99 < 200ms（标准路径）<br>**Guardrail**：不得影响正常开票链路成功率 |
| 不做什么 | 不校验发票业务真实性；不处理税局实时报文交互（由 ACT-10 负责）；差额征税规则（CN-VL2-004~006）本期 MVP 外 |

---

## 二、用户故事

### 业务场景

上游调用方提交开票请求后，平台在正式向税局发起开具前，需对发票数据进行增值税合规性自动校验；校验通过则数据锁定进入开具流程，校验失败则返回字段级错误清单供客户修正后重新提交。

### 主故事

```
As a    平台接入企业（通过开票接口提交开票申请的企业财务系），
I want  在发票提交后，平台自动完成增值税合规校验，无需人工介入，
So that 在正式向税局发起开具前拦截不合规数据，
        避免税局退票、罚款及企业合规风险。
```

### 用户旅程

**触发条件：** ACT-01 创建草稿完成后，平台自动触发 ACT-04

**Happy Path：**

```
1. invoice-data 状态为 S01（草稿 / DRAFT）
2. 平台自动触发 ACT-04，ProfileSelectionRules 路由至 CN-LEQI 校验规则包
3. 按序执行 VL1 → VL2 → VL3 → VL4（按需）规则包，全部 Fatal 规则通过
4. WriteValidationReport 写入校验报告引用至 AdditionalDocumentReference
5. 结果：状态迁移 S01 → S03（校验成功 / VALIDATED，数据锁定），进入开具流程（ACT-10）
```

**Unhappy Path：**

| # | 触发条件 | 系统行为 | 状态迁移 | 用户感知 |
|---|---------|---------|---------|---------|
| U1 | invoice-data 状态不是 S01 或 S02 | 拒绝执行，返回 HTTP 409 | 保持原状态 | 错误码 `INVDATA_INVALID_STATE` + 当前状态值 |
| U2 | 任一 Fatal 规则失败 | 收集全量错误，状态置 S02 | S01 → S02 | 字段级错误清单（code + field + message） |
| U3 | 仅 Warning 规则失败 | 状态仍置 S03，Warning 随错误清单返回 | S01 → S03 | Warning 提示，不阻断 |
| U4 | 校验服务内部异常 | 状态保持 S01，返回 HTTP 500 | 保持 S01 | "服务异常，请稍后重试"，不产生脏状态 |

### 验收标准

**功能 AC**

- [ ] [F-AC-01] status=S01 触发 ACT-04 且全部 Fatal 通过 → S03，响应含 `validation_result: "PASS"`
- [ ] [F-AC-02] status=S01 触发 ACT-04 且任一 Fatal 失败 → S02，响应含全量 errors 数组
- [ ] [F-AC-03] status 不是 S01/S02 时触发 ACT-04 → HTTP 409，`INVDATA_INVALID_STATE`
- [ ] [F-AC-04] 服务异常 → 保持 S01，HTTP 500
- [ ] [F-AC-05] S02 状态修正后重新触发 ACT-04 → 可正常走完校验链路
- [ ] [F-AC-06] 仅 Warning 规则失败（无 Fatal 失败）→ S03，Warning 随响应返回但不阻断开具流程

**合规 AC**

- [ ] [C-AC-01] CN-VL1-009：销方税号超过 20 位时触发拦截
- [ ] [C-AC-02] CN-VL1-005：专票购方税号为空时触发拦截；普票购方税号为空时通过
- [ ] [C-AC-03] CN-VL1-018：行税额计算误差 > 0.06 元时触发拦截
- [ ] [C-AC-04] CN-VL2-001：税率不在合法枚举内时触发拦截
- [ ] [C-AC-05] CN-VL4-EL-001：SpecialBusinessType=不动产租赁时 estateLeaseList 为空触发拦截
- [ ] [C-AC-06] 错误返回中 code 精确对应规则编码，field 精确到出错字段路径

**性能 AC**

- [ ] [P-AC-01] 标准路径（VL1+VL2+VL3）P99 < 200ms
- [ ] [P-AC-02] 含 VL4 路径（不动产租赁）P99 < 500ms

---

## 三、校验规则说明

> **设计原则：**
> - 规则包内规则以规则 ID 索引为准，不在本文重复描述逻辑，开发直接读取该特性关联对象的 RulePackage
> - 规则包外的约束在 3.2 节单独说明
> - 地区规则更新时只需维护 RulePackage，本文 3.1 仅更新规则 ID 列表

### 3.1 规则包调用（CN_RulePackage_v2.0.3-beta）

> 规则详情见：`invd_05.1_CN-LEQI_RulePackage.md`（v2.0.3-beta）
> 触发动作：ACT-04；Guard: S01/S02 → Effect: S03（通过）/ S02（失败）

**蓝票场景（InvoiceTypeCode=380）必跑规则：**

| 规则层 | 规则 ID                   | 规则名称                               | 严重性                     | 适用通道 |
| --- | ----------------------- | ---------------------------------- | ----------------------- | ---- |
| VL1 | CN-VL1-002 ~ CN-VL1-007 | 字段必填性（蓝字标志/票种/销购方/金额/明细行）          | ❌ Fatal                 | ALL  |
| VL1 | CN-VL1-008              | 发票号码格式校验（20位数字、前缀与票种一致）            | ❌ Fatal                 | ALL  |
| VL1 | CN-VL1-009 ~ CN-VL1-013 | 字段格式/长度（税号/金额精度/名称长度/行数上限）         | ❌/⚠️                    | ALL  |
| VL1 | CN-VL1-010              | 日期格式校验                             | ❌ Fatal                 | ALL  |
| VL1 | CN-VL1-014 ~ CN-VL1-019 | 数量单价联动、金额封闭性（单行/汇总/价税合计/税额）        | ❌ Fatal                 | ALL  |
| VL1 | CN-VL1-020              | 正数发票金额符号                           | ❌ Fatal                 | ALL  |
| VL1 | CN-VL1-021              | 折扣行规则（含税收分类编码须与被折扣行一致）             | ❌ Fatal                 | ALL  |
| VL1 | CN-VL1-022              | 自然人标志与证件联动                         | ⚠️ Warning              | ALL  |
| VL1 | CN-VL1-023              | 自然人证件与国籍联动                         | 🔷 Optional             | ALL  |
| VL1 | CN-VL1-024              | 自然人购方税号一致性                         | ❌ Fatal                 | ALL  |
| VL1 | CN-VL1-025              | 经办人信息完整性                           | ❌ Fatal                 | ALL  |
| VL2 | CN-VL2-001 ~ CN-VL2-003 | 税率有效性、商品编码有效性、优惠政策匹配               | ❌ Fatal                 | ALL  |
| VL2 | CN-VL2-007 ~ CN-VL2-009 | 减按征税类型/与差额互斥/税额计算（含3%简易征收减按1.5%场景） | ❌ Fatal                 | ALL  |
| VL2 | CN-VL2-010 ~ CN-VL2-011 | 不征税/简易征收不得混开                       | ❌ Fatal                 | ALL  |
| VL2 | CN-VL2-012              | 贷款服务/餐饮服务专票合规提示                    | ⚠️ Warning              | ALL  |
| VL2 | CN-VL2-013 ~ CN-VL2-014 | 即征即退类型校验、6开头商编强制不征税                | ❌ Fatal                 | ALL  |
| VL3 | CN-VL3-001 ~ CN-VL3-003 | 纳税人资质（风险类型/预警级别/状态）                | 🔷 Optional             | ALL  |
| VL3 | CN-VL3-004 ~ CN-VL3-006 | 额度管控（有效期/跨月/超额度）                   | 🔷 Optional             | ALL  |
| VL3 | CN-VL3-007 ~ CN-VL3-009 | 号段存在性/跨年禁用/联用号码位数                  | ❌ Fatal                 | LEQI |
| VL3 | CN-VL3-010              | 上传时序（开票与上传时间间隔<48h）                | ❌ Fatal                 | LEQI |
| VL3 | CN-VL3-011              | 红字确认单状态校验（红票专属）                    | ❌ Fatal                 | ALL  |
| VL3 | CN-VL3-012 ~ CN-VL3-014 | 开票人/开具方式代码/乐企模式代码                  | ❌ Fatal                 | LEQI |
| VL3 | CN-VL3-015              | 支付即开票场景校验                          | ❌ Fatal                 | LEQI |

**红票场景（InvoiceTypeCode=381）额外规则：**

| 规则层 | 规则 ID | 规则名称 | 严重性 |
|--------|---------|---------|--------|
| VL1 | CN-VL1-020 | 负数发票金额符号 | ❌ Fatal |
| VL3 | CN-VL3-011 | 红字确认单状态校验 | ❌ Fatal |

**不动产经营租赁（SpecialBusinessType="06"）额外规则：**

| 规则层 | 规则 ID | 规则名称 | 严重性 |
|--------|---------|---------|--------|
| VL4 | CN-VL4-001 ~ CN-VL4-003 | 特定业务类型扩展必填/禁填/必填字段 | ❌ Fatal |
| VL4 | CN-VL4-EL-001 ~ CN-VL4-EL-012 | 不动产经营租赁专项（含个体工商户/自然人商编扩展） | ❌/⚠️ |

**MVP 外（暂不实现）：**

| 规则 ID | 说明 |
|---------|------|
| CN-VL2-004 ~ CN-VL2-006 | 差额征税规则 |
| CN-VL4-BD / CN-VL4-FT / CN-VL4-TV | 建筑服务/货物运输/旅客运输 |

### 3.2 规则包外的约束

| 约束类型 | 约束内容 | 处理方式 |
|---------|---------|---------|
| 状态机 Guard | invoice-data.status 须为 S01 或 S02 | HTTP 409，`INVDATA_INVALID_STATE` |
| 服务异常保护 | 校验服务异常时状态保持 S01 | HTTP 500，不产生脏状态 |
| 全量错误收集 | 所有规则跑完后统一返回，不短路 | errors 数组包含全量失败规则 |

### 3.3 执行策略与状态结果

- **规则版本**：由 `ProfileSelectionRules` 命中的 profile 决定，产品侧统一维护。本节 3.1 中的规则信息均来源于该特性关联对象的 RulePackage，仅作快速索引，如有不一致以 RulePackage 为准。
- **按需加载**：VL4 仅在 `SpecialBusinessType` 命中时加载
- **Optional 规则**：CN-VL1-023（自然人证件国籍精确联动）待证件编码映射表完备后升级；CN-VL3-001~006 依赖税局前置信息（纳税人资质/额度），首版作为弱校验不阻断，当外部数据可用时升级为 Fatal

| 执行结果 | 目标状态 | 说明 |
|---------|---------|------|
| 全部 Fatal 通过 | S03（校验成功 / VALIDATED） | 数据锁定，进入 ACT-10 |
| 任一 Fatal 失败 | S02（校验失败 / VALIDATION_FAILED） | 返回错误清单，可修正重提 |
| 仅 Warning 失败 | S03（校验成功） | Warning 不阻断，随错误清单返回 |
| 服务异常 | 保持 S01 | HTTP 500 |

---

## 四、接口规格

### 提交合规校验（ACT-04 / OutInv_Validate_Content）

> 对内平台原子接口，由 ACT-01 创建草稿后串联调用，不直接对外暴露。

**前置条件（Guard）**

- `fullLifecycleStatus` 须为 `S01`（草稿 / DRAFT）或 `S02`（校验失败 / VALIDATION_FAILED）
- 违反时：HTTP 409，错误码 `INVDATA_INVALID_STATE`，响应体含当前状态值

---

### 4.1 请求参数

> ACT-04 以 `invoiceUUID` 为唯一调用入参。`invoiceUUID` 是平台在 ACT-01（创建发票草稿）时生成的对象内部唯一标识，与税局开具成功后返回的发票号码（`Invoice.ID`）不同——后者在 ACT-13（更新开具结果）写回前不存在。平台凭 `invoiceUUID` 从 invoice-data 对象中读取完整发票数据执行校验，调用方无需重复传参。

**调用入参**

| 字段名 | 中文名 | 类型 | 必填 | 说明 |
|--------|--------|------|------|------|
| `invoiceUUID` | 发票平台标识 | String | 是 | invoice-data 平台内部唯一标识（ACT-01 创建时生成，非税局发票号码） |

**平台内部读取字段（校验覆盖范围说明，供开发理解）**

| 字段名 | 中文名 | 类型 | 必填 | 说明 |
|--------|--------|------|------|------|
| `invoiceTypeCode` | 发票类型代码 | String | 是 | 380=正数蓝票，381=负数红票；决定发票方向及金额符号校验（CN-VL1-020） |
| `invoiceCategory` | 发票种类 | String | 是 | 028=数电普票，081=数电专票；影响购方税号必填性（CN-VL1-005）及票种枚举校验（CN-VL1-003） |
| `specialBusinessType` | 特殊业务类型 | String | 否 | 决定是否加载 VL4 规则包；值为"06"（不动产租赁）时触发 CN-VL4-EL 系列 |
| `digitalInvoiceNumber` | 发票号码 | String(20) | 是 | 20位纯数字；号码格式由通道保障，平台无需校验 |
| `issueDate` | 开票日期 | DateTime | 是 | 格式 yyyy-MM-dd HH:mm:ss（CN-VL1-010，❌ Fatal，格式 yyyy-MM-dd HH:mm:ss） |
| `accountingSupplierParty.party.partyTaxScheme.companyID` | 销方纳税人识别号 | String(20) | 是 | 不得为空；最大20位，数字+大写字母（CN-VL1-004/009） |
| `accountingSupplierParty.party.partyName.name` | 销方名称 | String | 是 | 不得为空；乐企最大300字符，电子税局最大150字符（CN-VL1-004/012） |
| `accountingSupplierParty.party.postalAddress.streetName` | 销方地址 | String | 是 | 不得为空（CN-VL1-004） |
| `accountingSupplierParty.party.financialAccount.id` | 销方银行账号 | String | 是 | 不得为空（CN-VL1-004） |
| `accountingCustomerParty.party.partyTaxScheme.companyID` | 购方纳税人识别号 | String(20) | 条件必填 | 专票（081）时必填；普票（028）时可为空；特定业务类型16（农产品收购）时必填（CN-VL1-005） |
| `accountingCustomerParty.party.partyName.name` | 购方名称 | String | 是 | 不得为空；乐企最大300字符，电子税局最大150字符（CN-VL1-005/012） |
| `invoiceLine[i].index` | 明细序号 | Integer | 是 | 从1开始，乐企通道必填（CN-VL1-007） |
| `invoiceLine[i].item.name` | 货物或应税劳务名称 | String(117) | 是 | 格式 `*简称*项目名称`，简称+两个*限17字符，项目名称限100字符，总长限117字符（CN-VL1-007） |
| `invoiceLine[i].taxClassificationCode` | 商品编码 | String(19) | 是 | 19位数字编码，须在商品编码表中存在（CN-VL1-007/VL2-002）；6开头须为不征税（CN-VL2-014） |
| `invoiceLine[i].taxRate` | 明细行税率 | Decimal | 是 | 须为合法税率：13%/9%/6%/5%/3%/1.5%/1%/0%（CN-VL2-001） |
| `invoiceLine[i].lineExtensionAmount` | 明细行不含税金额 | Decimal | 是 | 整数部分最大18位，保留2位小数（CN-VL1-011）；蓝票>0（除折扣行），红票<0（CN-VL1-020） |
| `invoiceLine[i].taxAmount` | 明细行税额 | Decimal | 是 | \|不含税金额×税率 - 税额\| ≤ 0.06（乐企）/ ≤ 0.01（电子税局，折扣行）（CN-VL1-018）；蓝票≥0，红票≤0（CN-VL1-020） |
| `invoiceLine[i].quantity` | 数量 | Decimal | 否 | 数量和单价须同时为空或同时不为空（CN-VL1-014）；整数位+小数位最大16位，小数位最多13位（CN-VL1-011） |
| `invoiceLine[i].price` | 单价 | Decimal | 否 | 同上；\|单价×数量 - 金额\| ≤ 0.01（CN-VL1-015） |
| `invoiceLine[i].discountType` | 行类型（折扣标志） | String | 是 | "1"=折扣行；折扣行须紧邻被折扣行，税率须一致，税收分类编码须与被折扣行一致（CN-VL1-021） |
| `invoiceLine[i].taxExemptionReasonCode` | 免税类型代码 | String | 条件必填 | 含免税/不征税行时必填；须为合法枚举值"01"~"18"（CN-VL2-003） |
| `invoiceLine[i].taxExemptionReason` | 免税原因说明 | String | 条件必填 | 含免税/不征税行时填写（CN-VL2-003） |
| `invoiceLine[i].realEstateInfo.address` | 不动产地址（省市区县+详细地址） | String(120) | 条件必填 | SpecialBusinessType="06"时必填；详细地址须含"街/路/村/乡/镇/道"关键词（CN-VL4-EL-004） |
| `invoiceLine[i].realEstateInfo.estateId` | 不动产权证号 | String | 条件必填 | SpecialBusinessType="06"时必填；无证书填"无"（CN-VL4-EL-003） |
| `invoiceLine[i].realEstateInfo.leaseStartDate` | 租赁期起 | String | 条件必填 | SpecialBusinessType="06"时必填；格式 yyyyMMddHHmm（CN-VL4-EL-005） |
| `invoiceLine[i].realEstateInfo.leaseEndDate` | 租赁期止 | String | 条件必填 | SpecialBusinessType="06"时必填；须晚于租赁期起（CN-VL4-EL-005） |
| `invoiceLine[i].realEstateInfo.crossCitySign` | 跨地市标志 | String | 条件必填 | SpecialBusinessType="06"时必填；取值"1"或"0"（CN-VL4-EL-006） |
| `invoiceLine[i].realEstateInfo.areaUnit` | 面积单位 | String | 条件必填 | SpecialBusinessType="06"时必填（CN-VL4-EL-007） |
| `taxTotal.taxAmount` | 发票税额合计 | Decimal | 是 | = 所有行 TaxAmount 之和；\|Σ(各行金额×税率) - 税额合计\| ≤ 1.27（CN-VL1-019） |
| `legalMonetaryTotal.taxExclusiveAmount` | 不含税金额合计 | Decimal | 是 | = 所有商品行金额之和，误差 ≤ 0.01（CN-VL1-016） |
| `legalMonetaryTotal.taxInclusiveAmount` | 含税金额合计（价税合计） | Decimal | 是 | = 合计金额 + 合计税额，误差 ≤ 0.01（CN-VL1-017） |
| `note` | 备注 | String | 否 | 蓝票最大450字符，红票最大382字符（CN-VL1-012）；差额征税蓝票须含"差额征税：xx.xx"（CN-VL2-005） |
| `naturalPersonFlag` | 自然人标志 | String | 否 | 非"Y"时自然人证件类型/号码/国籍须同时为空（CN-VL1-022）；"Y"时购方名称长度须>1字符 |
| `agentUser` | 开票人 | String | 是 | 必填（CN-VL1-025）；乐企通道须与配置的开票员信息一致（CN-VL3-012） |

---

### 4.2 响应规格

**校验通过（S01 → S03）**

| 字段名 | 中文名 | 类型 | 说明 |
|--------|--------|------|------|
| `invoiceUUID` | 发票平台标识 | String | invoice-data 平台内部唯一标识 |
| `fullLifecycleStatus` | 生命周期状态 | String | `S03`（校验成功 / VALIDATED） |
| `validationResult` | 校验结论 | String | `PASS` |
| `profileID` | 命中 Profile | String | 命中的规则包标识，如 `CN-LEQI` |
| `validatedAt` | 校验完成时间 | String (ISO8601) | 校验完成时间 |

**校验失败（S01 → S02）**

| 字段名 | 中文名 | 类型 | 说明 |
|--------|--------|------|------|
| `invoiceUUID` | 发票平台标识 | String | invoice-data 平台内部唯一标识 |
| `fullLifecycleStatus` | 生命周期状态 | String | `S02`（校验失败 / VALIDATION_FAILED） |
| `validationResult` | 校验结论 | String | `FAIL` |
| `profileID` | 命中 Profile | String | 命中的规则包标识 |
| `validatedAt` | 校验完成时间 | String (ISO8601) | 校验完成时间 |
| `errors` | 错误清单 | Array | 全量返回所有失败规则（不短路） |
| `errors[i].code` | 规则错误码 | String | 精确到子规则，如 `CN-VL1-018` |
| `errors[i].field` | 出错字段路径 | String | 如 `invoiceLine[0].taxAmount` |
| `errors[i].message` | 错误描述 | String | 错误描述（中文） |

**前置条件违反（HTTP 409）**

| 字段名 | 中文名 | 类型 | 说明 |
|--------|--------|------|------|
| `invoiceUUID` | 发票平台标识 | String | invoice-data 平台内部唯一标识 |
| `errorCode` | 错误码 | String | `INVDATA_INVALID_STATE` |
| `fullLifecycleStatus` | 当前状态 | String | 当前实际状态码，如 `S03` |
| `message` | 错误信息 | String | `当前发票状态不允许执行合规校验` |

**服务异常（HTTP 500）**

| 字段名 | 中文名 | 类型 | 说明 |
|--------|--------|------|------|
| `invoiceUUID` | 发票平台标识 | String | invoice-data 平台内部唯一标识 |
| `errorCode` | 错误码 | String | `VALIDATION_SERVICE_ERROR` |
| `message` | 错误信息 | String | `校验服务异常，发票状态未变更，请稍后重试` |

---

### 4.3 响应示例

**校验通过（S01 → S03）**

```json
{
  "invoiceUUID": "uuid-2026-00001",
  "fullLifecycleStatus": "S03",
  "validationResult": "PASS",
  "profileID": "CN-LEQI",
  "validatedAt": "2026-03-16T10:00:00Z"
}
```

**校验失败（S01 → S02）**

```json
{
  "invoiceUUID": "uuid-2026-00002",
  "fullLifecycleStatus": "S02",
  "validationResult": "FAIL",
  "profileID": "CN-LEQI",
  "validatedAt": "2026-03-16T10:00:01Z",
  "errors": [
    {
      "code": "CN-VL4-EL-004",
      "field": "invoiceLine[0].realEstateInfo.address",
      "message": "不动产经营租赁发票：具体地址须包含街、路、村、乡、镇、道等关键词"
    },
    {
      "code": "CN-VL1-018",
      "field": "invoiceLine[1].taxAmount",
      "message": "行税额计算误差超出允许范围（|不含税金额×税率 - 税额| 须 ≤ 0.06 元）"
    }
  ]
}
```

**前置条件违反（HTTP 409）**

```json
{
  "invoiceUUID": "uuid-2026-00003",
  "errorCode": "INVDATA_INVALID_STATE",
  "fullLifecycleStatus": "S03",
  "message": "当前发票状态不允许执行合规校验"
}
```

**服务异常（HTTP 500）**

```json
{
  "invoiceUUID": "uuid-2026-00004",
  "errorCode": "VALIDATION_SERVICE_ERROR",
  "message": "校验服务异常，发票状态未变更，请稍后重试"
}
```

---

## 五、地区差异说明

| 维度 | CN-LEQI | 其他地区 |
|------|---------|---------|
| 规则包 | CN_RulePackage_v2.0.3-beta（VL1~VL4，70条） | 各地区独立规则包 |
| 税率范围 | 13%/9%/6%/5%/3%/1.5%/1%/0% | 视地区而定 |
| 行业专项 | 不动产租赁（VL4-EL）为 MVP 内 | 视地区而定 |
| 减按征税 | 支持5%简易征收减按1.5%及3%简易征收减按1.5%两种场景 | 视地区而定 |

---

## 六、附录：产品本体对应实现关系

### 6.1 本体映射

| 本体概念 | 具体值 | 说明 |
|---------|--------|------|
| 对象 | invoice-data | 销项发票数据 |
| 动作 | ACT-04 / OutInv_Validate_Content | 提交合规校验 |
| Guard | S01（草稿）/ S02（校验失败） | |
| Effect | S03（校验成功）/ S02（校验失败） | |
| 规则路由 | ProfileSelectionRules → CN-LEQI | |
| 校验执行 | Profile.Validate(CN-LEQI) → RulePackage.CN-LEQI | |

### 6.2 执行函数链

```
入参：invoice_uuid
  ↓
读取 invoice-data 对象
  → Guard 检查：status ∈ {S01, S02}
  → 不满足：返回 HTTP 409，INVDATA_INVALID_STATE
  ↓
ProfileSelectionRules（FN-INVDATA-000）
  → 输入：InvoiceTypeCode / InvoiceCategory / SpecialBusinessType
         Party(AccountingSupplierParty).PostalAddress.Country
         Party(AccountingSupplierParty).Extension.CN.ChannelType
  → 命中 CN-LEQI
  ↓
Profile.Validate(CN-LEQI)（FN-INVDATA-010）
  → ValidateBaseCompleteness（FN-INVDATA-201）
  → RulePackage.CN-LEQI：
      VL1 CN-VL1-002~025    必跑（CN-VL1-022 Warning）
      VL2 CN-VL2-001~014    必跑（CN-VL2-004~006 MVP外）
      VL3 CN-VL3-001~015    必跑（CN-VL3-001~006 Optional（弱校验））
      VL4 CN-VL4-EL-001~012 按需加载（SpecialBusinessType="06"）
  → 收集全量错误（不短路）
  ↓
WriteValidationReport（FN-INVDATA-202）
  → 写入校验报告引用至 AdditionalDocumentReference
  ↓
WriteAuditLog
  ↓
状态写回：
  全部 Fatal 通过 → S03（校验成功 / VALIDATED）
  任一 Fatal 失败 → S02（校验失败 / VALIDATION_FAILED）
  服务异常 → 保持 S01，HTTP 500
```

### 6.3 本体文档引用索引

| 类型 | 文档路径 | 索引位置 | 本体状态 |
|------|---------|---------|---------|
| 对象定义 | invd_01_Properties.md | invoice-data 对象 | ✅ |
| 动作定义 | invd_04_ActionTypes.md | ACT-04 提交合规校验（OutInv_Validate_Content） | ✅ |
| 函数定义 | invd_05_Functions/invd_05.0_Functions.md | FN-INVDATA-000/010/201/202 | ✅ |
| 校验规则 | invd_05.1_CN-LEQI_RulePackage.md（v2.0.3-beta） | VL1~VL4 全量规则（70条） | ✅ |
| 状态定义 | invd_03_ValueSets.md | S01（草稿）/ S02（校验失败）/ S03（校验成功） | ✅ |

### 6.4 本体待补充清单

暂无
