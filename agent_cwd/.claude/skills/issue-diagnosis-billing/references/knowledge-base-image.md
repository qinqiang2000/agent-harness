# 影像业务知识库（knowledge-base-image）

本文件是「影像采集 / 匹配 / 提交 / 归档」业务的内嵌知识库，供无报错线索时的语义检索使用。
结构：关键词映射 → 直接给出调用链/核心类/关键字段；需要深入时按「深入」指针 Read 对应源码或文档。

---

## 一、项目地图

### 代码根路径

代码根目录由环境变量 `BILLING_CODE_BASE_DIR` 控制，未设置时默认 `/Users/panda/Documents/work/project/input/`。

| 变量 | 路径 |
|---|---|
| 标准版影像根路径 | `{BILLING_CODE_BASE_DIR}/input-project/standard/input` |

下文源码路径均以标准版影像根路径为基准，简写为 `standard/input/{repo-name}/...`。

技术栈：Spring Boot 2.x + MyBatis + ShardingSphere（按 `ftenant_num` 分库 `scan_$->{[...]}`） + Redis(db=15) + MinIO / AWS S3。

### 标准版影像项目结构

```
standard/input/
├── api-archive-scan/             # 【核心】影像扫描归档（端口 11105，contextPath=/imgsys）
├── api-archive-invoice/          # 票据 / 租户 / 扫描配置
├── api-archive-organization/     # 组织权限
├── api-archive-job/              # XXL-JOB Admin 调度中心
├── api-archive/                  # 档案系统（归档接收端）
├── api-archive-scan-move/        # 影像搬移服务
├── api-archive-machine-manage/   # 收单机管理
├── api-archive-license/          # License 管理
├── api-archive-webservice/       # WebService 对接
└── api-archive-alarm-monitor/    # 告警监控

standard/frontend/
├── image-system/                 # 影像管理主站（Egg.js + React + Dva，端口 10024）
└── image-asst/                   # 影像助手（Egg.js + React + Recoil，端口 10203）
```

> 注：`bill-eureka`、`base-gateway`、`archive-dataSource-utils`、`archive-pub-utils`、AI 子系统（`base-ai-file-cls`）**未克隆**，源码分析时不可用。

### 前端排查指引

后台代码找不到入口或逻辑时，可通过前端代码辅助排查：
- `image-system`：PC 端，负责影像采集、查看、匹配、审核等主流程
- `image-asst`：移动端（影像助手），负责附件上传、影像采集辅助

**分析前端代码时，优先读对应项目根目录的 `CLAUDE.md`**，其中有完整的架构说明和路由约定。

**前端→后端 URL 路由规则**（已从代码确认）：

| 前端 URL 前缀 | 后端服务 | 说明 |
|---|---|---|
| `/archivebase` 开头 | `api-archive-organization` | 登录、鉴权、组织、用户、License 相关 |
| `/imgsys` 开头 | `api-archive-scan` | 影像采集、匹配、提交、附件等所有业务接口 |

**接口路由位置**：
- `image-system`：`app/routeGroup/api.js`（archivebase 路由）+ `app/routeGroup/forwardRoutes/`（imgsys 转发路由）
- `image-asst`：`app/router/index.js` + `app/router/forwardRoutes/assistant.js`（k0~k8 转发路由）

**image-system 路由前缀**：页面 `/imgsys-web`，API `/imgsys-web/api`，后端 `/imgsys`
**image-asst 路由前缀**：页面 `/imgasst-web`，API `/imgasst-web/api`，后端 `/imgsys`

### 核心服务：api-archive-scan 包结构

源码根：`api-archive-scan/src/main/java/com/kingdee/`

```
com.kingdee/
├── annotation/   # 权限检查 / 抽检 / 状态控制注解
├── aspect/       # 权限、抽检 AOP 切面
├── async/        # 异步任务：CheckBillAsync / CommitAsync / MatchAsync / CompressFileAsync / TransferAsync
├── config/       # 多数据源/分片/XXL-JOB/拦截器/线程池
├── controller/   # 20+ 子模块（见下方接口前缀表）
├── enums/        # ScanModeTypeEnum / ScanDetailTypeEnum / SystemTenantConfigEnum 等
├── file/         # 文件 VO 与 HTTP 适配
├── fpy/          # 自研 MQ（Redis 队列 + 注解 @KingMqConsumer/@KingMqProducer）
├── mapper/       # 18+ 子模块 MyBatis Mapper
├── model/        # 40+ 子模块（scan / match / invoice / uex / signPostBill / export 等）
├── process/      # 流程链
├── queue/        # Redis 队列（去重 / 不去重 / 通知去重）
├── rpc/          # Feign 客户端 + Hystrix 降级
├── service/      # 30+ 子模块业务服务
├── task/         # 20+ XXL-JOB 任务
└── util/         # 工具类（imgsys / http / 加密 / 压缩 / OCR）
```

