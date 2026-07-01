# 业务知识库

本文件是「开票/收票/影像」业务的内嵌知识库，供无报错线索时的语义检索使用。
结构：关键词映射 → 直接给出调用链/核心类/关键字段；需要深入时按「深入」指针 Read 对应文档。

---

## 一、项目地图

### 代码根路径

代码根目录由环境变量 `BILLING_CODE_BASE_DIR` 控制，未设置时默认 `/Users/panda/Documents/work/project/input/`。

| 变量 | 路径 |
|---|---|
| 标准版收票根路径 | `{BILLING_CODE_BASE_DIR}/input-project/standard/input` |
| 重构版根路径 | `{BILLING_CODE_BASE_DIR}/input-project/refactor` |

### 标准版项目结构

```
standard/front/
├── fpzs-pc                   # 发票助手 PC 端前端（React + dva，端口 9000，对应后端 api-fpzs）
└── portal-web                # 商家平台前端页面项目（Vue，对应后端 bill-bm-ocr-invoice / bill-portal）

standard/input/
├── bill-bm-ocr-invoice       # 商家平台发票采集（两步上传：upload + upload/save，verifyCollect 软删除控制）
├── api-push-service-new      # 推送服务（WebSocket/长轮询推送给 ERP，含推送状态通知接口）
├── api-fpzs                  # 发票助手（前端交互层，150+ 接口，端口 9409）
├── api-expense               # 报销服务（合规校验 25+ 项）
├── api-invoice-check         # 发票查验（三级缓存 + 供应商路由）
├── api-invoice-collector     # 发票采集（邮箱取票 IMAP）
├── api-invoice-recognition   # 发票识别（OCR/XML/PDF/OFD）
├── api-invoice-frame         # 旗舰版接口适配层
├── api-invoice-input-db      # 数据库实体和 Mapper（底层依赖，82 个实体类）
├── api-invoice-input-utils   # 工具类和常量
├── api-invoice-input-query   # 查询服务
├── bill-wechat-mini-program  # 微信小程序（移动端推送）
└── bill-portal               # 门户管理后台

standard/common/
├── api-auth / base-iam       # 认证授权
├── api-company               # 企业信息
├── api-invoice-pdf / api-pdf-utils / api-ofd-utils  # 文件处理
├── base-file-center-server   # 文档中心（识别分流：网关拦截 → 按 url_config 执行上传/快照/识别/验签 → 结果注入请求体 → 转发业务接口）
└── base-gateway / bill-gateway  # 网关（FileStreamFilter 拦截文件操作请求，分流至文档中心）
```

### 重构版项目结构

```
refactor/
├── fpy-parent/               # 父 POM，统一依赖管理
├── fpy-sdk-base/             # 基础 SDK（实体、工具、配置，对应标准版 input-db + input-utils）
├── fpy-base-query/           # 查询服务（响应式，规则引擎，虚拟线程）
├── fpy-isv/                  # ISV 发票查验服务（独立项目，不依赖 fpy-sdk-base）
├── fpy-gateway/              # 网关服务
└── fpy-common/               # 公共模块
```

### 版本对照

| 维度 | 标准版 (standard/) | 重构版 (refactor/) |
|------|-------------------|-------------------|
| JDK | 8 | 21 (Record, switch表达式, 虚拟线程) |
| 框架 | Spring Boot 2.x + Servlet | Spring Boot 3.x + WebFlux |
| 数据库 | MyBatis | R2DBC（响应式，禁止 block()） |
| 缓存 | Redis | Caffeine(本地) + Redis/Redisson(分布式) |
| JSON | Fastjson（注意强转陷阱） | Fastjson2 / Jackson |

### 标准版 vs 重构版对应关系

