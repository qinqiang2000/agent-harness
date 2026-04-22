# 服务名 → GitLab 仓库映射

日志中 `project` 打印的服务名与 GitLab 实际仓库路径可能不一致，查此表获取正确的 `project_id`。

---

## piaozone（test-master.piaozone.com）

**GitLab Base URL**: `https://test-master.piaozone.com/git/`，clone 地址格式：`https://token:$GITLAB_TOKEN@test-master.piaozone.com/git/{project_id}.git`

| 日志服务名 (project) | GitLab 仓库路径 (project_id) | 描述                       |
|---|---|--------------------------|
| smkp | piaozone/output/bill-smkp | 输出层-税控开票服务               |
| api-invoice-frame | piaozone/base/api-invoice-frame | 基础层-发票框架服务               |
| api-invoice-data-collector | piaozone/base/api-invoice-data-collector | 基础层-发票数据采集服务             |
| api-invoice-order | piaozone/base/api-invoice-order | 基础层-发票订单服务               |
| api-invoice-pdf | piaozone/base/api-invoice-pdf | 基础层-发票 PDF 处理服务          |
| api-invoice-ofdfile | piaozone/base/api-invoice-ofdfile | 基础层-发票 OFD 文件服务          |
| api-auth | piaozone/base/api-auth | 基础层-鉴权认证服务               |
| api-storage | piaozone/base/api-storage | 基础层-存储服务                 |
| api-simulate | piaozone/base/api-simulate | 基础层-模拟/仿真服务              |
| api-express | piaozone/base/api-express | 基础层-快递/物流服务              |
| api-bdkp | piaozone/base/api-bdkp | 基础层-百旺开票服务               |
| api-kds | piaozone/base/api-kds | 基础层-KDS 服务               |
| api-pdf-analysis | piaozone/base/api-pdf-analysis | 基础层-PDF 解析服务             |
| api-service-timer | piaozone/base/api-service-timer | 基础层-定时任务服务               |
| api-company | piaozone/base/api-company | 基础层-企业信息服务               |
| api-cost-calculation | piaozone/base/api-cost-calculation | 基础层-费用计算服务               |
| api-exception-report | piaozone/base/api-exception-report | 基础层-异常上报服务               |
| api-base-operation | piaozone/base/api-base-operation | 基础层-基础运营服务               |
| api-mcp-frame | piaozone/base/api-mcp-frame | 基础层-MCP 框架服务             |
| api-mcp-server | piaozone/base/api-mcp-server | 基础层-MCP Server 服务        |
| api-invoice-check | piaozone/input/api-invoice-check | 进项-发票查验服务                |
| api-invoice-collector | piaozone/input/api-invoice-collector | 进项-发票采集服务                |
| api-invoice-recognition | piaozone/input/api-invoice-recognition | 进项-发票识别服务                |
| api-invoice-input-db | piaozone/input/api-invoice-input-db | 进项-发票数据库服务               |
| api-invoice-input-query | piaozone/input/api-invoice-input-query | 进项-发票查询服务                |
| api-invoice-input-query-v2 | piaozone/input/api-invoice-input-query-v2 | 进项-发票查询服务 v2             |
| api-fpzs | piaozone/input/api-fpzs | 进项-发票助手服务，日志服务名fpzs      |
| api-expense | piaozone/input/api-expense | 进项-报销合规校验服务              |
| api-invoice-manage | piaozone/input/api-invoice-manage | 进项-发票管理服务                |
| api-invoice-image | piaozone/input/api-invoice-image | 进项-发票影像服务                |
| api-invoice-ofd-analysis | piaozone/input/api-invoice-ofd-analysis | 进项-OFD 解析服务              |
| api-invoice-pdf-analysis | piaozone/input/api-invoice-pdf-analysis | 进项-PDF 解析服务              |
| api-invoice-check-noencrypt | piaozone/input/api-invoice-check-noencrypt | 进项-发票查验服务（非加密）           |
| api-invoice-check-util | piaozone/input/api-invoice-check-util | 进项-发票查验工具服务              |
| api-invoice-erp-client | piaozone/input/api-invoice-erp-client | 进项-ERP 客户端适配服务           |
| api-invoice-deduction-adapter | piaozone/input/api-invoice-deduction-adapter | 进项-归集和抵扣业务适配器（已适配微乐接口）   |
| api-msg-parser-utils | piaozone/input/api-msg-parser-utils | 进项-消息解析工具服务              |
| api-push-socket | piaozone/input/api-push-socket | 进项-消息推送 Socket 服务        |
| api-push-service | piaozone/input/api-push-service | 进项-消息推送服务                |
| api-account | piaozone/input/api-account | 进项-账户管理服务                |
| api-socketio-server | piaozone/input/socketio/api-socketio-server | 进项-SocketIO 服务端          |
| api-socketio-client | piaozone/input/socketio/api-socketio-client | 进项-SocketIO 客户端          |
| api-socketio-webclient | piaozone/input/socketio/api-socketio-webclient | 进项-SocketIO Web 客户端      |
| api-invoice-create | piaozone/output/api-invoice-create | 输出层-发票开具服务               |
| api-invoice-output-query | piaozone/output/api-invoice-output-query | 输出层-发票查询服务               |
| api-invoice-sm | piaozone/output/api-invoice-sm | 输出层-税务服务                 |
| api-company-search | piaozone/output/api-company-search | 输出层-企业查询服务               |
| api-hotel | piaozone/output/api-hotel | 输出层-酒店发票服务               |
| api-interface | piaozone/output/api-interface | 输出层-对外接口服务               |
| api-invoice-input-utils | piaozone/common/api-invoice-input-utils | 公共-进项工具包                 |
| api-invoice-utils | piaozone/common/api-invoice-utils | 公共-发票工具包                 |
| api-ofd-utils | piaozone/common/api-ofd-utils | 公共-OFD 工具包               |
| api-pdf-utils | piaozone/common/api-pdf-utils | 公共-PDF 工具包               |
| api-xbrl-utils | piaozone/common/api-xbrl-utils | 公共-XBRL 工具包              |
| api-aws-s3 | piaozone/common/api-aws-s3 | 公共-AWS S3 存储工具包          |
| api-signature-utils | piaozone/common/api-signature-utils | 公共-签名工具包                 |
| api-database-utils | piaozone/common/api-database-utils | 公共-数据库工具包                |
| api-elc-digital-invoice | piaozone/elc-integration/api-elc-digital-invoice | 集成层-全电发票服务               |
| api-elc-invoice-lqpt | piaozone/elc-integration/api-elc-invoice-lqpt | 集成层-乐企票通适配服务             |
| api-elc-invoice-create | piaozone/elc-integration/api-elc-invoice-create | 集成层-全电平台开票适配器（微乐/乐企/RPA） |
| api-elc-invoice-collect | piaozone/elc-integration/api-elc-invoice-collect | 集成层-全电发票采集服务             |
| api-elc-invoice-utils | piaozone/elc-integration/api-elc-invoice-utils | 集成层-集成组公共 util 包         |
| api-elc-invoice-gjfp | piaozone/elc-integration/api-elc-invoice-gjfp | 集成层-国家发票平台适配服务           |
| api-elc-invoice-lqly | piaozone/elc-integration/api-elc-invoice-lqly | 集成层-乐企来源适配服务             |
| api-elc-invoice-imputation | piaozone/elc-integration/api-elc-invoice-imputation | 集成层-发票归集服务               |
| api-elc-invoice-engine | piaozone/elc-integration/api-elc-invoice-engine | 集成层-全电发票引擎服务             |
| api-gateway | piaozone/imgsys-archive/api-gateway | 影像档案-网关服务                |
| api-archive | piaozone/imgsys-archive/api-archive | 影像档案-档案管理服务              |
| api-archive-scan | piaozone/imgsys-archive/api-archive-scan | 影像档案-扫描服务                |
| api-archive-scan-move | piaozone/imgsys-archive/api-archive-scan-move | 影像档案-扫描文件迁移服务            |
| api-archive-organization | piaozone/imgsys-archive/api-archive-organization | 影像档案-组织机构服务              |
| api-archive-machine-manage | piaozone/imgsys-archive/api-archive-machine-manage | 影像档案-设备管理服务              |
| api-archive-license | piaozone/imgsys-archive/api-archive-license | 影像档案-授权许可服务              |
| api-archive-invoice | piaozone/imgsys-archive/api-archive-invoice | 影像档案-发票档案服务              |
| api-archive-webservice | piaozone/imgsys-archive/api-archive-webservice | 影像档案-WebService 接口服务     |
| api-archive-job | piaozone/imgsys-archive/api-archive-job | 影像档案-定时任务服务              |
| api-archive-alarm-monitor | piaozone/imgsys-archive/api-archive-alarm-monitor | 影像档案-告警监控服务              |
| api-document | piaozone/product/api-document | 产品-文档服务                  |
| base-file-center | piaozone/base/base-file-center | 基础层-文件中心服务               |
| bill-organization | piaozone/base/bill-organization | 基础层-组织机构服务               |
| bill-account-statement | piaozone/output/bill-account-statement | 输出层-账单对账服务               |
| bill-portal | piaozone/base/bill-portal | 基础层-门户 PC 端              |
| bill-portal-h5 | piaozone/base/bill-portal-h5 | 基础层-门户 H5 端              |
| bill-bm-ocr-invoice | piaozone/input/bill-bm-ocr-invoice | 进项-百望 OCR 发票识别服务         |
| bill-input-account-manage-portal | piaozone/input/bill-input-account-manage-portal | 进项-账户管理门户                |
| bill-input-account-wechat-applet-portal | piaozone/input/bill-input-account-wechat-applet-portal | 进项-微信小程序账户门户             |
| base-cosmic-init | piaozone/base/base-cosmic-init | 基础层-苍穹初始化服务              |
| bill-operate-report | piaozone/base/bill-operate-report | 基础层-运营报表服务               |
| base-order | piaozone/base/base-order | 基础层-订单服务                 |
| base-iam | piaozone/base/base-iam | 基础层-身份与访问管理服务            |
| bill-business-cms | piaozone/base/bill-business-cms | 基础层-业务 CMS 服务            |
| bill-expense | piaozone/base/bill-expense | 基础层-报销服务                 |
| wechat-mini-program | piaozone/input/bill-wechat-mini-program | 进项-微信小程序（注意：日志服务名与仓库名不同） |
| base-platform-adapter | piaozone/base/base-platform-adapter | 基础层-平台适配服务               |
| bill-websocket | piaozone/output/bill-websocket | 输出层-WebSocket 推送服务       |
| base-ai-portal | piaozone/base/base-ai-portal | 基础层-AI 门户服务              |
| base-ai-llm | piaozone/base/base-ai-llm | 基础层-AI 大模型服务             |
| base-ai-data-match | piaozone/base/base-ai-data-match | 基础层-AI 数据匹配服务            |
| base-ai-python | piaozone/base/base-ai-python | 基础层-AI Python 服务         |
| base-ai-file-cls | piaozone/base/base-ai-file-cls | 基础层-AI 文件分类服务            |
| base-monitor-collect | piaozone/base/base-monitor-collect | 基础层-监控采集服务               |
| base-llm-config | piaozone/base/base-llm-config | 基础层-大模型配置服务              |
| base-chat-service | piaozone/base/base-chat-service | 基础层-对话服务                 |
| base-chat-service-web | piaozone/base/base-chat-service-web | 基础层-对话服务 Web 端           |
| base-log-alert | piaozone/base/base-log-alert | 基础层-日志告警服务               |
| base-online-view | piaozone/base/base-online-view | 基础层-在线预览服务               |
| base-gateway | piaozone/base/base-gateway | 基础层-网关服务                 |
| base-auth | piaozone/base/base-auth | 基础层-认证服务                 |
| base-cost | piaozone/base/base-cost | 基础层-费用服务                 |
| base-rights | piaozone/base/base-rights | 基础层-权限服务                 |
| bill-gateway | piaozone/base/bill-gateway | 基础层-发票云网关                |
| base-file-center-server | piaozone/base/base-file-center-server | 基础层-文件中心服务端              |
| fpy-isv | piaozone-v2/app/fpy-isv | 应用层-ISV 应用服务             |
| fpy-ar-invoice-ontology | piaozone-v2/app/fpy-ar-invoice-ontology | 应用层-AR 发票本体服务            |
| fpy-app-financial-client | piaozone-v2/app/fpy-app-financial-client | 应用层-财政客户端                |
| fpy-base-query | piaozone-v2/base/fpy-base-query | 基础层-查询服务                 |
| fpy-base-recognition | piaozone-v2/base/fpy-base-recognition | 基础层-识别服务                 |
| fpy-business-invoice | piaozone-v2/business/fpy-business-invoice | 聚合层-发票业务服务               |
| fpy-sdk-base | piaozone-v2/sdk/fpy-sdk-base | SDK-基础包，含模型和 util        |
| fpy-sdk-cover | piaozone-v2/sdk/fpy-sdk-cover | SDK-转换 model             |
| fpy-sdk-db-jpa | piaozone-v2/sdk/fpy-sdk-db-jpa | SDK-JPA 数据库操作            |
| fpy-sdk-db-mybatis | piaozone-v2/sdk/fpy-sdk-db | SDK-MyBatis 数据库操作        |
| fpy-sdk-call | piaozone-v2/sdk/fpy-sdk-call | SDK-调用工具                 |
| fpy-sdk-rpc | piaozone-v2/sdk/fpy-sdk-rpc | SDK-内部调用接口               |
| fpy-parent | piaozone-v2/fpy-parent | 项目父类 POM                 |

> 如需新增映射，按格式在表格中追加一行即可。