### 接口前缀（Controller Base Path）

| 前缀 | Controller | 功能 |
|------|------------|------|
| `/bill/scanner` | ScanController | 影像扫描管理、状态更新、查询、提交、删除 |
| `/bill/inside` | ScanBackEndController | 内部接口：文件上传、二维码、保存明细、查重 |
| `/bill/detail` | ScanDetailController | 明细查询、转附件、新增/删除发票、批注 |
| `/bill/outside` | ScanOutsideController / ScanOutSideApiController / DownloadController | 对外采集 / API |
| `/bill/outside/match` | MatchOutsideController | 对外匹配 |
| `/bill/outside/migrate` | ScanOutSideBillInfoController | 历史影像迁移 |
| `/bill/outside/appendix` | ScanOutSideUploadController | 附件上传 |
| `/bill/ocr` | OcrOutSideController | OCR 外部 |
| `/bill/erp/bankReceipt` | BankReceiptErpController | 银行回单 ERP 对接 |
| `/bill/scan/upload-check` | ScanUploadAndCheckController | 上传 + 识别 + 查验一体化 |
| `/bill/scan/operat/query` | ScanOperateController | 操作日志查询 |
| `/scan` | ScanMoveController / GxScanMoveController | 跨系统影像搬移（DKWS / 广西） |
| `/outside` | MatchFpzsController | 收票合作方接入 |
| `/bill/` | AisinoOutsideController | 航信对接 |
| `/bill/uex/*` | UEXController / ReceivingMachineController | 收单机 / 归档箱 |
| `/bill/h5/*` | H5ScanController | H5 移动端调阅 |
| `/bill/label/*` | LabelController | 文件标签 |
| `/bill/export/*` | ExportController | 导出任务 |

### 环境与端口

- 服务名：`api-archive-scan`，端口 `11105`，contextPath `/imgsys`
- 多租户：ShardingSphere 按 `ftenant_num` 分库
- Redis：生产/IDC/测试 `database=1`，本地开发 `database=15`，max-active=5000
- 文件存储：MinIO（私有化）/ AWS S3（公有云），切换由 `isPrivate` 控制
- 注册中心：Eureka（`bill-eureka`）

---

## 二、服务调用关系

```
客户端（浏览器 / 移动端）
        ▼
    image-system（PC，端口 10024）   image-asst（移动端，端口 10203）
        │  Egg.js BFF 代理转发              │  Egg.js BFF 代理转发
        ▼                                   ▼
    base-gateway
        ├──→ api-archive-scan         /imgsys 开头的 URL → 影像相关接口入口
        ├──→ api-archive-organization /archivebase 开头的 URL → 组织/登录/授权接口入口
        └──→ api-archive              档案相关接口入口

api-archive-scan 内部 Feign 调用：
    api-archive-scan ─── Feign ───┐
        ├── api-archive-organization    组织/用户/权限（含登录态校验）
        ├── api-archive-invoice         租户/扫描配置/版本/外部配置
        ├── api-archive                 档案系统（归档推送）
        ├── api-archive-alarm-monitor   告警监控
        ├── base-platform-adapter       运营平台 EOP 数据同步
        ├── BASE-AI-FILE-CLS            AI 文件分类（发票角度纠正/附件识别）
        └── base-iam                    统一身份认证（仅 EopPlatformUtil 查询公司信息时调用）

影像处理链路：
扫描设备 / 上传 → api-archive-scan
    ├── 识别（Strategy）：AWSFPY / 百胜 / 数英互联
    ├── 查验：→ api-archive-invoice 或合作方接口
    ├── 匹配：MatchService → 报销单 / 发票 / 附件
    ├── 提交：ScanBillSubmitService（basics / match / sync）
    ├── ERP 推送：StrategyContainer（EAS / 苍穹 / 星空 / 星瀚 / 弘鼎）
    ├── 归档推送：PushToArchiveService → api-archive
    └── 收单机投递：UexMachineService → t_uex_box

异步队列（Redis + XXL-JOB 触发）：
BillUploadRedisQueueTask        → 上传后异步识别查验
MatchCheckQueueTask             → 匹配查验
PushToArchiveTask               → 归档推送
CreateThumbnailORSnapshotTask   → 缩略图 / 快照
S3FileUploadQueueTask           → 文件异步上 S3
ImagingCompensationTask         → 影像化补偿
ErpBillPushFpzsInformTask       → ERP 单据推送通知发票助手
```

---

## 三、关键词 → 上下文映射

