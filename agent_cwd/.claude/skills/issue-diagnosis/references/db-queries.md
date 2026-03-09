# 数据库查询模板

## 数据源

- 数据源名称：`prod-main`（MySQL，cms 库）

## 表说明

| 表名 | 含义 | 关键字段 |
|------|------|---------|
| `t_ou_tenant` | 租户表 | `fclient_id`（clientId）、`fou_no`（租户编号）、`fstatus`（1启用/2停用/3删除） |
| `t_ou_company` | 企业表 | `ftax_no`（税号）、`fclient_id`、`fopen_invoice_type`（开票类型）、`fcity_name`、`fstatus` |
| `t_tax_user` | 开票账户表 | `flogin_account_uid`（办税人账号）、`fcompany_ou_no`（企业编号）、`fdefault_flag`、`fselected` |

---

## 查询模板

### FAQ 开票-Q2：未配置全电开票账号

验证 clientId + 税号 + 登录账号是否存在且匹配。

```sql
-- 1. 查租户是否存在（确认 clientId 有效）
SELECT fid, fclient_id, fou_no, fstatus
FROM t_ou_tenant
WHERE fclient_id = '<clientId>';

-- 2. 查企业是否存在（确认税号与 clientId 匹配）
SELECT fid, ftax_no, fclient_id, fou_no, fopen_invoice_type, fstatus
FROM t_ou_company c
left join t_ou_tenant t
WHERE t.fclient_id = '<clientId>'
  AND c.ftax_no = '<税号>';

-- 3. 查开票账户是否配置（确认登录账号存在）
SELECT fid, fcompany_ou_no, flogin_account_uid, fdefault_flag, fselected, fetax_account_type
FROM t_tax_user
WHERE fcompany_ou_no = '<企业 fou_no>'
  AND flogin_account_uid = '<登录账号>';
```

> 排查顺序：先确认租户存在 → 再确认企业税号匹配 → 最后确认账号已配置。
> `fopen_invoice_type` 需为 1（全电）或 3（全电+税盘）才支持全电开票。