| 标准版项目 | 重构版项目 | 说明 |
|-----------|-----------|------|
| api-invoice-check | fpy-isv (invoice/in/check/) | 发票查验，重构版独立部署 |
| api-invoice-input-db | fpy-sdk-base | 基础实体和工具 |
| api-invoice-input-query | fpy-base-query | 查询服务 |
| api-fpzs / api-expense 等 | 暂未重构 | 仍使用标准版 |

---

## 二、服务调用关系

```
文件操作请求（上传/识别等）:
客户端 → base-gateway(FileStreamFilter) → base-file-center-server(按url_config执行UPLOAD/SNAPSHOT/RECOGNITION/SIGNATURE)
    → 结果注入请求体(fileResultData) → 继续转发至实际业务接口

业务调用:
旗舰版(星瀚低代码) → api-invoice-frame → 标准版核心服务
                                            │
EAS/苍穹/星空 → api-fpzs ──┬── api-expense (合规校验, RPC)
                           ├── api-invoice-check (查验, RPC)
                           ├── api-invoice-recognition (识别, RPC)
                           ├── api-invoice-collector (邮箱取票, RPC)
                           └── api-invoice-input-db (数据访问)

商家平台采集:
portal-web(前端) → bill-bm-ocr-invoice → api-invoice-recognition (识别入库, RPC)
                                       → api-invoice-check (查验, RPC)
                                       → api-expense (合规校验, RPC)

发票导入推送:
api-fpzs → api-push-service-new (WebSocket/长轮询推送给ERP)
前端 → api-push-service-new GET /link/server/push/notify (轮询推送状态)
```

---

## 三、关键词 → 上下文映射

### 合规性校验 / 合规校验 / ExpenseVerify / InvoiceVerify
- **调用链**: api-fpzs → (RPC) → api-expense.ExpenseVerifyService.verifyBySerialNo()
- **配置管理**: bill-portal → api-expense `/expense/verify/config/save`
- **设计模式**: 策略模式 + 责任链，25+ 个 IVerifyService 实现类
- **校验项**: 重复报销、查验状态、购方名称/税号、个人发票、连号、跨年、销方黑名单等
- **校验级别**: ALLOW(允许) → YELLOW(警告) → MEDIUM(中等) → FILTER(拦截)
- **核心表**: t_expense_verify_config, t_expense_verify_config_relation
- **深入**: Read `api-expense/docs/合规性校验设计文档.md`

### 发票查验 / check / 查验
- **标准版调用链**: api-fpzs → (RPC) → api-invoice-check.InvoiceCheckService.check()
- **重构版调用链**: fpy-isv: InvoiceCheckController → ProviderRouterService → 适配器(ChangruanAdapter/LeqiAdapter/QixiangyunAdapter)
- **三级缓存**: Redis(checkType=2) → 数据库(checkType=3) → 实时调用供应商(checkType=1)
- **供应商路由(isDxCheck)**: 1=大象慧云 4=长软(主要) 5=公有云 6=账无忧 7=微乐 8=宁波港 9=大象慧云航信 默认=互金
- **重构版容错**: concatMap + onErrorResume + next 实现故障转移；默认不启用备用，需在客户配置 provider_config.fallback 中显式配置
- **重构版缓存Key**: `invoice_verification_v4:{type}:{code}:{number}:{date}:{verCode}:{amount}`，不含clientId（结果共享）
- **标准版关键类**: InvoiceCheckService → CheckResultService → CheckUtils → InvoiceOperationService
- **重构版关键类**: InvoiceCheckController → InvoiceCheckService → InvoiceSummaryService/InvoiceCheckCacheService/ProviderRouterService
- **深入(标准版)**: Read `api-invoice-check/docs/发票查验服务说明.md`
- **深入(重构版)**: Read `{重构版根路径}/fpy-isv/docs/in/check/发票查验模块说明.md`

#### 标准版查验接口清单