### 影像采集 / 扫描 / 上传 / scan / scanBill
- **核心实体**: `ScanBill`(`t_scan_bill`) + `ScanBillDetail`(`t_scan_bill_details`)，业务键 `(ftenant_num, fscan_bill_no)`
- **上传入口**:
  - `POST /bill/scan/upload-check/distinguish` 上传 + 识别 + 查验（ScanUploadAndCheckService）
  - `POST /bill/inside/file/qrcode/scan` 二维码识别（ScanService.qrcodeScan）
  - `POST /bill/inside/detail/save` 明细保存（ScanBillBusinessService.scanSaveCommit）
  - `POST /bill/outside/appendix` 附件外部上传
- **状态机 fscanStatus**: 1=影像已上传 / 2=影像已提交 / 3=影像审核完成 / 4=影像有误待重扫 / 5=影像匹配失败 / 6=单据处理失败异常 / 7=识别查验完成 / 8=影像匹配成功 / 9=单据被删除
- **明细类型 fscanType**: 1=发票 / 2=附件 / 3=大文件（ScanDetailTypeEnum）
- **文件类型 ffileType**: 1=PDF / 2=IMG / 3=OTHER / 4=EXCEL（Constant.FILE_TYPE_*）
- **退扫 fretreatScanStatus**: 0=正常提交 / 1=退扫后未调整 / 2=退扫后已调整 / 3=退扫后新增 / 4=退扫后手工确认正常
- **深入**: Read `api-archive-scan/src/main/java/com/kingdee/service/scan/ScanService.java`、`api-archive-scan/src/main/java/com/kingdee/service/scan/ScanBillBusinessService.java`

### 影像模式 / fbusinessModel / ScanModeTypeEnum
- **6 种模式（ScanModeTypeEnum）**：1=基础(BASIC) / 2=匹配(MATCH) / 3=同步(SYNC) / 4=稽核(APPROVE) / 5=人工审核(CHECK) / 6=附件(ATTACHMENT)
- **提交分流**: `ScanBillSubmitService.basicsSubmitBill / matchSubmitBill / syncSubmitBill`
- **归档推送过滤**: `Constant.PUSH_ARCHIVE_MODEL` 控制触发模式
- **深入**: Read `api-archive-scan/src/main/java/com/kingdee/enums/ScanModeTypeEnum.java`

### 影像识别 / OCR / recognition / Strategy
- **策略容器**: `InvoiceRecognitionStrategyContainer` + `InvoiceRecognitionStrategyFactory`
- **三家供应商**:
  - `AWSFPYInvoiceRecognition` 自研 / AWS
  - `BAISHENGInvoiceRecognition` 百胜
  - `ShuYingHuLianInvoiceRecognition` 数英互联
- **入口**: `ScanBillBusinessService.recognitionFile(scanDetailId, scanType, loginInfo)`
- **AI 二级分类**: `BaseAiFileClsRpcService` → `BASE-AI-FILE-CLS`（发票角度纠正 / 长图 / 票据特征）
- **深入**: Read `api-archive-scan/src/main/java/com/kingdee/service/Strategy/recognition/`

### 影像匹配 / match / 报销单 / 发票
- **入口**: `MatchService` / `MatchBusinessService` / `MatchAutoService`
- **核心表**: `t_match_record`(封面) / `t_match_invoice_info`(发票头) / `t_match_invoice_scan`(明细) / `t_match_cover` / `t_match_attachment`
- **类型策略**: `InvoiceMatchStrategyContainer` 按 `finvoiceType` 路由（9/10/11/17/19/20/21/24/25/26_27/28/29/30/31/72/83/84/others）
- **三种匹配**:
  - `electricTicketMatch` 全电票
  - `nonElectricTicketMatch` 非全电票（含纸票）
  - `specialTicketMatch` 特殊平台（商旅）默认通过
- **开关（SystemTenantConfigEnum）**: `ELECTRIC_INVOICE_MATCH` / `NO_MATCH_INVOICE_DELETE` / `INVOICE_NUM_MATCH_CHECK` / `MATCH_VIEW_V2`
- **去重**: `InvoiceMatchHashJob.DealInvoiceMatchHashTask`（XXL-JOB）维护匹配 hash
- **深入**: Read `api-archive-scan/src/main/java/com/kingdee/service/match/`、`api-archive-scan/src/main/java/com/kingdee/service/Strategy/invoiceMatch/`

### 影像提交 / commit / submit / ERP
- **统一入口**: `POST /bill/scanner/commit`（ScanController.commitScanBill）
- **多 ERP 策略**: `StrategyContainer` 路由
  - `EASStrategyFactory` EAS
  - `CQStrategyFactory` 苍穹
  - `XingKongStrategyFactory` 星空
  - `EASAndCQStrategyFactory` EAS + 苍穹混合
  - `HDStrategyFactory` 弘鼎
