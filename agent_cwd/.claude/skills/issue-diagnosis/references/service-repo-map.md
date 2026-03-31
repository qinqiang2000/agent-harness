# 服务名 → GitLab 仓库映射

日志中 `fields.project` 打印的服务名与 GitLab 实际仓库路径可能不一致，查此表获取正确的 `project_id`。

**GitLab Base URL**: `https://test-master.piaozone.com/git/`，clone 地址格式：`https://token:$GITLAB_TOKEN@test-master.piaozone.com/git/{project_id}.git`

| 日志服务名 (fields.project) | GitLab 仓库路径 (project_id) |
|---|---|
| smkp | piaozone/output/bill-smkp |
| api-invoice-frame | piaozone/base/api-invoice-frame |
| api-invoice-data-collector | piaozone/base/api-invoice-data-collector |
| api-invoice-order | piaozone/base/api-invoice-order |
| api-invoice-pdf | piaozone/base/api-invoice-pdf |
| api-invoice-ofdfile | piaozone/base/api-invoice-ofdfile |
| api-auth | piaozone/base/api-auth |
| api-storage | piaozone/base/api-storage |
| api-simulate | piaozone/base/api-simulate |
| api-express | piaozone/base/api-express |
| api-bdkp | piaozone/base/api-bdkp |
| api-kds | piaozone/base/api-kds |
| api-pdf-analysis | piaozone/base/api-pdf-analysis |
| api-service-timer | piaozone/base/api-service-timer |
| api-company | piaozone/base/api-company |
| api-cost-calculation | piaozone/base/api-cost-calculation |
| api-exception-report | piaozone/base/api-exception-report |
| api-base-operation | piaozone/base/api-base-operation |
| api-mcp-frame | piaozone/base/api-mcp-frame |
| api-mcp-server | piaozone/base/api-mcp-server |
| api-invoice-check | piaozone/input/api-invoice-check |
| api-invoice-collector | piaozone/input/api-invoice-collector |
| api-invoice-recognition | piaozone/input/api-invoice-recognition |
| api-invoice-input-db | piaozone/input/api-invoice-input-db |
| api-invoice-input-query | piaozone/input/api-invoice-input-query |
| api-invoice-input-query-v2 | piaozone/input/api-invoice-input-query-v2 |
| api-fpzs | piaozone/input/api-fpzs |
| api-expense | piaozone/input/api-expense |
| api-invoice-manage | piaozone/input/api-invoice-manage |
| api-invoice-image | piaozone/input/api-invoice-image |
| api-invoice-ofd-analysis | piaozone/input/api-invoice-ofd-analysis |
| api-invoice-pdf-analysis | piaozone/input/api-invoice-pdf-analysis |
| api-invoice-check-noencrypt | piaozone/input/api-invoice-check-noencrypt |
| api-invoice-check-util | piaozone/input/api-invoice-check-util |
| api-invoice-erp-client | piaozone/input/api-invoice-erp-client |
| api-invoice-deduction-adapter | piaozone/input/api-invoice-deduction-adapter |
| api-msg-parser-utils | piaozone/input/api-msg-parser-utils |
| api-push-socket | piaozone/input/api-push-socket |
| api-push-service | piaozone/input/api-push-service |
| api-account | piaozone/input/api-account |
| api-socketio-server | piaozone/input/socketio/api-socketio-server |
| api-socketio-client | piaozone/input/socketio/api-socketio-client |
| api-socketio-webclient | piaozone/input/socketio/api-socketio-webclient |
| api-invoice-create | piaozone/output/api-invoice-create |
| api-invoice-output-query | piaozone/output/api-invoice-output-query |
| api-invoice-sm | piaozone/output/api-invoice-sm |
| api-company-search | piaozone/output/api-company-search |
| api-hotel | piaozone/output/api-hotel |
| api-interface | piaozone/output/api-interface |
| api-invoice-input-utils | piaozone/common/api-invoice-input-utils |
| api-invoice-utils | piaozone/common/api-invoice-utils |
| api-ofd-utils | piaozone/common/api-ofd-utils |
| api-pdf-utils | piaozone/common/api-pdf-utils |
| api-xbrl-utils | piaozone/common/api-xbrl-utils |
| api-aws-s3 | piaozone/common/api-aws-s3 |
| api-signature-utils | piaozone/common/api-signature-utils |
| api-database-utils | piaozone/common/api-database-utils |
| api-elc-digital-invoice | piaozone/elc-integration/api-elc-digital-invoice |
| api-elc-invoice-lqpt | piaozone/elc-integration/api-elc-invoice-lqpt |
| api-elc-invoice-create | piaozone/elc-integration/api-elc-invoice-create |
| api-elc-invoice-collect | piaozone/elc-integration/api-elc-invoice-collect |
| api-elc-invoice-utils | piaozone/elc-integration/api-elc-invoice-utils |
| api-elc-invoice-gjfp | piaozone/elc-integration/api-elc-invoice-gjfp |
| api-elc-invoice-lqly | piaozone/elc-integration/api-elc-invoice-lqly |
| api-elc-invoice-imputation | piaozone/elc-integration/api-elc-invoice-imputation |
| api-elc-invoice-engine | piaozone/elc-integration/api-elc-invoice-engine |
| api-gateway | piaozone/imgsys-archive/api-gateway |
| api-archive | piaozone/imgsys-archive/api-archive |
| api-archive-scan | piaozone/imgsys-archive/api-archive-scan |
| api-archive-scan-move | piaozone/imgsys-archive/api-archive-scan-move |
| api-archive-organization | piaozone/imgsys-archive/api-archive-organization |
| api-archive-machine-manage | piaozone/imgsys-archive/api-archive-machine-manage |
| api-archive-license | piaozone/imgsys-archive/api-archive-license |
| api-archive-invoice | piaozone/imgsys-archive/api-archive-invoice |
| api-archive-webservice | piaozone/imgsys-archive/api-archive-webservice |
| api-archive-job | piaozone/imgsys-archive/api-archive-job |
| api-archive-alarm-monitor | piaozone/imgsys-archive/api-archive-alarm-monitor |
| api-document | piaozone/product/api-document |

> 如需新增映射，按格式在表格中追加一行即可。
