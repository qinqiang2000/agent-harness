| **文档编号** | **适用产品版本** | **使用范围** | **更新内容** | **创建（修改）时间** | **责任人** |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **v25.0.01** | **标准版发票云** | **公开** | **创建** | **2025-11-19** | **兰茜凤** |


# 环境准备
1. EAS版本：8.0版本、8.2版本、8.5版及以上**<font style="color:#E8323C;">（建议购买86版本）</font>**
2. 补丁： 8.0和8.2和8.5版本需要【费用报销】的最新版全局补丁。
3. 86版本需升级至861版本后再打全局补丁。

<details class="lake-collapse"><summary id="ub76338bf"><span class="ne-text">补丁获取方式：</span></summary><p id="u78b85861" class="ne-p"><span class="ne-text">WEB门户——金蝶专区——云客服——客户工单处理，进入KSM提单系统。</span></p><p id="u0b22d339" class="ne-p" style="text-align: justify; margin-left: 2em"><img src="https://cdn.nlark.com/yuque/0/2021/png/2185333/1623822829314-e5a0de84-9ad8-4cba-9631-2d1f65bb69a2.png" width="593" id="pJDe1" class="ne-image"></p><p id="u9f677849" class="ne-p" style="text-align: justify; margin-left: 2em"><img src="https://cdn.nlark.com/yuque/0/2021/png/2185333/1623822856657-f85d93b6-68ed-413f-9ce5-7617628af53a.png" width="374" id="Hgc53" class="ne-image"></p><p id="u02db171e" class="ne-p" style="text-align: justify; margin-left: 2em"><span class="ne-text">进入系统后，在右上角【补丁下载】模块搜索对应补丁。</span></p><p id="u1b9e6cb2" class="ne-p" style="text-align: justify; margin-left: 2em"><img src="https://cdn.nlark.com/yuque/0/2021/png/2185333/1623822921090-952c5f6c-df97-4305-9f75-2ceb40a66120.png" width="472" id="jFYDb" class="ne-image"><img src="https://cdn.nlark.com/yuque/0/2021/png/2185333/1623822662870-5f1f71bb-44ac-48e7-9cda-103dce00b9a1.png" width="448" id="pDjoK" class="ne-image"></p><p id="ub66a8825" class="ne-p" style="text-align: justify; margin-left: 2em"><span class="ne-text">建议下载【开票管理】/【收票管理】和【税务管理】的最新版全局补丁。如对补丁功能有所疑问，请联系EAS同事沟通。</span></p><p id="ue6dfaf6e" class="ne-p"><br></p></details>
# **一、发票云产品激活**
**<font style="color:#DF2A3F;">是否必需：是</font>**