- **同步通道**: `ScanService.commitToEas / commitToCouldXingkong / commitToCouldCangqiong / commitToOA`
- **token 管理**: `ScanService.getCloudcangqiongToken / getCloudcangqiongAppToken`
- **苍穹 token 传递**: `SystemTenantConfigEnum.ACCESS_IN_HEAD=1` 时通过 Header 传 `accessToken`
- **深入**: Read `api-archive-scan/src/main/java/com/kingdee/service/Strategy/erp/StrategyContainer.java`

### ERP 单据推送 / erpBillPush / 单据池通知 / FPZS
- **核心服务**: `SignPostBillService.saveErpBillPush / erpBillPush`
- **主表**: `t_erp_bill_push`
- **链路**: ERP 推送 → 异步入 `t_erp_bill_push` → 触发 FPZS 拉取（`HANDLE_FPZS_INFORM=1`）→ 入 `t_match_record` → 匹配触发
- **重试**: `ErpBillPushFpzsInformTask` + `RetryFpzsInformQueueTask`（XXL-JOB，按 ftenant 维度）
- **绑定凭证**: `POST /erpBingScanVoucher` 写 `t_scan_bill.fscan_voucher`

### 收单机 / 归档箱 / UEX / box
- **服务**: `UexMachineService`，UEX 厂商收单机器人
- **核心表**:
  - `t_uex_machine`(fserial_number) 机器
  - `t_uex_box`(fbox_number) 归档箱
  - `t_uex_upload_record` 投递记录
  - `t_uex_deduction_pick_record` 抵扣联领取
  - `t_receive_details / t_receive_invoice` 收单机端发票明细
- **业务流**: 扫码 → `/checkBillNo`(影像编号合法性) → 上传文件 → `/commitToBox`(投箱) → `/fullBox`(满箱关闭) → `/takeOutBox`(取出)
- **稽核**: `UexBoxStatisticsRejectBillVO` 统计退扫
- **打回通知**: `UexRejectBillNoticeTask`（XXL-JOB）短信通知管理员
- **入口**: `/bill/uex/*`（UEXController）+ `/receiving/*`（ReceivingMachineController）

### 签收单据 / signPostBill
- **服务**: `SignPostBillService`
- **核心表**: `t_sign_post_bill`(主) / `t_sign_post_detail_reimbursement`(明细)
- **流程**:
  - `POST /scanPostBillAdd` 新增签收单
  - `POST /scanPostDetailAdd` 添加报销单明细（addType 单条/批量）
  - `POST /boxAdd` 添加归档箱
  - `POST /billCommit` 提交签收
  - `POST /receiveAdd | /receiveSave` 接收（暂收 / 确认）
- **一键签收**: `oneClickSignSave`
- **计数维护**: `updateFpostReimbursementCount / updateFpostUexBoxSum`

### 档案归档推送 / pushToArchive / archive
- **服务**: `PushToArchiveService`
- **触发**: 提交完成（NoticeEnum.ALREADY=1）且 `fbusinessModel ∈ Constant.PUSH_ARCHIVE_MODEL` → 入队 `RedisConstant.COMMIT_BILL_PUSH_TO_ARCHIVE`
- **执行**: `PushToArchiveTask`（XXL-JOB）出队 → 组装 `ScanToArchivePushVO`（封面 / 附件 / 发票 + 标签）→ Feign `ArchiveRpcService.pushToArchive`
- **状态 farchivePushStatus**: 0=处理中 / 1=成功 / 2=失败

### 影像调阅 / H5 / 移动端
- **服务**: `H5ScanService`
- **入口**:
  - `getInfoByScanBillNo(scanBillDetail, fetchSource)`
  - `handH5ScanBillInfoByScanBillNo(scanBillNo, fetchSource, tenantNum)`
- **来源 fetchSource**: 1=报销岗(queryDetailForViewByExpense) / 2=扫描岗(queryDetailForViewByScan)
- **PDF base64 注入**: `fillPdfBase64IfNeeded` 按需注入
- **长图快照替换**: 末尾追加 `LongImageSnapshotService.replaceSnapshotIdsIfEnabled`（开关 `image.long-snapshot.enabled`）
- **深入**: Read `api-archive-scan/src/main/java/com/kingdee/service/h5/H5ScanService.java`

### 文件存储 / S3 / MinIO / MongoDB / fileId
- **双通道**: `MinIOUtils`（私有化 MinIO） + `AwsS3Helper`（公有云 S3），由 `${isPrivate}` 切换
- **关键能力**:
  - 预签名直传：`createUploadUrl(bucketName, objectName)`
  - 分片：`createUploadChunkUrlList(md5, chunkCount)` + `composeObject`
  - 读取：`getMinioInputStream(url, bucket)` / `getMinioStream`
  - 并发打包：`zipFileWriteWithRetry(piped, list)` 带重试
