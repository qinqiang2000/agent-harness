# 数据库查询模板

## 数据源

可用数据源定义在 `db/db_config.json`，禁止自行推导生气了执行，必须是该文档里的sql

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

### 进项采集任务状态查询

查询任务批次号对应的任务状态及错误描述。

```sql
-- 查询进项采集任务状态
SELECT fbatch_no, ftask_status, ferr_desc, fcreate_time, fupdate_time
FROM t_elc_sync_task
WHERE fbatch_no = '{batchNo}';
```

> `ftask_status` 含义：
> - 1=待处理，2=已入队列，3=处理中，4=处理完成
> - 5=处理失败，6=处理失败待重试，7=部分成功，8=全部失败
> - 9=未登录等待重试，-1=异常请求不入队列，-2=文件下载单独处理任务
>
> `ferr_desc`：最新结果描述，失败时包含具体错误信息。
> 数据源：`prod-invoice`（生产）或 `test-invoice`（测试）

---

### 合规校验-重复报销查询

查询发票流水号对应的报销单占用情况。

```sql
SELECT fexpense_num, fexpense_id, fclient_id, fstatus, fcreate_time
FROM t_bill_expense_relation
WHERE fserial_no = '{serial_no}'
  AND fstatus IN (30, 60, 65)
ORDER BY fstatus;
```

> `fstatus` 含义：30=审批中，60=已通过，65=已入账
> 数据源：`prod-invoice`（生产）或 `test-invoice`（测试）
> 若返回多条记录，说明该发票被多个报销单占用（跨企业重复报销时 `fclient_id` 不同）。

---

### 重复报销-企业名称查询

根据 fclient_id 查询企业名称和税号，用于在结论中替代 clientId 展示。

```sql
SELECT fclient_id, fname, ftax_no, fstatus
FROM t_ou_company
WHERE fclient_id = '{fclient_id}';
```

> 数据源：`prod-main`（生产）或 `test-main`（测试），即 cms 库
> `fname` 为企业名称，`ftax_no` 为税号，在结论中用企业名称替代 clientId 展示。

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