**<font style="color:red;"> </font>**[产品激活及参数获取](https://jdpiaozone.yuque.com/nbklz3/tadboa/sf09ttllvsbpkyae)

# 二、ERP配置
## 报销企业税号资料维护
**<font style="color:#DF2A3F;">是否必需：是</font>**

**<font style="color:#117CEE;">路径：GUI -->企业建模-->组织架构--->组织单元-->组织单元</font>****<font style="color:#1D1D1D;">（</font>****<font style="color:red;">费用报销单 申请人公司</font>****<font style="color:#1D1D1D;">）</font>**

<font style="color:#1D1D1D;">填写如下图，填写税号、clientid（发票云授权码）、clientsecret （发票云授权密钥）</font>

<font style="color:#F5222D;">复制信息时请检查对应信息是否有空格，及时将空格删除</font>

![](https://cdn.nlark.com/yuque/0/2020/png/1579635/1591841133016-e098d69a-f406-4690-9b5b-1556650661f3.png)

## 发票分类设置
<font style="color:#117CEE;">路径：web端---财务会计---费用管理--基础设置---发票分类设置</font>

![](https://cdn.nlark.com/yuque/0/2021/png/21649460/1627873669890-c5b748fe-7b05-44af-b4c7-8b97ba9c0a61.png)

进行发票分类设置，建立费用类型和税收编码的映射

![](https://cdn.nlark.com/yuque/0/2021/png/21649460/1627873692385-4202b42e-7550-4078-9aef-c26b07203c24.png)

## 费用报销单的编码规则
费用报销单的编码规则定义里面（<font style="color:red;">必须勾选新增显示</font>) 如下图：

![](https://cdn.nlark.com/yuque/0/2020/png/1579635/1591841133595-e8f10a4c-2f4b-42c6-95f2-368f6092be18.png)

 

**温馨提示：**

请新增一张报销单在新增页面自行检查<font style="color:red;">（用户登录</font><font style="color:red;">eas</font><font style="color:red;">后不进行切换组织，新增费用报销单，新增页面打开后，表头的申请人公司，分录的费用支付公司</font><font style="color:red;"> </font><font style="color:red;">费用支付部门有没有值，这个三个字段必须有值，如下图）</font>，没有值请给该职员配置默认值或者提单后支持部同事会进行手把手给予处理。

![](https://cdn.nlark.com/yuque/0/2020/png/1579635/1591841133729-0e351012-693b-4266-acaa-7c8e61937961.png)

## 选择发票参数设置
    1. <font style="color:#117CEE;">GUI路径：系统平台——系统工具——系统配置——参数设置（选择费用管理模块）</font>

<font style="color:red;">有关参数 CP039是否显示按钮字段；  CP03901 CP03902 CP03903 CP03904 判断发票是否合法 合规具体看参数说明</font>

![](https://cdn.nlark.com/yuque/0/2020/png/1579635/1591841133864-fc645e9b-b100-40e4-b3ce-a7242fb23532.png)

    2. <font style="color:#000000;">发票云商户运营平台的合规性设置中也可进行相关设置</font><font style="color:red;">，优先以商户运营平台设置生效</font>
    - [http://tax.piaozone.com/](http://tax.piaozone.com/)（正式环境）
    - [http://tax-test.piaozone.com/](http://tax-test.piaozone.com/)（测试环境）

<font style="color:#117CEE;">路径：【进项发票管理】——【发票合规性设置】</font>

![](https://cdn.nlark.com/yuque/0/2021/png/21649460/1629344309885-95301ff8-94c8-4c9d-b158-5ddfae03aab3.png)

# 三、费用报销使用指引
## 新增费用报销单 
**<font style="color:#117CEE;">路径：</font>**<font style="color:#117CEE;">Web端 财务会计—报销工作台—费用报销单新增（或对公报销单或差旅报销单）</font>

![](https://cdn.nlark.com/yuque/0/2021/png/21649460/1627873768619-662663a7-a11d-4132-a9cc-366e9375e730.png)

## web端导入发票
点击选择发票，提供多种方式进行导入发票：电脑端选取、扫描枪扫描、微信小程序导入

 

本文以微信小程序为例，微信扫描弹出的二维码（进入发票云的微信公众号），扫码，确认添加，确认（推送发票到PC端）

![](https://cdn.nlark.com/yuque/0/2021/png/21649460/1627873800404-2231f701-3f44-48e1-b61a-c7380fb5f2e5.png)

可通过扫码（扫发票上的二维码）、微信卡包导入、拍照、手工添加输入发票信息等多种方式采集发票信息，然后点击去报销、推送到PC端

 

![](https://cdn.nlark.com/yuque/0/2020/png/1579635/1591841134356-21bcb05a-0cc2-413d-b82d-254379f08c80.png)![](https://cdn.nlark.com/yuque/0/2020/png/1579635/1591841134537-ccf4965c-4e0c-43ed-bfd6-6ed96e2510da.png)

<font style="color:#1D1D1D;"> </font>

<font style="color:#1D1D1D;">此时，PC端会收到手机移动端推过来的发票，点击导入发票，可看到</font>发票信息

![](https://cdn.nlark.com/yuque/0/2021/png/21649460/1627874221528-1b542db4-8343-4184-9e79-44649ed2e916.png)

发票信息如下：

![](https://cdn.nlark.com/yuque/0/2021/png/21649460/1627874282615-fc947aa5-2298-407a-9439-a665252be0a1.png)

**温馨提示：**

导入发票后，如果第2.4步发票分类设置中，没有建立发票种类与费用类型的映射，此时费用类型为空；建立映射，费用类型才会有值。

![](https://cdn.nlark.com/yuque/0/2021/png/21649460/1627874361334-62d58647-a78c-486f-8a74-17d901cb8123.png)

**关于高拍仪收票**

目前，发票云收票支持使用高拍仪进行收票，入口与【扫描仪收票】为同一个入口。但是高拍仪收票，需满足以下几个前提：

1. 高拍仪需支持TWAIN协议，此外<font style="color:rgb(0, 0, 0);">还需要能接入sdk，被第三方软件调用</font>
2. 需在电脑中安装：高拍仪驱动程序、 twain 程序、发票云扫描程序。（如不清楚程序的获取方式，请联系与您对接的高拍仪厂商获取） 
3. 推荐对接型号：<font style="color:rgb(0, 0, 0);">德意拍 JW901 紫光 Unispro G880、Unispro G760</font>
4. 扫描时，需关闭高拍仪驱动程序

## 查看发票
查看发票按钮---显示整单的所有发票，及通过发票助手上传的附件内容

![](https://cdn.nlark.com/yuque/0/2021/png/21649460/1627874497825-d8e460b9-9692-4687-b548-4c86350e3ae8.png)

 

分录中查看发票：点击 “发票N张”如下图，显示此行分录对应的发票

![](https://cdn.nlark.com/yuque/0/2021/png/21649460/1627874588490-4411041e-edda-4d78-9782-d601008eeec7.png)

# 四、 费用报销与发票云功能说明
## 状态说明
1. 新增页面：选择发票、查看发票、分录查看发票

提交报销类单据之后，报销类单据状态为“提交”，对应的发票状态为“报中”

2. 查看页面：查看发票、分录查看发票
3. 审批页面：查看发票（<font style="color:red;">此功能待发补丁完善</font>）、分录查看发票
4. 核定页面：查看发票、分录查看发票

报销类单据状态为“审批通过”，对应的发票状态为“已用”

与EAS税务集成，EAS税务会把报销类单据的票拉到税务模块。

5. 报销类单据状态在工作流或者列表页面单据被废弃时，对应的发票状态为“未用”
6. 报销类单据状态在工作流走分支“审批未通过”，对应的发票状态为“未用”

<font style="color:red;">所有页面的“选择发票”、“查看发票”按钮；分录查看发票分布如下图：</font>

![](https://cdn.nlark.com/yuque/0/2020/png/1579635/1591841135727-22d2fab6-2531-45a4-a8e5-8228345ba244.png)

## 报销类单据功能说明
    1. 费用报销单：选择发票-->导入发票：会根据发票类型或者发票税收分类编码进行归类，然后生成对应费用报销的分录，导入的发票展示在费用报销单的发票信息分录

![](https://cdn.nlark.com/yuque/0/2020/png/1579635/1591841136154-96e57179-5c9d-4f55-b511-148da09ee069.png)

    2. 差旅费用报销单：选择发票-->导入发票：会根据长途费、市内交通费、住宿费、其他费用进行归类，<font style="color:red;">只生成一条差旅报销单的分录</font>，导入的发票展示在费用报销单的发票信息分录

![](https://cdn.nlark.com/yuque/0/2020/png/1579635/1591841136300-75f218b0-847a-45f2-a8c7-9006d4549700.png)

 

    3. 对公费用报销单：选择发票-->导入发票：会根据发票类型或者发票税收分类编码进行归类，然后生成对应费用报销的分录，导入的发票展示在对公费用报销单的发票信息分录，导入的发票会生成对应的收款信息分录。

![](https://cdn.nlark.com/yuque/0/2020/png/1579635/1591841136514-f2460282-035d-4237-97f4-07f98d496044.png)

![](https://cdn.nlark.com/yuque/0/2020/png/1579635/1591841136693-99affe02-dd0b-4573-9a5c-87739e91cb02.png)

![](https://cdn.nlark.com/yuque/0/2020/png/1579635/1591841137164-d145f58a-ef83-4709-996c-22b9f07336bc.png)

 

    4. 物品采购报销单：选择发票-->导入发票：会根据发票类型或者发票税收分类编码进行归类，然后生成对应费用报销的分录，导入的发票展示在物品采购报销单的发票信息分录，导入的发票会生成对应的收款信息分录

![](https://cdn.nlark.com/yuque/0/2020/png/1579635/1591841137306-cabfe9ee-3b8e-4bab-865f-749c955977d0.png)

 

五、

# 五、测试环境
<font style="color:#1D1D1D;">如需使用测试环境，请将此配置文件放置到该目录下替换</font><font style="color:red;">（正式环境请忽略）</font>

<font style="color:#1D1D1D;">cpbc_invoice_config.xml （详细见文档底部附件）</font>

<font style="color:#1D1D1D;">路径：</font><font style="color:#1D1D1D;">*\eas\server\properties\cpbc_invoice_config.xml</font>

<font style="color:red;">替换之后</font>

<font style="color:red;">（1）杀掉 java 和javaw进程   </font>

<font style="color:red;">（2）重启服务器 </font>

<font style="color:red;">（3）如果使用测试环境，每次更新补丁都需要替换一次，打上补丁后默认连接发票云正式环境</font>