- **文件表**: `t_sa_file_info`（fileId / fileUrl / bucketName / fileSize / ftenantNum / fclientId）
- **历史快照**: MongoDB（`MongoDBService` / `MongoDBMapper`）服务老数据
- **MinIO 配置**: `AWS_S3` / `ACCESS_KEY_ID` / `SECRET_KEY_ID` / `minioUrl` / `minioUser` / `minioPassword`
- **深入**: Read `api-archive-scan/src/main/java/com/kingdee/util/imgsys/MinIOUtils.java`

### 缩略图 / 快照 / Thumbnail / Snapshot
- **任务**: `CreateThumbnailORSnapshotTask`（XXL-JOB Handler `CreateThumbnailORSnapshotTask` / `ThumbnailQueueTask`）
- **队列**: `RedisConstant.THUMBNAIL_SNAPSHOT` / `THUMB_QUEUE`
- **字段**: `ScanBillDetail.fscanThumbnailId`(缩略图) + `fscanSnapshotId`(快照)
- **长图快照（规划中）**: 新表 `t_scan_long_image_snapshot` 持久化「原 PDF fileId → 长图 fileId」映射

### 大文件上传 / largeFile / 分片
- **服务**: `LargeFileUplaodService` / `LargeFileUploadOutsideApiService`
- **入口**: `LargeFileUplaodController` / `LargeFileUploadOutsideApiController`
- **核心表**: `t_large_file`（含分片信息）

### 数据导出 / export
- **入口**: `POST /bill/export/generate` 生成 → `/downloadCheck` 校验 → `/get` 下载 → `/reload` 失败重做；批跑 `ExportTask`（XXL-JOB）
- **策略**: `ExportStrategy` + `@ExportComponent` 注解
  - `ExportScanBillListInfoImpl` 单据列表导出
  - `ExportScanBillListImageImpl` 单据列表带影像导出
  - `ExportScanViewBatchImageImpl` 批量影像视图导出
- **状态（ExportStatusEnum）**: WORKING / WORK_SUCCESS / WORK_FAILED
- **核心表**: `t_export_task` / `t_export_error` / `t_export_params`

### 文件标签 / Label / 附件类型
- **标签**: `LabelService` → `t_label`
- **附件模板**: `AttachmentTemplatePersistence` + `AttachmentFormatConfigPersistence`
  - `t_attachment_template` 模板
  - `t_attachment_template_label_relation` 模板↔标签
  - `t_format_config` 文件格式校验
- **影像 ↔ 标签**: `t_scan_bill_details_label_relation`
- **影像 ↔ 附件类型**: `t_scan_bill_details_attachment_type_relation`
- **批量打标签**: `ScanAttachmentService.batchSetAttachmentType(detailIds, attachmentTypeId, tenantNum)`

### 影像扫描点 / scanSpot / 抽检
- **服务**: `ScanSpotService`（采集物理位置 / 组织维度）+ `ScanStatisticsService`（随机抽样审核）
- **开关**: `COVER_NO_RULE_CHECK`（封面编号校验） / `SCAN_WITHOUT_COVER`（无封面采集）

### 跨系统迁移 / DKWS / 广西
- **服务**: `GxScanSyncService`（广西） / `DkwsScanInfoService`（DKWS）
- **任务**: `DKWSScanMoveTask`（@XxlJob `DKWSScanMoveTask`） / `GXDataRepairTask`（@XxlJob `gxDataRepairTask`）
- **核心表**: `t_dkws_scan_info` / `t_dkws_scan_info_record` / `t_gx_scan_sync_info`
- **入口**: `/scan/getOutsideScanData` / `/scan/syncOutsideScanData` / `/scan/addOutsideScanUser`

### 通用同步任务 / DataSyncTask
- **服务**: `DataSyncTaskService`
- **任务**: `DataSyncTaskJob`（Handler `DataSyncTask` / `AutoDataSyncTask` / `DealDataSyncTaskError`）
- **核心表**: `t_data_sync_task` / `t_data_sync_task_details`

### 操作日志 / 审计
- **业务级**: `ScanOperatingRecordService` → `t_scan_operating_record`（`ScanOperateContentEnum` + `ScanOperateContentActionEnum`）
- **租户级**: `RecordLogService` → `t_record_log` + `t_record_log_details`
- **异步**: `scanOperatingRecordService.asyncScanBillRecord(oldBill, newBill, errCode, desc, action, currentUser)`

