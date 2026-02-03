| **文档编号** | **适用产品版本** | **使用范围** | **更新内容** | **创建（修改）时间** | **责任人** |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **v25.0.01** | **标准版发票云** | **公开** | **创建** | **2025-11-19** | **兰茜凤** |


# 环境准备
1. **1AS版本**： 8.0版本、8.2版本、8.5版本
2. **补丁**<font style="color:#F5222D;">： 8.0和8.2版本需要更新【开票管理】/【收票管理】与【税务管理】的最新全局补丁PTM及开收票补丁 、8.5及以上版本更新对应模块最新补丁号。</font>
3. 对应版本最新税务补丁号可参考ESA补丁帖子进行相关说明查看（具体可联系税务模块老师进行确认）[EAS Cloud 税务管理知识合辑](https://vip.kingdee.com/knowledge/specialDetail/249195983434059776?category=249267138123885568&id=212586865499843328)
4. **配套所购EAS模块要求：**<font style="color:red;">费用报销模块、EAS收票管理、应付模块</font>

<details class="lake-collapse"><summary id="u52ffc3cd" style="text-align: justify"><span class="ne-text">补丁获取方式：</span></summary><p id="u5c6a274a" class="ne-p" style="text-align: justify"><span class="ne-text">WEB门户——金蝶专区——云客服——客户工单处理，进入KSM提单系统。</span></p><p id="uf846bd80" class="ne-p" style="text-align: justify"><img src="https://cdn.nlark.com/yuque/0/2021/png/2185333/1623822829314-e5a0de84-9ad8-4cba-9631-2d1f65bb69a2.png" width="593" id="r0l6s" class="ne-image"></p><p id="u8e1fb0a1" class="ne-p" style="text-align: justify"><img src="https://cdn.nlark.com/yuque/0/2021/png/2185333/1623822856657-f85d93b6-68ed-413f-9ce5-7617628af53a.png" width="374" id="P8v4B" class="ne-image"></p><p id="u16e00d9a" class="ne-p" style="text-align: justify"><span class="ne-text">进入系统后，在右上角【补丁下载】模块搜索对应补丁。</span></p><p id="u51820b27" class="ne-p" style="text-align: justify"><img src="https://cdn.nlark.com/yuque/0/2021/png/2185333/1623822921090-952c5f6c-df97-4305-9f75-2ceb40a66120.png" width="472" id="Pmu2j" class="ne-image"></p><p id="ucf8974e8" class="ne-p" style="text-align: justify"><img src="https://cdn.nlark.com/yuque/0/2021/png/2185333/1623822788620-99352d6e-0e6a-4b73-8228-4681886ed912.png" width="533" id="oQwbx" class="ne-image"></p><p id="uf097e3ca" class="ne-p" style="text-align: justify"><span class="ne-text">建议下载【开票管理】/【收票管理】和【税务管理】的最新版全局补丁。如对补丁功能有所疑问，请联系EAS同事沟通。</span></p><p id="u87517d9d" class="ne-p" style="text-align: justify"><strong><span class="ne-text" style="color: red">注意：本文档主要是关于税盘收票、发票认证的实施配置，如果想配置费用报销与发票云的集成收票，详见文档：</span></strong><a href="https://www.yuque.com/docs/share/2bde771e-c55e-40b5-b508-00f2194a6aa8?#" data-href="https://www.yuque.com/docs/share/2bde771e-c55e-40b5-b508-00f2194a6aa8?#" target="_blank" class="ne-link"><span class="ne-text">https://www.yuque.com/docs/share/2bde771e-c55e-40b5-b508-00f2194a6aa8?#</span></a><span class="ne-text"> 《EAS【财税一体综合收票服务】费用报销_实施文档》</span></p><p id="ud66bffb9" class="ne-p" style="text-align: justify"><img src="https://cdn.nlark.com/yuque/0/2020/png/1580060/1599119386504-426d1be2-fa3b-4e8a-baca-9f5df9556e4c.png" width="427" id="m8GHN" class="ne-image"></p><p id="uc0a17d82" class="ne-p" style="text-align: justify"><br></p><p id="u19d0570f" class="ne-p"><br></p></details>
# 一、发票云产品激活
**<font style="color:#DF2A3F;">是否必需：是</font>**

 [产品激活及参数获取](https://jdpiaozone.yuque.com/nbklz3/tadboa/sf09ttllvsbpkyae)

# 二、ERP配置
## 环境部署--同步权限项、分配权限等
**<font style="color:#DF2A3F;">是否必需：是</font>**

使用管理员登陆EAS客户端，同步权限项、分配税务管理权限、更新本地数据、同步日志项数据等操作。

1. **分配权限：**<font style="color:#117CEE;">企业建模—安全管理—权限管理—用户管理</font>

![](https://cdn.nlark.com/yuque/0/2020/png/1580060/1599119388223-5b072668-5112-4233-b6a8-4459b0e85d96.png)

2. **更新本地数据：**系统—更新本地数据

![](https://cdn.nlark.com/yuque/0/2020/png/1580060/1599119388517-3e479898-ed4e-4886-8f91-9697726b23c9.png)

3. **同步日志数据：**企业建模—安全管理—系统监控—上机日志

![](https://cdn.nlark.com/yuque/0/2020/png/1580060/1599119388674-639c0317-7deb-41d7-af4b-67c82e01b70f.png)

## 金税互联设置
**<font style="color:#DF2A3F;">是否必需：是</font>**

**<font style="color:#117CEE;">路径：税务管理模块—增值税发票管理—基础设置—金税互联设置</font>**

![](https://cdn.nlark.com/yuque/0/2020/png/1580060/1599119389021-6ae4c8a6-5c3a-4ecd-8323-6da2987535f3.png)

![](https://cdn.nlark.com/yuque/0/2020/png/1580060/1599119389178-b4e54eec-2dfc-4d87-8954-65a259f9fc95.png)

**操作说明**：

+ 组织维护：收票财务组织
+ 操作类型维护：收票
+ http地址：https://api.piaozone.com/bill-websocket/v3/invoicewebsocket/push?taxNo=<font style="color:#DF2A3F;">当前企业税号</font>&clientId=<font style="color:#DF2A3F;">企业对应的发票云ClientId的值</font>&request_path=
+ **发票云ID、发票云密钥、加密密钥：**从发票云授权邮件中获取（<font style="color:#DF2A3F;">请使用税号对应的企业授权，不要用租户授权！！</font>）

![](https://cdn.nlark.com/yuque/0/2020/png/1580060/1607994424018-0a514622-b795-4585-b787-a2fc0a6019f3.png)

![](https://cdn.nlark.com/yuque/0/2022/png/34387723/1669971203066-33be9f27-41b0-4f80-84bf-59f9fa6c9a3a.png)

## 3.3 通讯基本设置
**<font style="color:#DF2A3F;">是否必需：是</font>**

用<font style="color:red;">administrator</font><font style="color:red;">登录</font>客户端

<font style="color:#117CEE;">路径：税务管理—增值税发票管理—基础设置—金税互联日志</font>

打开金税互联日志记录，可看到通讯基本设置按钮，如下图

点击通讯基本设置，出现地址设置界面，如下图

![](https://cdn.nlark.com/yuque/0/2025/png/39256605/1764225514457-27bf6c7d-d242-491b-b81e-560510e3cca0.png)

发票云官网地址：[https://api.piaozone.com](https://api.piaozone.com)

发票云测试环境地址：[https://api-dev.piaozone.com/test](https://api-dev.piaozone.com/test)

长连接地址：[https://wss.piaozone.com/bill-websocket/invoicewebsocket/push](https://wss.piaozone.com/bill-websocket/invoicewebsocket/push)

**<font style="color:red;">修改说明：</font>**

如果是正式生产环境，这里就勾选启用正式环境；在测试环境内使用正式帐套进行测试也需要勾选；

如果是测试环境，取消勾选启用正式环境



# 三、收票操作指引
[发票下载操作指引](https://vip.kingdee.com/link/s/ZT8bN)

[【收票新增】操作手册](https://vip.kingdee.com/link/s/ZT86v)

[【抵扣勾选统计】操作手册](https://vip.kingdee.com/link/s/ZT80L)







