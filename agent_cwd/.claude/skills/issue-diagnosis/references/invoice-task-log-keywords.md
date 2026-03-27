# 进项发票采集任务 — 接口入口日志查询关键字

> 规则：有 batchNo 优先使用 batchNo，无 batchNo 则使用 taxNo

---

## 使用方法

1. 根据用户描述的操作类型，匹配下方表格中对应的日志关键字
2. 将关键字填入 `searchWordList`，同时加入 `batchNo` 或 `taxNo`
3. 查到入口日志后，提取该条日志的 `id`（即 traceid），再用 `traceid` + `projectList` 包含 'api-elc-invoice-lqpt' 'api-elc-digital-invoice'查完整调用链,查到有日志后无需再查询任何日志了

---

## InvoiceInputController (`/rpa/fpdk`)

| 接口作用 | 日志关键字 |
|---------|-----------|
| 代扣代缴完税凭证查询 | `voucherHeaderApply` and 任务batchNo |
| 代扣代缴完税凭证勾选 | `voucherCheckApply` and 任务batchNo |
| 代扣代缴完税凭证已认证查询 | `voucherConfirmedQuery` and 任务batchNo |
| 出口退税表头查询 | `tsgxQueryInvoices` and taxNo |
| 历史已退税或已勾选发票查询 | `tsgxQueryHistoryInvoices` and taxNo |
| 一键统计 | `scdktjbb` and 任务batchNo |
| 确认统计 | `gxConfirm` and 任务batchNo |
| 取消统计 | `qxdktjbb` and 任务batchNo |
| 统计查询 | `wqtjcx` and 任务batchNo |
| 勾选发票表头查询 | `queryInvoices` and 任务batchNo |
| 抵扣表头采集 | `invoiceDeductionHeaderApply` and 任务batchNo |
| 已勾选和历史已抵扣已认证发票查询 | `ygxInvoices` and taxNo |
| 获取税款所属期 | `getSkssq` and taxNo |
| 勾选和撤销勾选 | `gxInvoices` and 任务batchNo |
| 出口退税勾选 | `tsgx gxInvoices` and 任务batchNo |
| 出口退税用途确认 | `tsgx tsytComfirm` and 任务batchNo |
| 出口退税统计查询 | `tsgx querytsytb` and 任务batchNo |
| 发票勾选（抵扣/不抵扣/退税） | `invoiceDeductionCheck` and 任务batchNo |
| 进项发票下载 | `invoice download` and taxNo |
| 不抵扣勾选 | `bdkGxInvoices` and 任务batchNo |
| 海关缴款书表头查询 | `queryCustomBill` and 任务batchNo |
| 海关缴款书抵扣表头采集 | `customsDeductionHeaderApply` and 任务batchNo |
| 全量发票查询 | `queryFullInvoices` and 任务batchNo |
| 海关缴款书全量采集（异步） | `customsFullQuery` and 任务batchNo |
| 海关缴款书全量采集（同步） | `customsFullSyncApply` and 任务batchNo |
| 海关缴款书勾选 | `gxCustoms` and 任务batchNo |
| 发票未确认状态查询 | `invoiceStatusQuery` and 任务batchNo |
| 海关缴款书手动录入申请 | `manualCustomsPaymentEntryApply` and 任务batchNo |
| 海关缴款书采集申请 | `customsPaymentCollectionApply` and 任务batchNo |

---

## EntryMarkController (`/etax-bill/invoice/entry/mark`)

| 接口作用 | 日志关键字 |
|---------|-----------|
| 入账状态申请 | `EntryMark submit apply` and 任务batchNo |
| 发票入账状态查询 | `EntryMark query` and taxNo |
| 发票入账状态更新 | `EntryMark update` and 任务batchNo |

---

## FarmProductController (`/etax-bill/farm-product/invoice`)

| 接口作用 | 日志关键字 |
|---------|-----------|
| 待处理农产品发票查询 | `farmProductInvoiceProcessingQuery` and taxNo |
| 农产品加计扣除发票查询 | `farmProductInvoiceAddDeductingQuery` and taxNo |
| 待处理农产品发票勾选 | `farmProcessingCheck` and 任务batchNo |
| 农产品加计扣除发票勾选 | `farmAddDeductCheck` and 任务batchNo |

---

## 二次 traceid 查询流程

1. 用关键字查到入口日志后，记录该条日志的 `id`（即 traceid）
2. 用该 traceid 再次调用 `mcp__elastic__searchTraceOrKeyWordsLog`，查完整调用链
3. 分析完整链路中的日志，定位根因