### 租户配置 / SystemTenantConfigEnum / 开关
- **入口**: `TenantExternalConfigService` / RPC `InvoiceRpcService.getTenantExternalConfig`
- **存储**: `t_tenant_external_config`（`fcode` = `SystemTenantConfigEnum.code`）
- **常用开关**: `ELECTRIC_ATTACHMENT_UP` / `ELECTRIC_INVOICE_MATCH` / `NO_MATCH_INVOICE_DELETE` / `BASIC_MODE_CHECK` / `INVOICE_NUM_MATCH_CHECK` / `COVER_NO_RULE_CHECK` / `SCAN_WITHOUT_COVER` / `IMPORT_FILE_TYPE_CATEGORY` / `HANDLE_FPZS_INFORM` / `IMAGE_DISPLAY_SEQUENCE` / `REVIEW_WATERMARK_DISPLAY` / `MATCH_VIEW_V2` / `ACCESS_IN_HEAD`
- **深入**: Read `api-archive-scan/src/main/java/com/kingdee/enums/SystemTenantConfigEnum.java`

### 用户配置 / UserConfigurationEnum
- **入口**: `api-archive-organization`（用户级偏好），通过 `UserConfigurationDTO` 传至 H5
- **典型用法**: H5 调阅时的展示偏好（顺序 / 默认页 / 水印开关）
- **深入**: Read `api-archive-organization/src/main/java/com/kingdee/enums/UserConfigurationEnum.java`

### 影像化补偿 / ImagingCompensationTask
- **任务**: `ImagingCompensationTask` + `RetryFpzsInformTask`（XXL-JOB）
- **目标**: 补偿因网络/服务波动导致的影像生成缺失
- **状态**: 0=失败 / 1=成功 / 2=处理中

### 自研 MQ / FPY MQ / Redis 队列
- **包**: `com.kingdee.fpy`
- **注解**: `@KingMqProducer`(生产) / `@KingMqConsumer`(消费) / `@MqService`(服务声明)
- **触发器**: `MqConsumerTrigger`（本地 `LocalMqConsumerTrigger`）
- **底层**: `RedissonMqQueue` 基于 Redisson 的有序队列 + `HashMqQueueStrategy`
- **配置**: `RedissonMqProperties`（`spring.fpy.mq.*`）
- **XXL-JOB Handler**: `consumerMq`

### XXL-JOB 任务清单（api-archive-scan）

| JobHandler | 作用 |
|---|---|
| BillUploadRedisQueueTask | 文件上传异步识别查验 |
| MatchCheckQueueTask | 匹配查验队列 |
| InformSysDataRedisQueueTask | 单据池通知 |
| CommitRetryQueueTask | 提交重试 |
| CreateThumbnailORSnapshotTask / ThumbnailQueueTask | 缩略图 / 快照 |
| S3FileUploadQueueTask / ScanFileUploadQueueTaskNew / ScanFileUploadTenantTask / FileUploadQueueTask / RetryFpzsInformQueueTask | S3 / 文件上传 |
| S3OldFileDeleteTask | 老文件清理（按 t_file_aging 30 天） |
| PushToArchiveTask | 档案推送 |
| ImagingCompensationTask / RetryFpzsInformTask | 影像化补偿 |
| ErpBillPushFpzsInformTask / ErpBillPushFpzsInformByFtenant | ERP 推送至 FPZS |
| ExportTask | 导出执行器 |
| DataSyncTask / AutoDataSyncTask / DealDataSyncTaskError | 数据同步 |
| DKWSScanMoveTask | DKWS 影像搬移 |
| gxDataRepairTask | 广西影像数据修复 |
| DealInvoiceMatchHashTask | 发票匹配 hash 维护 |
| UexRejectBillNoticeTask | 收单机打回单据短信 |
| ScanVersionManagerTask | 扫描版本上线状态 |
| MenuSyncTask | 菜单同步 |
| EopDataSyncTask | 运营数据同步至 base-platform-adapter |
| ScanRetryHandleTask | 近 3 天提交失败重试 |
| consumerMq | FPY 自研 MQ 消费 |
| ImageDataSyncTask | 凌晨 0 点统计租户影像数同步至 EOP |

---

## 四、核心表 / 状态机速查

### 主要业务表

