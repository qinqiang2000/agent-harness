# 字段与枚举速查表

分析日志时，遇到不确定含义的字段或枚举值，先查此表。查不到再去源码定位。

---

## api-elc-invoice-lqpt：抵扣勾选 / 撤销勾选

### `authenticateFlag` 
| 值 | 含义 |
|---|---|
| `0` | 未勾选/撤销勾选（勾选操作） |
| `1` | 已勾选/抵扣勾选（勾选操作） |
| `2` | 已认证 |

> **注意**：用户描述的操作类型与日志中的实际值可能不一致，必须以日志为准。

---

### `gxzt`（勾选状态，用于航信预查询参数和税局的勾选状态）

| 值 | 含义 |
|---|---|
| `0` | 未勾选/查询**未勾选**发票列表 |
| `1` | 已勾选/查询**已勾选**发票列表 |


---

### `selectResult`

| 值 | 含义 |
|---|---|
| `1` | 操作成功 |
| `2` | 操作失败 |

---

## 通用字段

### `invoiceStatus`（发票状态，通用）

| 值 | 含义 |
|---|---|
| `0` | 正常 |
| `2` | 作废 |
| `3` | 红冲 |
| `4` | 异常 |
| `5` | 蓝冲 |
| `7` | 部分红冲 |
| `8` | 全额红冲 |

---

### `accountStatus`（入账状态）

| 值 | 含义 |
|---|---|
| `01` | 未入账 |
| `02` | 已入账 |
| `03` | 已勾选 |
| `06` | 已退回 |

---

### `isDxCheck`（查验供应商路由）

| 值 | 供应商 |
|---|---|
| `1` | 大象慧云 |
| `4` | 长软（主要） |
| `5` | 公有云 |
| `6` | 账无忧 |
| `7` | 微乐 |
| `8` | 宁波港 |
| `9` | 大象慧云航信 |
| 默认 | 互金 |

---

> 如需新增条目，按服务分组追加，注明字段来源（类名:行号）。

---

## 发票类型字段关联（invoiceType / govInvoiceType）

来源：`api-elc-invoice-lqpt / com.kingdee.enums.channels.mengbai.MbInvoiceTpyeEnum`

> `invoiceType` 是发票云内部类型值，`govInvoiceType`（税局字段名 `fplx`）是税局发票类型代码。一个 `invoiceType` 可能对应多个 `govInvoiceType`（纸质/电子两种形态）。

| invoiceType | govInvoiceType (fplx) | 枚举名 | 描述 |
|---|---|---|---|
| -1 | -1 | UNKNOWN_TYPE | 不支持的票种 |
| 1 | 10 | ORDINARY_ELECTRONIC_INVOICE | 普通电子发票 |
| 2 | 08 | ELECTRONIC_INVOICE | 电子专用发票 |
| 3 | 04 | PLAIN_PAPER_INVOICE | 普通纸质发票 |
| 3 | 86 | PLAIN_PAPER_INVOICE_ELC | 普通纸质发票（电子） |
| 4 | 01 | SPECIAL_PAPER_INVOICE | 专用纸质发票 |
| 4 | 85 | SPECIAL_PAPER_INVOICE_ELC | 专用纸质发票（电子） |
| 5 | 11 | ORDINARY_PAPER_ROLL_INVOICE | 普通纸质卷票 |
| 7 |  | GENERAL_MACHINE_PRINTED_INVOICE | 通用机打发票 |
| 8 |  | TAXI_INVOICE | 的士票 |
| 9 |  | TRAIN_INVOICE | 火车票 |
| 10 |  | AIR_INVOICE | 飞机票 |
| 11 |  | OTHER_INVOICE | 其他票 |
| 12 | 03 | MOBILE_INVOICE | 机动车票 |
| 12 | 87 | MOBILE_INVOICE_ELC | 机动车票（电子） |
| 13 | 15 | USED_INVOICE | 二手车票 |
| 13 | 88 | USED_INVOICE_ELC | 二手车票（电子） |
| 14 |  | QUOTA_INVOICE | 定额发票 |
| 15 | 14 | TOLL_INVOICE | 通行费发票 |
| 16 |  | PASSENGER_TRANSPORT_INVOICE | 客运发票 |
| 17 |  | CROSS_INVOICE | 过路过桥费 |
| 18 |  | VEHICLE_AND_VESSEL_TAX_INVOICE | 车船税发票 |
| 19 |  | DUTY_PAID_PROOF | 完税证明 |
| 20 |  | SHIP_TICKET_INVOICE | 轮船票 |
| 21 | 17 | CUSTOMS_DEMAND_NOTE | 海关缴款书 |
| 23 |  | GENERAL_MACHINE_PRINTED_ELECTRONIC_INVOICE | 通用机打电子 |
| 24 |  | TRAIN_TICKET_REFUND_CERTIFICATE | 火车票退票凭证 |
| 25 |  | FINANCIAL_ELECTRONIC_BILL | 财政电子票据 |
| 26 | 82 | ALL_ELECTRIC_TICKET | 数电票（普通发票） |
| 27 | 81 | ALL_ELECTRIC_SPECIAL_TICKET | 数电票（增值税专用发票） |
| 28 | 61 | ELE_AIR_INVOICE | 数电票（航空运输电子客票行程单） |
| 29 | 51 | ELE_TRAIN_INVOICE | 数电票（铁路电子客票） |
| 30 |  | OVERSEA_INVOICE | 形式发票 |
| 72 | 8208 | ELC_ELECTRONIC_INVOICE | 数电发票（通行费发票） |