| 接口路径 | 说明 |
|---------|------|
| `POST invoice/sys/checkfull` | 单张查验（同步入库），返回 serialNo 等完整信息 |
| `POST invoice/sys/check` | 单张查验（异步入库），不返回 serialNo |
| `POST invoice/list/check` | 批量查验（异步入库） |
| `POST invoice/img/check/thirdPartyCall` | 第三方直接调用查验 |

#### 标准版查验请求参数

| 参数 | 必填条件 | 说明 |
|-----|---------|------|
| clientId | 是 | 客户标识 |
| invoiceCode | 传统票必填 | 发票代码（数电票为空） |
| invoiceNo | 是 | 传统8位/数电20位 |
| invoiceDate | 是 | yyyyMMdd |
| invoiceMoney | 传统票必填 | 不含税金额 |
| totalAmount | 数电票必填 | 价税合计 |
| checkCode | 普票必填 | 校验码后6位 |
| isDxCheck | 否 | 供应商路由，默认4(长软) |

#### 重构版查验接口

| 接口路径 | 说明 |
|---------|------|
| `POST /partners/v1/invoice-verifications` | 发票查验，Header需传 X-Request-Id |

---

### 邮箱取票 / 邮箱收票 / mail / collector
- **项目**: api-invoice-collector
- **核心类**: MailFolderScanJob(扫描), MailTaskProcessJob(处理)
- **协议**: IMAP
- **海外发票**: t_email_config.invoice_region (0=国内, 1=海外)
- **深入**: Read `api-invoice-collector/docs/邮箱取票设计文档.md`

### RPA / etax / 税局下票 / 入账状态 / 农产品发票 / batchNo
- **项目**: api-invoice-collector，包路径 `com.kingdee.service.etax`
- **4 种任务类型 (ETaxTypeEnum)**:
  - type=1 数电发票下载 (EleInvoiceService)
  - type=2 农产品发票下载 (FarmInvoiceService)
  - type=3 入账状态查询 (MarkStatusService)
  - type=4 入账状态提交/更新 (MarkBridgeService)
- **状态机 (ETaxStatusEnum)**: 0=处理中 1=成功 2=系统异常 3=业务失败 4=部分成功 5=需重试 6=已废弃
- **错误码**: 1307=处理中可重试(含429限流) / 1100=不可恢复 / 1300=参数错误
- **核心表**: t_rpa_apply_log(任务主表), t_rpa_apply_log_detail(明细), t_invoice_extra(入账状态缓存)
- **深入**: Read `api-invoice-collector/docs/RPA税局下票技术文档.md`