| 表名 | 用途 |
|------|------|
| `t_scan_bill` | 影像主表，主键 `fid`，业务键 `(ftenant_num, fscan_bill_no)` |
| `t_scan_bill_details` | 影像明细（封面 / 发票 / 附件） |
| `t_scan_bill_details_record` | 退扫历史明细 |
| `t_scan_bill_files_relation` | 影像 ↔ 文件关系 |
| `t_scan_files` | 文件元信息（fileUrl / bucketName / fileType） |
| `t_sa_file_info` | 文件统一信息（fileId / fileUrl / bucketName） |
| `t_scan_invoice_relation` | 影像明细 ↔ 发票池 |
| `t_invoice_pool` | 发票池（汇总各类发票） |
| `t_scan_operating_record` | 影像操作日志 |
| `t_scan_attachment` | 影像附件 |
| `t_attachment_template` / `t_format_config` | 附件模板与文件格式配置 |
| `t_label` / `t_scan_bill_details_label_relation` | 标签 + 关系 |
| `t_match_record` / `t_match_cover` / `t_match_attachment` / `t_match_invoice_info` / `t_match_invoice_scan` | 匹配主链路 |
| `t_erp_bill_push` | ERP 推送单据 |
| `t_sign_post_bill` / `t_sign_post_detail_reimbursement` | 签收单据 + 明细 |
| `t_uex_machine` / `t_uex_box` / `t_uex_upload_record` / `t_uex_deduction_pick_record` | 收单机生态 |
| `t_receive_details` / `t_receive_invoice` | 收单机端发票明细 |
| `t_export_task` / `t_export_error` / `t_export_params` | 导出任务体系 |
| `t_data_sync_task` / `t_data_sync_task_details` | 数据同步任务 |
| `t_dkws_scan_info` / `t_dkws_scan_info_record` / `t_gx_scan_sync_info` | 跨系统迁移 |
| `t_file_aging` | 文件 S3 老化清理 |
| `t_compress_file` | 压缩文件元信息 |
| `t_record_log` / `t_record_log_details` | 租户级操作日志 |
| `t_inform_record` | 通知记录 |
| `t_air_ticket` / `t_train_tickets` / `t_taxi_tickets` / `t_vat_*_invoice` 等 | 各类发票分表（与 invoice 项目共享） |
| `t_scan_long_image_snapshot` | （规划中）长图快照映射表 |

### 状态枚举速查

| 枚举 | 取值 | 说明 |
|------|------|------|
| `ScanBill.fscanStatus` | 1/2/3/4/5/6/7/8/9 | 影像已上传 / 影像已提交 / 影像审核完成 / 影像有误待重扫 / 影像匹配失败 / 单据处理失败异常 / 识别查验完成 / 影像匹配成功 / 单据被删除 |
| `ScanBillDetail.fscanType` | 1/2/3 | 发票 / 附件 / 大文件（ScanDetailTypeEnum） |
| `ScanBillDetail.ffileType` | 1/2/3/4 | PDF / IMG / OTHER / EXCEL（Constant.FILE_TYPE_*） |
| `ScanBillDetail.fdelFlag` | 0/1 | 正常 / 删除 |
| `ScanBillDetail.fretreatScanStatus` | 0/1/2/3/4 | 正常提交 / 退扫后未调整 / 退扫后已调整 / 退扫后新增 / 退扫后手工确认正常 |
| `ScanBill.farchivePushStatus` | 0/1/2 | 处理中 / 成功 / 失败（PushToArchiveService 维护） |
| `ScanBill.fbusinessModel` | 1~6 | ScanModeTypeEnum（基础/匹配/同步/稽核/人工/附件） |
| `NoticeEnum` | 1/2/3 | 已就绪 / 影像退扫 / 影像审核 |
| `ScanBillRecognitionTypeEnum` | 0/1/2 | 封面 / 发票 / 附件 |
| `ExportStatusEnum` | WORKING / WORK_SUCCESS / WORK_FAILED | 导出任务状态 |
| `ElectronicInvoiceTypeEnum` | 0/1/2 | 纸票 / 电票 / 其他 |
| `RetreatScanStatusEnum` | 同上 fretreatScanStatus | 退扫子状态 |
| `PlaceType` | — | 存放视图类型 |
| `ProcessType` | — | 流程类型 |
| `ScanSpotTypeEnum` | — | 抽检类型 |
| `ScanHomeUrlStatusEnum` | — | 首页 URL 状态 |
| `UploadModeEnum` | — | 影像上传方式 |

---

## 五、版本管理 / 升级规则

- **版本号格式**: `YY.MM.VX`（如 `26.03.V1`）
- **升级触发**:
  - `archive-dataSource-utils` / `archive-pub-utils` 字段或工具类变更 → 上层服务必须升版本号
  - `api-archive-invoice` Mapper / 表字段变更 → `api-archive-scan` 需升版本号
- **依赖链**:
  ```
  archive-dataSource-utils ─┐
  archive-pub-utils ────────┴──→ api-archive-invoice ─→ api-archive-scan
                                                     ↘ api-archive-organization
  ```
- **数据库变更 DDL**:
  - 标准放置：`api-archive-{xxx}/db/*.ddl` 或 `db/`
  - DDL 必须**幂等**（`CREATE TABLE IF NOT EXISTS`、动态判 `information_schema` 后建索引）
  - 范式参考：`api-archive-scan/db/` 下已有 DDL 为准（相对 `{BILLING_CODE_BASE_DIR}/input-project/standard/input/`）

