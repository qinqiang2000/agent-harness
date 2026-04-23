# Issue-Diagnosis 历史经验库

每条 Case 由 agent 在用户纠正后自动写入，人工审核后合并到 FAQ 或 SKILL.md。

**字段说明**：
- `match_confidence`：适用条件的匹配置信度（0.6-0.9），创建时评估，不随反馈变化
- `answer_confidence`：结论可信度，随用户反馈动态调整（确认 +0.1，否定 -0.2，降至 0.1 以下标记 rejected）

**状态说明**：
- `pending_review`：待人工审核
- `merged`：已合并到 FAQ 或 SKILL.md
- `rejected`：审核不通过，已废弃

---

<!-- Cases will be appended below by the agent -->

## Case #006
- 触发场景: 台账管理中通过采集人姓名/手机号查询查不到发票数据，但通过发票号码直接查询可以查到，服务 `bill-bm-ocr-invoice` / `api-account`
- 初次诊断: t_bill_account_user 表中 fuser_id 与查询传入的 userId 不匹配
- 用户反馈: [显式] 小程序采集的发票，在台账管理中用采集人手机号筛选只能查到pc端采集的，查不到小程序采集的；采集人姓名是模糊查询不准确，建议用手机号查；相同采集人名称对应的userId在不同渠道可能不一样
- 正确路径:
  1. 根因：`t_bill_account_user.fuser_id` 存储的是发票云 IAM 内部 UUID（来自 `t_invoice_user_client`），而 `queryRelationUser` 在做云之家 uid → UUID 转换时，优先返回移动端（mobile）userId，PC端（fpy）和小程序端的 userId 是不同的 UUID。小程序采集入库时写入的是小程序端 userId，而 PC 端查询时 `queryRelationUser` 返回的是移动端或 PC 端 userId，两者不匹配导致 EXISTS 子查询返回空。
  2. 采集人姓名查询走 `t_cms_user.fname LIKE '%姓名%'` 模糊匹配，同名用户会命中多个，不准确。
  3. 不同渠道（PC/小程序/移动端）同一个人对应多个 `t_invoice_user_client` 记录，每条记录的 `fuser_id`（即 `t_invoice_user` 主键）可能不同。
  4. 处置建议：
     - 采集人筛选建议改用手机号查询（`queryByPhone` 接口），手机号能跨渠道关联所有 userId
     - 若需支持小程序采集发票的采集人筛选，需在 `queryRelationUser` 中补充返回小程序端 userId，或在查询时扩展为按手机号查所有关联 userId
- 适用条件: 台账管理按采集人姓名或手机号查询结果为空，但按发票号码可查到；日志中 `queryUidList` 命中缓存，EXISTS 子查询 `d.fuser_id IN (...)` 返回空；涉及小程序采集场景
- match_confidence: 0.7
- answer_confidence: 0.8
- 状态: pending_review
- 创建时间: 2026-04-23

## Case #005
- 触发场景: 错误码 `ELC-CLRNC-INTL-PAGERO-SYS-ERROR`，报错 "get pagero token fail message"，服务 `api-elc-invoice-gjfp`
- 初次诊断: `PageroOauthDto` 构建时 `client_secret` 被错误赋值为 `client_id` 的值，`password` 被赋值为 `username`，导致 Pagero OAuth 返回 401 `invalid_client`
- 用户反馈: [显式] 根因是昨天的 ouno 配置填错了
- 正确路径:
  1. 根因：Pagero 通道的 ouno（OAuth 账号）配置填写有误，导致 `PageroUtil.getOauthToken()` 构建请求参数时 `client_secret` / `password` 字段取到了错误的值
  2. 日志特征：`getOauthToken pageroOauthDto` 中 `client_secret` 与 `client_id` 值相同，或 `password` 与 `username` 值相同；紧接着 `httpPutFormDataRequest status:401，resultBody:{"error":"invalid_client"}`
  3. 处置：检查并修正 Pagero 通道的 ouno 配置（client_id、client_secret、username、password 四个字段），保存后重试即可
- 适用条件: 报错含 "get pagero token fail message" 或错误码 `ELC-CLRNC-INTL-PAGERO-SYS-ERROR`，日志中 Pagero OAuth 返回 401 `invalid_client`
- match_confidence: 0.7
- answer_confidence: 0.8
- 状态: pending_review
- 创建时间: 2026-04-21

## Case #004
- 触发场景: 报销单全量查询接口报错"发票数据不能为空"，日志显示按发票流水号查询 t_bill0_x 分表返回空
- 初次诊断: 发票数据未入库、分表路由错误或数据被删除
- 用户反馈: [显式] 如果分表查不到对应发票，且发票开具日期是2023年以前的，需要找值班研发处理
- 正确路径:
  1. 根因：发票流水号在 `t_bill_expense_relation` 中存在关联记录，但在对应分表（如 `t_bill0_3`）中查无数据
  2. 进一步确认发票开具日期：若开具日期为 2023 年以前，属于历史数据迁移问题，数据可能未迁移到当前分表
  3. 处置：联系值班研发处理历史数据问题（数据补录或迁移）
  4. 若开具日期为 2023 年及以后，则按常规排查：发票未入库、分表路由错误、数据被删除等