### 旗舰版 / 星瀚 / 苍穹 / api-invoice-frame / firmament / 数据同步 / 收票同步
- **统一入口**: POST /m3/bill/firmament/img/handle（eventType 数字路由，见下表）
- **架构**: 旗舰版(星瀚低代码) → api-invoice-frame(FirmamentApiController#handle) → 标准版核心服务
- **适用场景**: 凡是「标准版收票数据同步到星瀚」「星瀚发起的收票操作」「苍穹侧数据缺失/同步中断」等问题，入口均在此

#### handle eventType 枚举（关键场景）

| eventType | 方法 | 说明 |
|---|---|---|
| 1 | getTaxPeriod | 查询税款所属期 |
| 2 | queryInvoices | **采集发票 / 数据同步**（公有云底账同步，按 clientId 全量，同步中断需重新触发） |
| 3 | getTongjiStatus | 获取企业统计表 |
| 4 | createTongji | 生成统计表 |
| 5 | cancelTongji | 取消统计表 |
| 6 | confirmTongji | 确认统计表 |
| 7 | invoiceGx | 发票勾选 |
| 8 | downloadApply | 进销项下载申请 |
| 9 | downloadQuery | 进销项发票下载查询 |
| 10 | invoiceRecognitionCheck | 发票识别查验 |
| 11 | invoiceCheck | 发票查验 |
| 12 | placeMapping | 省市区查询 |
| 13 | blackListMapping | 销方黑名单列表 |
| 14 | getLinkkey | 获取 LinkKey |
| 15 | getUserKey | 获取 userKey |
| 16 | getMiniProgramQrcode | 生成小程序二维码（GET） |
| 17 | queryInputSync | **查询发票同步状态**（同步中断排查入口） |
| 18 | blockChainCheck | 区块链发票查验 |
| 19 | getYunpiaoValidatecode | 云票获取短信验证码 |
| 20 | yunpiaoIdentifyAndAuthorization | 云票验证码授权 |
| 21 | getYunpiaoInvoice | 云票获取发票数据 |
| 22 | sendVerifyCode | 发送邮箱验证码 |
| 23 | bandMail | 绑定邮箱 |
| 24 | queryMyMailList | 查询我的邮箱列表 |
| 25 | unBandMail | 解绑邮箱 |
| 26 | mailTask | 邮箱取票任务列表 |
| 27 | mailRetryTask | 邮箱重试任务 |
| 28 | mailDelTask | 邮箱删除任务 |
| 29 | createInvoicePdf | 生成底账 PDF |
| 30 | msgCollectConfirm | 短信取票-确认取票 |
| 31 | msgTaskList | 短信取票-获取任务列表 |
| 32 | msgTaskRetry | 短信取票-重试失败任务 |
| 33 | msgTaskDel | 短信取票-删除任务 |
| 34 | invoiceParamSerialNoQuery | 根据流水号查询数据 |
| 35 | pureRecognition | 睿琪纯识别 |
| 37 | getTenantToken | 获取租户 token |
| 38 | getTenantInfo | 获取租户信息 |
| 39 | getClientRights | 获取用户权益 |
| 40 | syncXkBlackListInfo | 信科黑名单数据同步 |
| 41 | syncConfig | 同步邮箱配置 |
| 42 | queryTaskList | 分页查询任务列表 |
| 43 | queryTaskDetail | 查询任务详情 |
| 44 | syncMailEnable | 同步邮箱可用状态 |
| 46 | parseLink | 链接解析（二维码，含识别+查验） |

- **数据同步中断排查**: eventType=2 调用 `collectorRpcService.queryInvoices()`，同步逻辑在 api-invoice-collector；定时任务关闭/重启导致中断时需按 clientId 重新触发全量同步；aws 无切片记录故中断后必须全量重跑
- **枚举表兜底**: 若上表中找不到对应 eventType，先拉取最新代码确认当前枚举全集，再判断是 bug（已有 eventType 行为异常）还是需求（缺少 eventType 或新功能诉求）：
  ```bash
  git -C {BILLING_CODE_BASE_DIR}/input-project/standard/input/api-invoice-frame pull
  grep -n "case " {BILLING_CODE_BASE_DIR}/input-project/standard/input/api-invoice-frame/src/main/java/com/kingdee/controller/firmament/FirmamentApiController.java
  ```
- **深入**: Read `api-invoice-frame/docs/旗舰版接口对接文档.md`

### 发票助手 / fpzs / api-fpzs
- **接口前缀**: /m4 或 /m4-web
- **对接产品线**: EAS（分录管理）、苍穹/星瀚费报（status区分）、星空（linkKey+扫码）
- **深入**: Read `api-fpzs/docs/接口清单.md` 和 `api-fpzs/docs/对接流程说明.md`

### 报销 / expense / 报销单 / 状态
- **状态流转**: 未用(1) → 在用(30) → 已用(60) → 已入账(65)
- **核心表**: t_bill_expense, t_bill_expense_relation
- **产品线差异**: EAS(前端推送+缓存) / 苍穹(同接口status区分) / 星空(linkKey+扫码)

- **旧台账**: t_bill_belong_relation（JOIN多表，慢）
- **新台账**: t_bill_account_company + t_bill_account_user（宽表，快10倍+）
- **同步**: AOP自动同步 (Bill0AccountAop + VatRecognitionAccountAop)
- **深入**: Read `api-invoice-input-db/docs/台账设计文档.md`

### 文档中心 / file-center / 分流 / 网关拦截 / UPLOAD / SNAPSHOT / SIGNATURE
- **项目**: base-file-center-server
- **网关拦截**: FileStreamFilter(GlobalFilter, order=99) 根据 `gateway.file.handle.url` 配置匹配请求路径
- **operator 格式**: 逗号分隔，操作码: UPLOAD(上传) / SNAPSHOT(快照) / RECOGNITION(识别) / SIGNATURE(验签)
- **关键类**: FileStreamFilter(网关) → BaseFileRpcService(Feign) → FileOperatorController → UriDbConfigService → FileOperationServiceImpl → 各 HandleService
- **深入**: 知识库「文档中心」条目已有完整说明，或 Read base-file-center-server 源码

### 发票识别 / recognition / OCR
- **项目**: api-invoice-recognition
- **前置**: 识别请求先经网关分流至文档中心，由 RecognitionHandleServiceImpl 按文件格式执行解析/OCR，结果注入请求体后才到达 api-invoice-recognition
- **支持格式**: 图片(OCR) / PDF(解析) / OFD(解析) / XML(解析) / XBRL(专用解析器)
- **深入**: Read `api-invoice-recognition/docs/文档中心保存发票文档.md`

### 商家平台发票采集 / bill-bm-ocr-invoice / verifyCollect / fdelete
- **两步流程**: `/portal/bm/ocr/recognition/upload`（识别+查验）→ `/portal/bm/ocr/recognition/upload/save`（确认上传）
- **fdelete 状态**: verifyCollect=true 时识别入库 fdelete=2（软删除待确认）→ 用户确认后 fdelete=1（可用）
- **深入**: Read `bill-bm-ocr-invoice/docs/商家平台发票采集接口文档.md`

### 台账查询 / 台账统计 / 数据统计
- **入口服务**: bill-bm-ocr-invoice
- **两条路径**:
  - 旧版台账：`InvoiceAccountController` → `InvoiceAccountService`（本地查询）
  - 新版台账（全票池）：`InputAccountController` → `InputInvoiceQueryRpcService`（RPC → api-invoice-input-query）
- **深入**: Read bill-bm-ocr-invoice 对应 Controller 源码

### 发票导入 taxRate / 税率字段
- **接口**: `POST /m4/fpzs/expense/invoice/insert`
- **取值路由**: 从明细行 items[0].taxRate: 1/2/3/4/5/7/15/23/26/27/30/72/83；从票头 taxRate: 9/10/12/16/20/28/29；免税强制返回0: 84
- **深入**: Read `api-fpzs/docs/发票导入taxRate字段取值设计文档.md`

### 合规校验重构 / fpy-base-query / VerifyInvoiceService
- **项目**: fpy-base-query，接口 `POST /verify/invoice`
- **架构**: VerifyInvoiceController → VerifyInvoiceService → LoadExpenseDataService + RuleConfig.execute(INVOICE_VERIFY)
- **规则引擎**: 25 个 RuleExecutor，ORDER 串行执行
- **校验级别**: ALLOW("1") → YELLOW("3") → MEDIUM("2") → FILTER("0")
- **深入**: Read `{重构版根路径}/fpy-base-query/docs/合规性校验重构设计文档.md`

### 版本管理 / 依赖升级 / 版本号
- **版本号格式**: `YY.MM.VX`（如 26.03.V1）
- **升级触发规则**:
  - api-invoice-input-db **字段变更** → 必须升版本号
  - api-invoice-input-utils **工具类/业务变更** → 必须升版本号
- **依赖链**: api-invoice-input-db → api-invoice-input-utils → 上层服务（api-fpzs/api-expense/api-invoice-check 等）

---

## 四、开票业务（待补充）

> 此节暂为占位，待开票业务知识整理后填入。
> 填入格式参考「三、关键词 → 上下文映射」中的收票条目。

---

## 五、影像业务（待补充）

> 此节暂为占位，待影像业务知识整理后填入。
> 填入格式参考「三、关键词 → 上下文映射」中的收票条目。

---

## 六、全量文档索引

### 标准版（相对 `{BILLING_CODE_BASE_DIR}/input-project/standard/input/`）

| 文档路径 | 说明 |
|---------|------|
| api-fpzs/docs/接口清单.md | 150+ API 接口分类 |
| api-fpzs/docs/对接流程说明.md | EAS/苍穹/星空对接流程 |
| api-fpzs/docs/发票上传流程设计文档.md | m4/fpzs/expense/upload 完整流程 |
| api-fpzs/docs/发票导入taxRate字段取值设计文档.md | taxRate 按票种路由规则 |
| api-fpzs/docs/msg消息格式说明.md | saveBill 推送格式 |
| api-fpzs/docs/接口分析-verificate-query.md | verificate/query 接口完整分析 |
| api-expense/docs/合规性校验设计文档.md | 25+ 校验项详解 |
| api-expense/docs/购方校验票种配置功能说明.md | 购方校验配置 |
| api-invoice-check/docs/发票查验服务说明.md | 查验流程和供应商路由 |
| api-invoice-check/docs/invoice-check-service.md | 四段式流程详解 |
| api-invoice-check/docs/地区异常统计说明.md | CheckStatsImpl 省级预警机制 |
| api-invoice-collector/docs/邮箱取票设计文档.md | 邮箱收票完整流程 |
| api-invoice-collector/docs/RPA税局下票技术文档.md | RPA 架构、任务类型、状态机 |
| api-invoice-collector/docs/发票重复保存问题分析与优化方案.md | 重复保存风险与 Redis 幂等方案 |
| api-invoice-frame/docs/旗舰版接口对接文档.md | 旗舰版统一入口 |
| bill-bm-ocr-invoice/docs/商家平台发票采集接口文档.md | 两步上传流程、fdelete 状态机 |
| api-push-service-new/docs/superpowers/specs/2026-03-25-push-notify-design.md | 推送状态通知接口设计 |
| api-invoice-input-db/docs/台账设计文档.md | 新旧台账对比 |
| api-invoice-input-db/docs/数据库表结构文档.md | 核心表结构 |
| api-invoice-recognition/docs/文档中心保存发票文档.md | 识别保存流程 |
| bill-portal/docs/发票查验批量接口分析文档.md | CheckInvoiceController 批量查验 |

### 重构版（相对 `{BILLING_CODE_BASE_DIR}/input-project/refactor/`）

| 文档路径 | 说明 |
|---------|------|
| fpy-isv/docs/in/check/发票查验模块说明.md | 查验主流程、供应商路由、故障转移 |
| fpy-isv/docs/in/check/查验场景测试指南.md | 7 个测试场景（缓存/DB/穿透/短路/窗口期） |
| fpy-isv/docs/invoice-recognition-api-design.md | 发票识别查验 ISV 重构接口 |
| fpy-base-query/docs/合规性校验重构设计文档.md | 24 个规则执行器、compare 模式 |
| fpy-base-query/docs/Rule规则引擎设计文档.md | 规则引擎架构 |

---

## 七、知识库更新指引

新增条目时：
1. **新场景/功能** → 在「三、关键词 → 上下文映射」中按业务分组追加
2. **新文档** → 在「六、全量文档索引」中添加条目
3. **开票/影像补充** → 分别填入「四」「五」节
4. **服务调用关系变更** → 更新「二、服务调用关系」

扫描新文档命令：
```bash
find {BILLING_CODE_BASE_DIR}/input-project/standard/input -path "*/docs/*.md" -newer {本文件路径}
find {BILLING_CODE_BASE_DIR}/input-project/refactor -path "*/docs/*.md" -newer {本文件路径}
```
