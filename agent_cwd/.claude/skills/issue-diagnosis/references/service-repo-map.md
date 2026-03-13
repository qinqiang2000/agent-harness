# 服务名 → GitLab 仓库映射

日志中 `fields.project` 打印的服务名与 GitLab 实际仓库路径可能不一致，查此表获取正确的 `project_id`。

| 日志服务名 (fields.project) | GitLab 仓库路径 (project_id) |
|---|---|
| smkp | https://git.kingdee.com/piaozone/output/bill-smkp.git |

> 如需新增映射，按格式在表格中追加一行即可。
