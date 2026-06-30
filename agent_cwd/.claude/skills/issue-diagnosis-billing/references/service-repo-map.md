# 服务名 → GitLab 仓库映射

日志中 `project` 打印的服务名与 GitLab 实际仓库路径可能不一致，查此表获取正确的 `project_id`。

---

**GitLab Base URL**: 由环境变量 `GITLAB_BASE_URL` 控制，默认 `http://123.207.158.7:5000/ai-agent/git`

clone 地址格式：`http://token:$GITLAB_TOKEN@{GITLAB_BASE_URL}/{project_id}.git`

---

## piaozone — 标准版开票/收票/影像服务

| 日志服务名 (project) | GitLab 仓库路径 (project_id) | 描述 |
|---|---|---|
| smkp | piaozone/output/bill-smkp | 输出层-税控开票服务 |
| api-invoice-frame | piaozone/base/api-invoice-frame | 基础层-发票框架服务 |
| api-invoice-order | piaozone/base/api-invoice-order | 基础层-发票订单服务 |
| api-invoice-pdf | piaozone/base/api-invoice-pdf | 基础层-发票 PDF 处理服务 |
| api-invoice-ofdfile | piaozone/base/api-invoice-ofdfile | 基础层-发票 OFD 文件服务 |
| api-auth | piaozone/base/api-auth | 基础层-鉴权认证服务 |
| api-storage | piaozone/base/api-storage | 基础层-存储服务 |
| api-bdkp | piaozone/base/api-bdkp | 基础层-百旺开票服务 |
| api-kds | piaozone/base/api-kds | 基础层-KDS 服务 |
| api-pdf-analysis | piaozone/base/api-pdf-analysis | 基础层-PDF 解析服务 |
| api-company | piaozone/base/api-company | 基础层-企业信息服务 |
| api-invoice-check | piaozone/input/api-invoice-check | 进项-发票查验服务 |
| api-invoice-collector | piaozone/input/api-invoice-collector | 进项-发票采集服务 |
| api-invoice-recognition | piaozone/input/api-invoice-recognition | 进项-发票识别服务 |
| api-invoice-input-db | piaozone/input/api-invoice-input-db | 进项-发票数据库服务 |
| api-invoice-input-query | piaozone/input/api-invoice-input-query | 进项-发票查询服务 |
| api-invoice-input-query-v2 | piaozone/input/api-invoice-input-query-v2 | 进项-发票查询服务 v2 |
| api-invoice-input-utils | piaozone/common/api-invoice-input-utils | 进项-公共工具包（RPC接口/DTO/枚举） |
| api-fpzs | piaozone/input/api-fpzs | 进项-发票助手服务（日志服务名 fpzs） |
| fpzs | piaozone/input/api-fpzs | 进项-发票助手服务（别名） |
| api-expense | piaozone/input/api-expense | 进项-报销合规校验服务 |
| api-invoice-manage | piaozone/input/api-invoice-manage | 进项-发票管理服务 |
| api-invoice-image | piaozone/input/api-invoice-image | 进项-发票影像服务 |
| api-invoice-ofd-analysis | piaozone/input/api-invoice-ofd-analysis | 进项-OFD 解析服务 |
| api-invoice-pdf-analysis | piaozone/input/api-invoice-pdf-analysis | 进项-PDF 解析服务 |
| api-invoice-erp-client | piaozone/input/api-invoice-erp-client | 进项-ERP 客户端适配服务 |
| api-invoice-create | piaozone/output/api-invoice-create | 输出层-发票开具服务 |
| api-invoice-output-query | piaozone/output/api-invoice-output-query | 输出层-发票查询服务 |
| api-invoice-sm | piaozone/output/api-invoice-sm | 输出层-税务服务 |
| api-interface | piaozone/output/api-interface | 输出层-对外接口服务 |
| api-gateway | piaozone/imgsys-archive/api-gateway | 影像档案-网关服务 |
| api-archive | piaozone/imgsys-archive/api-archive | 影像档案-档案管理服务 |
| api-archive-scan | piaozone/imgsys-archive/api-archive-scan | 影像档案-扫描服务 |
| api-archive-scan-move | piaozone/imgsys-archive/api-archive-scan-move | 影像档案-扫描文件迁移服务 |
| api-archive-organization | piaozone/imgsys-archive/api-archive-organization | 影像档案-组织机构服务 |
| api-archive-machine-manage | piaozone/imgsys-archive/api-archive-machine-manage | 影像档案-设备管理服务 |
| api-archive-license | piaozone/imgsys-archive/api-archive-license | 影像档案-授权许可服务 |
| api-archive-invoice | piaozone/imgsys-archive/api-archive-invoice | 影像档案-发票档案服务 |
| api-archive-webservice | piaozone/imgsys-archive/api-archive-webservice | 影像档案-WebService 接口服务 |
| api-archive-job | piaozone/imgsys-archive/api-archive-job | 影像档案-定时任务服务 |
| api-archive-alarm-monitor | piaozone/imgsys-archive/api-archive-alarm-monitor | 影像档案-告警监控服务 |
| api-elc-digital-invoice | piaozone/elc-integration/api-elc-digital-invoice | 集成层-全电发票服务 |
| api-elc-invoice-lqpt | piaozone/elc-integration/api-elc-invoice-lqpt | 集成层-乐企票通适配服务 |
| api-elc-invoice-create | piaozone/elc-integration/api-elc-invoice-create | 集成层-全电平台开票适配器 |
| api-elc-invoice-collect | piaozone/elc-integration/api-elc-invoice-collect | 集成层-全电发票采集服务 |
| api-elc-invoice-gjfp | piaozone/elc-integration/api-elc-invoice-gjfp | 集成层-国家发票平台适配服务 |
| api-elc-invoice-engine | piaozone/elc-integration/api-elc-invoice-engine | 集成层-全电发票引擎服务 |
| base-gateway | piaozone/base/base-gateway | 基础层-网关服务 |
| base-auth | piaozone/base/base-auth | 基础层-认证服务 |
| bill-gateway | piaozone/base/bill-gateway | 基础层-发票云网关 |
| base-file-center | piaozone/base/base-file-center | 基础层-文件中心服务 |
| bill-organization | piaozone/base/bill-organization | 基础层-组织机构服务 |
| bill-bm-ocr-invoice | piaozone/input/bill-bm-ocr-invoice | 进项-百望 OCR 发票识别服务 |
| bill-wechat-mini-program | piaozone/input/bill-wechat-mini-program | 进项-微信小程序（移动端推送） |
| bill-portal | piaozone/base/bill-portal | 进项-门户管理后台 |
| base-iam | piaozone/base/base-iam | 基础层-认证授权服务（api-auth 替代） |
| api-pdf-utils | piaozone/common/api-pdf-utils | 公共-PDF 文件处理工具 |
| api-ofd-utils | piaozone/common/api-ofd-utils | 公共-OFD 文件处理工具 |
| base-file-center-server | piaozone/base/base-file-center-server | 基础层-文档中心（识别分流：网关拦截→上传/快照/识别/验签） |
| fpzs-pc | piaozone/frontend/fpzs-pc | 前端-发票助手 PC 端（React + dva，端口 9000） |
| portal-web | piaozone/frontend/portal-web | 前端-商家平台前端（Vue） |
| fpy-parent | piaozone-v2/fpy-parent | 重构版-父 POM（统一依赖管理） |
| fpy-sdk-base | piaozone-v2/sdk/fpy-sdk-base | 重构版-基础 SDK（实体、工具、配置） |
| fpy-base-query | piaozone-v2/base/fpy-base-query | 重构版-查询服务（响应式，规则引擎，虚拟线程） |
| fpy-isv | piaozone-v2/app/fpy-isv | 重构版-ISV 发票查验服务（独立部署） |

> 如需新增映射，按格式在表格中追加一行即可。