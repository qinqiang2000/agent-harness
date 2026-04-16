# 网关路由配置

> 来源：Spring Cloud Gateway 配置文件
> 用途：根据接口 URL 前缀查找对应的后端服务名，再通过 service-repo-map.md 找到 GitLab 仓库

## 查询方法

给定接口路径（如 `/m3/bill/invoice/verify`），按以下步骤匹配：
1. 找到路径前缀匹配的路由（如 `/m3/**` → `api-invoice-frame`）
2. 用服务名查 [service-repo-map.md](service-repo-map.md) 获取 GitLab project_id
3. 注意：路由 52（`/**`）是兜底路由，匹配所有未命中的路径，服务为 `erp`

## 路由表

| URL 前缀 | 服务名 | 路由 ID |
|---|---|---|
| /base/download/** | base-file-center | oss |
| /doc/** | base-file-center | doc |
| /portal/org/** | bill-organization | portal-org |
| /portal/account/** | bill-account-statement | portal-account |
| /polling/fpzs/** | api-push-service | polling |
| /portal/platform/** | bill-portal | portal-platform |
| /portal/bm/** | bill-bm-ocr-invoice | portal-bm |
| /m14/** | bill-input-account-manage-portal | m14 |
| /m15/** | bill-input-account-wechat-applet-portal | m15 |
| /m16/** | api-invoice-pdf-analysis | m16 |
| /m17/** | bill-portal-h5 | m17 |
| /base_cosmic/** | base-cosmic-init | base-cosmic-init |
| /portal/m19/** | bill-operate-report | m19 |
| /file/** | api-invoice-input-query | pdffile |
| /public/** | api-invoice-pdf | publicfile |
| /m22/** | NODE-DOC-VIEW | node22 |
| /m23/**, /m2/**, /m3/**, /m5/**, /m6/**, /m7/**, /jichu/**, /m18/**, /m13/** | api-invoice-frame | foreign |
| /m25/** | base-order | portal-order |
| /m26/** | base-iam | m26 |
| /m28/** | api-invoice-erp-client | m28 |
| /base/** | base | base |
| /m1/** | api-company | m1 |
| /m4/**, /m4-web/** | fpzs | m4 |
| /m8/** | bill-business-cms | m8 |
| /m9/** | api-invoice-manage | m9 |
| /m10/** | wechat-mini-program | m10 |
| /m11/** | api-hotel | m11 |
| /m12/** | bill-expense | m12 |
| /nlp_service/match/file | base-ai-file-cls | base-ai-file-cls |
| /archive/** | api-archive | archive |
| /archivebase/** | api-archive-organization | archivebase |
| /imgsys/** | api-archive-scan | scan |
| /archive-job-admin/** | api-archive-job | job |
| /archive-sentinel-dashboard/** | archive-sentinel-dashboard | sentinel |
| /trdPlatform/** | base-platform-adapter | trdPlatform |
| /lqpt/callback/** | api-elc-invoice-lqpt | api-elc-invoice-lqpt |
| /archive_license/** | api-archive-license | license |
| /financial/** | fpy-app-financial-client | financial |
| /etax-bill/fpdk/**, /etax-bill/invoice/**, /etax-bill/lqimp/**, /etax-bill/customs/**, /etax-bill/export-rebate/**, /etax-bill/farm-product/**, /etax-bill/increment/**, /etax-bill/inside/**, /etax-bill/lq/**, /etax-bill/moven/**, /etax-bill/withhold/**, /etax-bill/tax-invoice-pool/** | api-elc-digital-invoice | api-elc-digital-invoice |
| /bill-websocket/**, /etax-bill/** | bill-websocket | bill-websocket |
| /bak-online-view/** | online-view-sit.piaozone.com（外部） | office-view |
| /ai/knowledge/** | base-ai-portal | base-ai-portal |
| /base-ai-llm/nlpService/overseaInvoice/extraction, /base-ai-llm/nlpService/document/analyze | base-ai-llm | base-ai-llm |
| /base-ai-data-match/nlpService/item/match | base-ai-data-match | base-ai-data-match |
| /base-ai-python/nlp_service/match/** | base-ai-python | base-ai-python |
| /rpa/** | api-invoice-data-collector | rpa |
| /gjfp/** | api-elc-invoice-gjfp | gjfp |
| /fpy-query/** | fpy-base-query | fpy-base-query |
| /xm-demo/** | api-elc-invoice-engine | api-elc-invoice-engine |
| /monitor/** | base-monitor-collect | base-monitor-collect |
| /partners/** | fpy-isv | fpy-isv |
| /dop/** | fpy-ar-invoice-ontology | fpy-ar-invoice-ontology |
| /** （兜底） | erp | erp |

## 常用路径速查

| 业务场景 | 典型路径前缀 | 服务名 |
|---|---|---|
| 开票（发票开具） | /m3/**, /m2/**, /m5/**, /m6/**, /m7/** | api-invoice-frame |
| 收票（进项发票） | /m9/** | api-invoice-manage |
| 查验 | /m3/bill/invoice/sys/check, /portal/platform/checkinvoice/** | api-invoice-frame, bill-portal |
| 数电发票 | /etax-bill/** | api-elc-digital-invoice 或 bill-websocket |
| 进项采集 | /rpa/** | api-invoice-data-collector |
| 鉴权/IAM | /m26/** | base-iam |
| 企业信息 | /m1/** | api-company |
| 文件/PDF | /file/**, /public/**, /doc/** | api-invoice-input-query, api-invoice-pdf, base-file-center |
| 归档 | /archive/**, /archivebase/** | api-archive, api-archive-organization |