---

## 发票状态字段关联（invoiceStatus / fpzt）

来源：`api-elc-invoice-lqpt / com.kingdee.enums.InvoiceStatusEnum`

> `invoiceStatus` 是发票云内部状态值，`fpzt` 是税局发票状态代码（对应枚举中的 `mbStatus`）。

| invoiceStatus | fpzt (mbStatus) | 枚举名 | 描述 |
|---|---|---|---|
| 0 | 01 | NORMAL | 正常 |
| 2 | 02 | CANCEL | 作废 |
| 7 | 04 | PARTIAL_RED_WASH | 部分红冲 |
| 8 | 03 | FULL_RED_WASH | 全额红冲 |

---

### `clientsType` / `channelType`（客户端类型）

来源：`com.kingdee.enums.ClientsTypeEnum`

| clientsType | channelType | 描述      |
|-------------|-------------|---------|
| 1           | 0           | 本地全电客户端 |
| 2           | 0           | 本地税盘客户端 |
| 3           | 0           | 云化全电客户端 |
| 4           | 4           | 乐企      |
| 9           | 9           | 航信      |

---

### `statistics` / `resType`（统计申请状态）

来源：`com.kingdee.enums.StatisticsEnum`

| statistics | resType | 描述 |
|---|---|---|
| 0 | 01 | 未申请统计 |
| 4 | 02 | 已申请，待确认 |
| 6 | 05 | 已申请，已确认 |

---

## api-elc-digital-invoice：数电发票

### `createInvoiceStatus` / `lastStatus`（开票状态）

来源：`com.kingdee.enums.CreateInvoiceStatusEnum`

| createInvoiceStatus | lastStatus | 描述 |
|---|---|---|
| -1 | 4 | 开票失败 |
| 0 | null | 初始/待入队 |
| 1 | 0 | 待消费 |
| 2 | 4 | 失败待重试 |
| 3 | 4 | 开票成功 |
| 4 | 1 | 已消费 |
| 5 | 4 | 异步开票中 |

---

### `invoiceInputDateType` / `qxyType`（发票输入方向）

来源：`com.kingdee.enums.InvoiceInputDateTypeEnum`

| invoiceInputDateType | qxyType | 描述 |
|---|---|---|
| 1 | jx | 收票（进项） |
| 2 | xx | 开票（销项） |

---

## api-elc-invoice-engine：发票引擎

### `invoiceRequestStatus` / `status`（开票请求状态）

来源：`com.kingdee.fpy.enums.InvoiceRequestStatus`

| invoiceRequestStatus | status | 描述 |
|---|---|---|
| 1 | Draft | 草稿 |
| 2 | Enriching | 补全中 |
| 3 | Validated | 已校验 |
| 4 | ValidFailed | 校验失败 |
| 5 | Pending | 待审核 |
| 6 | InvoiceIssueing | 开票中 |
| 7 | PartInvoiced | 部分开票 |
| 8 | FullyInvoiced | 完全开票 |
| 9 | DebitApply | 借记申请 |
| 10 | ReIssued | 重新签发 |

---

### `invoiceStatus` / `value`（发票引擎发票状态）

来源：`com.kingdee.fpy.enums.InvoiceStatus`

> 注意：此为发票引擎内部状态，与 `InvoiceStatusEnum` 不同。

| invoiceStatus | value | 描述 |
|---|---|---|
| 1 | InvoiceReady | 发票就绪 |
| 2 | Reporting | 税局上报中 |
| 3 | Reported | 已上报税局 |
| 4 | ReportFailed | 上报税局失败 |
| 5 | Delivering | 交付中 |
| 6 | Delivered | 已交付 |
| 7 | DeliverFailed | 交付失败 |

---

## api-elc-invoice-lqly：乐企开票

### `lqDiscountType` / `fphxz`（发票行性质）

来源：`com.kingdee.enums.LqDiscountTypeEnum`

| lqDiscountType | fphxz | 描述 |
|---|---|---|
| 0 | 00 | 正常行（数电普） |
| 1 | 01 | 折扣行（数电专） |
| 2 | 02 | 被折扣行（数电专） |

---

### `invoiceTaskStatus`（乐企开票任务状态）

来源：`com.kingdee.enums.InvoiceTaskStatusEnum`

| 值 | 描述 |
|---|---|
| -1 | 开票确定失败 |
| 0 | 开票成功（PDF/OFD/XML 已生成） |
| 1 | 初始化未赋码 |
| 2 | 赋码失败 |
| 3 | 已赋码未上传 |
| 4 | 已赋码，上传税局返回成功 |
| 5 | 已赋码，上传税局返回明确失败 |
| 6 | 已赋码，上传税局返回不明确失败（会自动重试） |
| 7 | 已赋码，查询上传结果返回上传成功（文件未生成完） |
| 8 | 已赋码，查询上传结果返回明确失败 |
| 9 | 已赋码，查询上传结果返回重复上传 |