---

## 六、全量文档索引

### 标准版后端（相对 `{BILLING_CODE_BASE_DIR}/input-project/standard/input/`）

| 文档路径 | 说明 |
|---------|------|
| `api-archive-scan/README_ImageDataSyncTask.md` | 凌晨 0 点同步租户影像数到 EOP |
| `api-archive-scan/db/` | 影像项目 DDL 存放点 |
| `api-archive-invoice/db/试用账号初始化租户过期字段.ddl` | 试用账号 DDL |
| `api-archive-job/db/xxl-job-ddl-mysql.sql` | XXL-JOB Admin 表 DDL |

### 标准版前端（相对 `{BILLING_CODE_BASE_DIR}/input-project/standard/frontend/`）

| 仓库 | 说明 |
|------|------|
| `image-system/` | 影像管理主站（Egg.js + React + Dva），对应后端 `api-archive-scan` |
| `image-asst/` | 影像助手（Egg.js + React + Recoil），对应后端 `api-archive-scan` |

### 重点源码索引（相对 `{BILLING_CODE_BASE_DIR}/input-project/standard/input/`）

| 源码路径 | 说明 |
|---------|------|
| `api-archive-scan/src/main/java/com/kingdee/service/scan/ScanService.java` | 扫描主服务（3800+ 行，几乎所有扫描业务的中枢） |
| `api-archive-scan/src/main/java/com/kingdee/service/scan/ScanBillBusinessService.java` | 扫描业务接口（采集 → 保存 → 提交） |
| `api-archive-scan/src/main/java/com/kingdee/service/h5/H5ScanService.java` | H5 调阅业务 |
| `api-archive-scan/src/main/java/com/kingdee/service/match/MatchService.java` | 匹配核心 |
| `api-archive-scan/src/main/java/com/kingdee/service/submit/ScanBillSubmitService.java` | 提交接口（基础/匹配/同步） |
| `api-archive-scan/src/main/java/com/kingdee/service/scan/PushToArchiveService.java` | 档案归档推送 |
| `api-archive-scan/src/main/java/com/kingdee/service/SignPostBill/SignPostBillService.java` | 签收单据 |
| `api-archive-scan/src/main/java/com/kingdee/service/uex/UexMachineService.java` | 收单机 / 归档箱 |
| `api-archive-scan/src/main/java/com/kingdee/service/export/ExportService.java` | 导出策略容器 |
| `api-archive-scan/src/main/java/com/kingdee/service/Strategy/erp/StrategyContainer.java` | ERP 多产品线提交策略 |
| `api-archive-scan/src/main/java/com/kingdee/service/Strategy/recognition/InvoiceRecognitionStrategyContainer.java` | 识别供应商策略 |
| `api-archive-scan/src/main/java/com/kingdee/service/Strategy/invoiceMatch/InvoiceMatchStrategyContainer.java` | 发票类型匹配策略 |
| `api-archive-scan/src/main/java/com/kingdee/enums/SystemTenantConfigEnum.java` | 租户级开关枚举 |
| `api-archive-scan/src/main/java/com/kingdee/enums/ScanModeTypeEnum.java` | 影像模式枚举 |
| `api-archive-scan/src/main/java/com/kingdee/util/Constant.java` | 全局常量（FILE_TYPE / NUMBER_STATUS / PUSH_ARCHIVE_MODEL） |
| `api-archive-scan/src/main/java/com/kingdee/util/imgsys/MinIOUtils.java` | 文件存储工具（MinIO / S3 双通道） |
| `api-archive-scan/src/main/resources/mapper/scan/ScanMapper.xml` | 扫描主表 SQL（含查询拼接逻辑） |

---

## 七、知识库更新指引

新增条目时：
1. **新场景 / 功能** → 在「三、关键词 → 上下文映射」中按业务分组追加，附「调用链 / 核心类 / 关键字段 / 深入指针」
2. **新表 / 字段变更** → 「四、核心表 / 状态机速查」补充行
3. **新 XXL-JOB** → 「三 - XXL-JOB 任务清单」追加 JobHandler 行
4. **新 ERP / 识别供应商策略** → 在对应「Strategy / Factory」条目追加；记得在 `StrategyContainer` 注册
5. **新增文档** → 「六、全量文档索引」追加路径与说明
6. **服务调用关系变更** → 更新「二、服务调用关系」图

扫描新文档命令：
```bash
find {BILLING_CODE_BASE_DIR}/input-project/standard/input -path "*/db/*.ddl" -o -name "*.md" | grep -v target | grep -v node_modules | sort
```