- 适用条件: 报错含"发票数据不能为空"，日志中 `新版查询结果数量[0]` 且 SQL 查询 `t_bill0_x` 返回空，需进一步确认发票开具日期
- match_confidence: 0.7
- answer_confidence: 0.8
- 状态: pending_review
- 创建时间: 2026-04-16

## Case #003
- 触发场景: 报错"请求企业配置信息出现错误，请联系工作人员"，日志显示根据 clientId 查询租户/企业信息返回 null
- 初次诊断: clientId 在 IAM 系统中查无对应租户或企业记录
- 用户反馈: [显式] 除企业未注册、clientId 传错外，还需提示用户 clientId 中易混淆字符（数字0与字母O、数字1与字母l）导致填写错误的可能
- 正确路径:
  1. 根因：`base-iam` 服务查询 `t_ou_tenant` 和 `t_ou_company` 表均返回 null，`bill-websocket` 无法获取企业配置，触发报错
  2. 当数据库查询 `t_ou_tenant` 和 `t_ou_company` 均返回 null 时，给出以下建议：
     a. 企业未注册/未开通：该 clientId 对应企业尚未在发票云完成注册，需在管理后台补录
     b. clientId 填写有误：用户手动输入 clientId 时易混淆字符，如数字 `0` 与字母 `O`、数字 `1` 与字母 `l`（小写L），建议让用户复制粘贴原始 clientId 后重试
     c. 数据被禁用：检查 IAM 数据状态，`t_ou_tenant.fstatus` 是否为 1、`t_ou_company.fstatus` 是否为 3
- 适用条件: 报错含"请求企业配置信息出现错误"，日志中 `queryTenantByClientId1 result:null` 或 `queryCompanyByClientId1 ouCompany:null`
- match_confidence: 0.7
- answer_confidence: 0.8
- 状态: pending_review
- 创建时间: 2026-04-15

## Case #002
- 触发场景: 星瀚系统中操作提示"没有开启软证书"，接口报错"税号:{税号},没有开启软证书模式"
- 初次诊断: （本条为用户主动录入的经验，无初次诊断）
- 用户反馈: [显式] 用户直接提供正确根因和处理方式
- 正确路径:
  1. 根因：星瀚系统收票通道配置有误，通道被配置为"软证书"模式，但实际未开启软证书
  2. 处置：进入星瀚系统 → 收票通道配置 → 检查当前通道类型是否为"软证书"，若是，改为"下数电"或"乐企"通道即可
- 适用条件: 报错含"没有开启软证书模式"，且系统为星瀚（xinghan），场景为收票通道配置
- match_confidence: 0.7
- answer_confidence: 0.9
- 状态: pending_review
- 创建时间: 2026-04-10

## Case #001
- 触发场景: 登录提示"检测到您数电账号里维护的电子税局身份有误"，错误码 0702034（可信错误）
- 初次诊断: 税局侧身份校验问题，建议用户去电子税局修正身份信息
- 用户反馈: [显式] 不对，应先检查源码，用户传的是办税员，但系统实际用了不同角色去登录，用户在电子税局只有办税员角色才会报这个错
- 正确路径:
  1. 查日志确认错误码为 0702034，属可信错误
  2. 根因：系统自动登录时从 Redis（key: NEW_ERA_LOGIN_SUCCESS_ROLE_CODE:{taxNo}:{account}）取缓存的 roleCode，若缓存了账号不具备的角色（如 09 开票员），而用户在电子税局只有办税员（03）角色，税局会拒绝并返回 0702034
  3. 源码位置：api-elc-invoice-lqpt NewEraService.java:1309-1314（自动登录覆盖 roleCode）、:440-441（按优先级 01,02,09,03 缓存角色）
- 处置建议:
  1. 先让用户自行登录电子税局，检查账号实际拥有的身份角色，与发票云登录时传入的 roleCode 是否一致
  2. 若一致（说明是 Redis 缓存了错误角色），联系值班人员清除 Redis 中该账号的 NEW_ERA_LOGIN_SUCCESS_ROLE_CODE 缓存，再让用户重新手动登录一次
  3. 若不一致，让用户在电子税局补充对应角色权限后重试
- 适用条件: 报错含"数电账号里维护的电子税局身份有误"或 errcode=0702034，且用户反映账号角色配置正确
- match_confidence: 0.7
- answer_confidence: 0.8
- 状态: pending_review
- 创建时间: 2026-04-10
