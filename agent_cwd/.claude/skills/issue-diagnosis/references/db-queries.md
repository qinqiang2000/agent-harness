# 数据库查询模板

## 数据源

可用数据源定义在 `db/db_config.json`，每个数据源有 `env`（prod/test）和 `domain`（开票/鉴权、运营/订单）字段。

**选择规则**：
- 用户指明"测试环境" → 选 `env=test`；未指明或指明"生产环境" → 选 `env=prod`
- 开票/鉴权相关问题 → 选 `domain=开票/鉴权`（cms 库）
- 运营/订单相关问题 → 选 `domain=运营/订单`（eop 库）

---

## prod-main / test-main（cms 库）

## 表说明

| 表名 | 含义 | 关键字段 |
|------|------|---------|
| `t_ou_tenant` | 租户表 | `fclient_id`（clientId）、`fou_no`（租户编号）、`fstatus`（1启用/2停用/3删除） |
| `t_ou_company` | 企业表 | `ftax_no`（税号）、`fclient_id`（企业clientid，非租户cleintid）、`fopen_invoice_type`（开票类型）、`fcity_name`、`fstatus` |
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

-- 2. 查企业是否存在（确认税号与 租户 匹配）
SELECT fid, ftax_no, fclient_id, fou_no, fopen_invoice_type, fstatus
FROM t_ou_company 
WHERE ftenant_ou_no = '<租户 fou_no>' AND ftax_no = '<税号>';

-- 3. 查开票账户是否配置（确认登录账号存在）
SELECT fid, fcompany_ou_no, flogin_account_uid, fdefault_flag, fselected, fetax_account_type
FROM t_tax_user
WHERE fcompany_ou_no = '<企业 fou_no>'
  AND flogin_account_uid = '<登录账号>';
```

> 排查顺序：先确认租户存在 → 再确认企业税号匹配 → 最后确认账号已配置。
> `fopen_invoice_type` 需为 1（全电）或 3（全电+税盘）才支持全电开票。

---

### FAQ 接口参数-Q1：统一社会信用代码或纳税人识别号错误

验证税号对应的城市配置是否正确。

```sql
-- 查企业表，确认税号对应的城市配置
SELECT ftax_no, fcity_name, fopen_invoice_type, fstatus
FROM t_ou_company
WHERE ftax_no = '<税号>';
```

> `fcity_name` 即系统中配置的城市，与企查查等网站的实际注册城市比对，确认是否有误。

---

### FAQ 鉴权登录-Q27：企业配置信息出现错误

验证 clientId 类型是否正确（租户 vs 企业），以及税号是否与之匹配。

```sql
-- 1. 查租户表（clientId 以 TN_ 开头时走这里）
SELECT fid, fclient_id, fou_no, fstatus
FROM t_ou_tenant
WHERE fclient_id = '<clientId>';

-- 2. 查企业表（确认税号与租户匹配）
SELECT fid, ftax_no, fclient_id, fou_no, fstatus
FROM t_ou_company
WHERE ftenant_ou_no = '<租户 fou_no>' AND ftax_no = '<税号>';
```

> clientId 以 `TN_` 开头 → 是租户 clientId，走 `t_ou_tenant`；否则是企业 clientId，直接查 `t_ou_company.fclient_id`。
> 两者不可混用，混用会导致"企业配置信息出现错误"。
