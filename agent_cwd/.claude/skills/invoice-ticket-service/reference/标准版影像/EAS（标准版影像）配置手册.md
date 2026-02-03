| **文档编号** | **适用产品版本** | **使用范围** | **更新内容** | **创建（修改）时间** | **责任人** |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **v25.0.01** | **标准版发票云** | **公开** | **创建** | **2025-11-19** | **兰茜凤** |


# 一、产品订单激活
**<font style="color:#DF2A3F;">是否必需：是</font>**

[产品激活及参数获取](https://jdpiaozone.yuque.com/nbklz3/tadboa/sf09ttllvsbpkyae)

# 二、环境准备
EAS版本：8.5及以上版本

# 三、ERP配置
**<font style="color:#DF2A3F;"> EAS影像功能清单及配置流程</font>**

![](https://cdn.nlark.com/yuque/0/2021/png/21649460/1621587425486-fc93c4ae-723f-4450-95ba-2b0eea56ad8f.png)

![](https://cdn.nlark.com/yuque/0/2021/png/21649460/1621587425845-9070e0c6-c137-4cfc-9ef2-38a0107dca5c.png)

## 增加影像审批节点
**<font style="color:#DF2A3F;">是否必需：是</font>**

相关工作流审批设置，可参考以下资料

[金蝶EAS Cloud【财务共享平台】知识合辑2020](https://vip.kingdee.com/article/167307538659046144)

[金蝶EAS Cloud用户手册丛书---参考指南](https://vip.kingdee.com/eascloud/help/8.6hybrid/FSSC.web/index.html)

![](https://cdn.nlark.com/yuque/0/2021/png/21649460/1622080274276-24d516e1-0734-44b5-96e1-b92b92d7ee24.png)

![](https://cdn.nlark.com/yuque/0/2021/png/21649460/1630660594685-64eb4774-d879-4ac1-a233-e0108cd15b81.png)

![](https://cdn.nlark.com/yuque/0/2021/png/21649460/1622080904668-8c91803a-530f-4eee-99d0-16ed00d5daf8.png)

## 发票云授权配置
**<font style="color:#DF2A3F;">是否必需：是</font>**

**<font style="color:#117CEE;">路径：</font>**<font style="color:#117CEE;">GUI -->企业建模-->组织架构--->组织单元-->组织单元</font>

<font style="color:#1D1D1D;">确认企业税号、企业名称、发票云授权id、发票云授权秘钥正确填写</font>

<font style="color:#FF0000;">注意：确认参数信息填写正确，检查是否有ID、secret是否有空格存在</font>

![](https://cdn.nlark.com/yuque/0/2021/jpeg/21649460/1621587426372-a43be1fc-1617-4955-942f-10f742cf7283.jpeg)

## 多影像系统配置
**<font style="color:#DF2A3F;">是否必需：是</font>**

<font style="color:#117CEE;">操作路径：〖财务共享〗->〖共享任务管理〗->〖基础设置〗->〖多影像系统配置〗</font>

![](https://cdn.nlark.com/yuque/0/2021/png/21649460/1621587426790-46c847a4-cf5c-4157-8641-4925a9212a8f.png)

【配置信息】

1. 发票云授权码：client id   发票云授权密钥：client secret
2. 影像IP/域名
    - 公有云演示环境：http://kdimage-demo.piaozone.com/
    - 公有云正式环境：http://api.piaozone.com/
    - 私有部署：http://ip:端口/api/（服务器部署的port及端口信息）
3. 端口填写
    - 公有云演示环境：<font style="color:rgb(0, 0, 0);">http端口用80，htpps端口用443</font>
    - 公有云正式环境：80
    - 私有部署：8080（没有修改过部署脚本的情况下）

<font style="color:rgb(0, 0, 0);">PS：下面的【高级配置】点击【保存】后接口后缀会自动生成，不需要手动去敲打（避免出错），只需要修改对应的前缀IP和端口即可。</font>

<font style="color:#F5222D;">自动生成后，请检查下对应的格式，可能会出现格式错乱，多余的冒号或斜杠</font>

**<font style="color:rgb(0, 0, 0);">公有云部署</font>****<font style="color:rgb(0, 0, 0);">👇</font>**

![](https://cdn.nlark.com/yuque/0/2021/png/21649460/1629879706811-836d019b-dbd8-42d2-b885-9aa472d9f284.png)



![](https://cdn.nlark.com/yuque/0/2021/png/21649460/1621587427430-3788f8a2-8139-4790-a3e7-09ea4b617c60.png)

**私有云部署****👇**

![](https://cdn.nlark.com/yuque/0/2021/png/21649460/1637743351453-94192c5b-0d48-4d35-b074-4f060f72ae61.png)

## 扫描点设置
**<font style="color:#DF2A3F;">是否必需：是</font>**

<font style="color:#117CEE;">路径：〖财务共享〗->〖共享任务管理〗->〖基础设置〗->〖扫描点维护〗</font>

![](https://cdn.nlark.com/yuque/0/2021/png/21649460/1621587427828-491d339f-6109-4fa5-8660-747a14c5085b.png)

![](https://cdn.nlark.com/yuque/0/2021/png/21649460/1621587428539-83c7c119-d73d-40cb-a379-52106579ab65.png)

## 套打模板设置
**<font style="color:#DF2A3F;">是否必需：是</font>**

单据提交后需要提交发票等票据信息进行影像扫描录入系统，为了方便识别票据所属单据，一般都会为每个单据打印个扫描封面，封面上打印出单据对应的二维码，通过扫描二维码识别单据生成对应的影像编号，快速将票据和单据关联上。点击【打印】/【打印封面】选择对应格式。

![](https://cdn.nlark.com/yuque/0/2021/png/21649460/1621587428909-5fce885b-c259-48cb-882b-6f6da652737f.png)

<font style="color:#F5222D;">PS: 目前发票云影像仅支持二维码识别, 若套打模板设置为条形码，需修改为二维码显示方式</font>

设置方式：登录<font style="color:#117CEE;">GUI 【系统平台-业务工具-套打】</font>设置相关单据套打模板

![](https://cdn.nlark.com/yuque/0/2021/png/21649460/1631239440644-2e2927d9-17b9-49f9-94b7-d55995532868.png)

![](https://cdn.nlark.com/yuque/0/2021/png/21649460/1631239381497-b9d49272-2ab3-47b5-883c-63e22a0dce6f.png)

## 影像上传
**<font style="color:#DF2A3F;">是否必需：是</font>**

<font style="color:#117CEE;">【操作路径】：〖财务共享〗->〖共享任务管理〗->〖共享任务处理〗->〖影像上传〗</font>

点击影像上传，选择对应扫描点，跳转至金蝶发票云影像系统，上传影像。

![](https://cdn.nlark.com/yuque/0/2021/png/21649460/1631240056161-34a87ab9-5feb-4195-985a-79eef4aa2fef.png)

跳转到影像系统后，可以通过【影像扫描】上传影像

![](https://cdn.nlark.com/yuque/0/2021/png/21649460/1637217738358-e57fb4f9-3a33-4628-baa1-50d79acd349f.png)

<font style="color:#DF2A3F;">注意：</font>

从EAS账号跳转过来后,没有【影像扫描】菜单，此为账号权限导致

<font style="color:#E8323C;">（目前EAS中维护的扫描点与账号没有同步到影像系统,与影像系统是两套独立的数据,所以扫描点和对应人员的账号还需要单独在影像系统中添加）</font>

<font style="color:#E8323C;"></font>

用申请影像的管理员账号单独登录影像系统（登录网址，账号信息均在影像授权邮件中查看）

+ 首次使用，在【权限管理】--【角色管理】中新增对应权限的角色名称
+ 【权限管理】--【用户管理】中，添加对应账号，账号与当前跳转EAS账号<font style="color:#E8323C;">手机号码一致</font>；添加后对该账号进行组织授权、角色授权.
+ 首次使用，还需在影像系统添加扫描点，入口【扫描点管理】--【扫描点列表】新增；新增扫描点后，绑定对应扫描人员（若没有绑定扫描点，提交影像无权限）

Q：绑定扫描人员时，先确认组织是否一致，该账号是否有分配对应扫描权限，否则扫描点无法查询到该账号

# 四、影像系统配置
## 对接业务系统配置
**<font style="color:#DF2A3F;">是否必需：是</font>**

按截图所示逐一检查，参数不对会校验失败。

+ 业务系统：EAS
+ 前缀地址：http:// IP:端口/ormrpc/services/（填写时请检查是否有空格）
+ EAS数据中心编码：数据中心ID
+ EASSI名称：默认值,请填eas
+ EAS用户名：EAS登录账号
+ EAS密码：EAS登录密码

![](https://cdn.nlark.com/yuque/0/2024/png/21778712/1724668696463-b91b8e7c-5943-4d0d-91c1-30c299fee12f.png)

## 收票配置（发票同步到影像）
**<font style="color:#DF2A3F;">是否必需：是</font>**

同步和匹配模式必须配置

<details class="lake-collapse"><summary id="u846da136"><strong><span class="ne-text" style="color: rgba(245,31,53,1)">影像模式选择</span></strong></summary><p id="u66b78318" class="ne-p"><span class="ne-text" style="font-size: 16px">发票云影像系统有三种可选模式，需要与客户确认其使用场景后选择对应的模式。</span></p><p id="u5b5d2d02" class="ne-p"><img src="https://cdn.nlark.com/yuque/0/2021/png/21649460/1621587422753-090c2d72-b957-4d88-a6b9-b4fcb10601b2.png?x-oss-process=image%2Fresize%2Cw_548%2Climit_0" width="548" id="XJP2J" class="ne-image"></p><h5 id="kteSt"><span class="ne-text">（1）基础模式：</span></h5><p id="ub1b1dd49" class="ne-p"><strong><span class="ne-text">【适用场景】</span></strong><span class="ne-text" style="font-size: 16px">客户有指定的扫描岗，没有用影像收票，需要在影像系统采集影像，仅做影像数据存储。</span></p><p id="u97ddd8fa" class="ne-p"><img src="https://cdn.nlark.com/yuque/0/2021/png/21649460/1621587423281-fa81895a-70b4-49b7-800d-e19ca1ffc150.png" width="1091" id="PvPoF" class="ne-image"><img src="https://cdn.nlark.com/yuque/0/2021/png/21649460/1621587423281-fa81895a-70b4-49b7-800d-e19ca1ffc150.png" width="1091" id="T2t73" class="ne-image"></p><h5 id="FMFJP"><span class="ne-text">（2）影像匹配：</span></h5><p id="u1f5ccc99" class="ne-p"><strong><span class="ne-text">【适用场景】</span></strong><span class="ne-text" style="font-size: 16px">有指定的扫描岗，有用收票或者业务系统集成收票功能，可以在提单的时候获取发票结构化数据，需要在影像系统采集影像，需要做系统初审（二次匹配）</span></p><p id="uc197e905" class="ne-p"><img src="https://cdn.nlark.com/yuque/0/2021/png/21649460/1621587423614-2f5e14c8-be41-4067-8143-f908db9093ac.png" width="1091" id="sSOdT" class="ne-image"></p><p id="u06105ece" class="ne-p"><strong><span class="ne-text" style="font-size: 16px">说明：匹配模式下，私有化影像需放开影像系统访问 api.piaozone.com 443（生产）api-dev.piaozone.com 443（演示）的白名单网络权限</span></strong></p><p id="u978952f3" class="ne-p"><strong><span class="ne-text" style="font-size: 16px"></span></strong></p><h5 id="r2Gtk"><span class="ne-text">（3）影像同步提单人：</span></h5><p id="u3cfaee9d" class="ne-p"><strong><span class="ne-text">【适用场景】</span></strong><span class="ne-text" style="font-size: 16px">没有指定的扫描岗，人人可上传影像，不需要在影像系统采集影像</span></p><p id="ue9d99db7" class="ne-p"><img src="https://cdn.nlark.com/yuque/0/2021/png/21649460/1621587424183-640e8d64-f171-44d4-8758-f9d6ba81f60e.png" width="1091" id="GRIAv" class="ne-image"></p></details>
请确认使用的是AWS收票助手，界面如下

![](https://cdn.nlark.com/yuque/0/2023/png/21649460/1683354812454-d385f661-014e-44b9-9b09-7f23aeb122c1.png)

**提供信息给总部实施，配置AWS收票推送表**

+ <font style="color:#E8323C;">企业名称</font>
+ <font style="color:#E8323C;">企业税号</font>
+ <font style="color:#E8323C;">对应的clientid </font>
+ <font style="color:#E8323C;">推送地址（影像登录地址，若为私有化部署需提供影像映射的外网地址，否则网络不通）</font>

## 企业授权配置
**<font style="color:#DF2A3F;">是否必需：是</font>**

**功能说明：**

添加使用影像系统租户下的组织授权，用于影像系统登录、外部获取请求token认证，租户初始化，从收票获取发票数据，数据的新增和删除由影像系统运维人员操作，影像系统用户只有查看的权限。



点击新增，在弹出的窗口中录入：

企业税号、名称、授权客户ID、secret、encrypt_key；

注意信息要和收票的授权保持一致，并且client ID 信息部门一定是存在，否则保存不成功；

录入完成后点击确定，完成企业授权新增

![](https://cdn.nlark.com/yuque/0/2023/png/29641274/1684465609909-13873fc2-ce56-4051-a9e0-bfe663aa757a.png)

# 五、影像系统操作手册
影像系统各功能节点详细操作说明，请以下产品手册：

[AWS_影像系统操作手册](https://jdpiaozone.yuque.com/nbklz3/tadboa/pv44zoeo7ky2m5cc?singleDoc#)<font style="color:#E8323C;"> </font>



