# 服务名 → GitLab 仓库映射

日志中 `fields.project` 打印的服务名与 GitLab 实际仓库路径可能不一致，查此表获取正确的 `project_id`。

| 日志服务名 (fields.project) | GitLab 仓库路径 (project_id) |
|---|---|
| smkp | https://git.kingdee.com/piaozone/output/bill-smkp.git |
| api-invoice-check | piaozone/input/api-invoice-check |
| api-invoice-collector | piaozone/input/api-invoice-collector |
| api-invoice-recognition | piaozone/input/api-invoice-recognition |
| api-invoice-frame | piaozone/base/api-invoice-frame |
| api-invoice-input-db | piaozone/input/api-invoice-input-db |
| api-invoice-input-utils | piaozone/common/api-invoice-input-utils |
| api-invoice-input-query | piaozone/input/api-invoice-input-query |
| api-fpzs | piaozone/input/api-fpzs |
| api-expense | piaozone/input/api-expense |

> 如需新增映射，按格式在表格中追加一行即可。