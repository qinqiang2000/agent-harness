# 收票系统目录映射

## 标准版项目结构

### JDK 8 版本（standard/input/）

```
api-invoice-collector/          # 发票采集服务
├── src/main/java/
│   ├── controller/            # REST控制器
│   │   ├── MailController.java           # 邮箱取票接口
│   │   ├── ScanController.java           # 扫描取票接口
│   │   └── ManualController.java         # 手工录入接口
│   ├── service/               # 业务服务
│   │   ├── MailService.java              # 邮箱服务
│   │   ├── RecognitionRpcService.java    # 识别服务
│   │   ├── VerificationService.java      # 查验服务
│   │   ├── InputInvoiceService.java      # 入库服务
│   │   └── ArchiveService.java           # 归档服务
│   ├── job/                   # 定时任务
│   │   ├── MailFolderScanJob.java        # 邮箱扫描
│   │   └── MailTaskProcessJob.java       # 邮件处理
│   └── util/                  # 工具类
│       ├── FileHashUtils.java            # 文件Hash
│       └── InvoiceDeduplicator.java      # 发票去重
└── docs/
    └── 邮箱取票设计文档.md

api-invoice-input-db/           # 数据库模型
├── entity/                    # 实体类
│   ├── Invoice.java                      # 发票实体
│   ├── MailTask.java                     # 邮件任务
│   └── Certificate.java                  # 附件实体
└── mapper/                    # MyBatis Mapper
    ├── InvoiceMapper.java
    └── MailTaskMapper.java

api-invoice-input-query/        # 查询服务
└── service/
    └── InvoiceQueryService.java
```

### JDK 21 版本（refactor/input/）

```
fpy-isv/                        # ISV服务（独立项目）
├── check/                     # 查验模块
│   └── adapter/               # 供应商适配器
│       ├── ChangruanAdapter.java         # 长软
│       ├── LeqiAdapter.java              # 乐企
│       └── QixiangyunAdapter.java        # 企享云
├── constants/                 # 枚举常量
│   ├── InvoiceTypeEnum.java
│   └── InvoiceStatusEnum.java
└── dto/                       # 数据传输对象
    ├── request/
    └── response/

fpy-base-query/                 # 查询服务（响应式）
└── service/
    └── InvoiceQueryService.java

fpy-sdk-base/                   # 基础SDK
└── model/
    └── Invoice.java
```

## 旗舰版项目结构

```
api-invoice-frame/              # 旗舰版接口应用
├── controller/
│   └── FirmamentController.java          # 统一入口
│       └── /m3/bill/firmament/img/handle
├── service/
│   ├── EventDispatcher.java              # 事件分发
│   └── StandardInvoker.java              # 标准版调用
└── docs/
    └── 旗舰版接口对接文档.md
```

## 数据库表映射

### 发票主表（按类型分表）

```
t_bill_*                        # 发票主表
├── t_bill_vat_special          # 增值税专用发票
├── t_bill_vat_normal           # 增值税普通发票
├── t_bill_electronic           # 电子发票
└── ...
```

### 邮箱取票相关表

```
t_mail_task                     # 邮件任务表
t_mail_task_detail              # 任务明细表
t_mail_config                   # 邮箱配置表
```

### 附件相关表

```
t_fpzs_certificate              # 附件表
t_certifacate_belong_relation   # 附件关联表
```

## 配置文件位置

### 标准版

```
application.yml                 # 主配置
application-dev.yml             # 开发环境
application-prod.yml            # 生产环境
```

### 旗舰版

```
api-invoice-frame/
└── application.yml             # 接口应用配置
```

## 关键配置项

### 邮箱配置

```yaml
mail:
  imap:
    host: imap.example.com
    port: 993
    ssl: true
  scan:
    cron: "0 */5 * * * ?"       # 每5分钟扫描
```

### 识别服务配置

```yaml
recognition:
  ocr:
    url: http://ocr-service/api/recognize
    timeout: 30000
```

### 查验服务配置

```yaml
verification:
  changruan:
    url: http://changruan-api/verify
    appKey: xxx
  leqi:
    url: http://leqi-api/verify
    appKey: xxx
```

## 日志位置

```
logs/
├── collector.log               # 采集服务日志
├── recognition.log             # 识别服务日志
├── verification.log            # 查验服务日志
└── error.log                   # 错误日志
```
