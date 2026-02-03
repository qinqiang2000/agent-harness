

**文档说明：**

       该文档主要记录收票配置问题、收票操作报错。每一个FAQ分问题、方案两部分内容。若为咨询类问题，可转至一问一答查看[https://jdpiaozone.yuque.com/nbklz3/tadboa/pgss9eco9x0hq2ph?singleDoc#GaKF](https://jdpiaozone.yuque.com/nbklz3/tadboa/pgss9eco9x0hq2ph?singleDoc#GaKF) 《收票》



#### <font style="color:rgb(0, 0, 0);">企业票夹</font>
【问题】：企业票夹没有显示税局下载的发票

<font style="color:rgb(38, 38, 38);">【方案】：</font>

检查发票的核算组织，然后sql查询发票组织是否一致。

<font style="color:rgb(0, 0, 0);">select * from t_rim_inv_collect_org where fid in (select fid from t_rim_invoice where finvoice_no='发票号码')</font>

<font style="color:rgb(0, 0, 0);"></font>

<font style="color:rgb(0, 0, 0);"></font>

#### <font style="color:rgb(51,51,51);">基础授权信息有误</font>
<font style="color:rgb(38, 38, 38);">【问题】：</font><font style="color:rgb(51,51,51);">单据上打开发票助手页面一直显示：基础授权信息有误，请联系管理员，</font>

<font style="color:rgb(38, 38, 38);">【方案】：</font>

1. <font style="color:rgb(51,51,51);">检查</font>**<font style="color:rgb(51,51,51);">“</font>**<font style="color:rgb(51,51,51);">发票云授权配置</font>**<font style="color:rgb(51,51,51);">”</font>**<font style="color:rgb(51,51,51);">界面：</font>

<font style="color:rgb(51,51,51);">      （1）url指向生产环境时，应使用生产环境的发票云授权参数（clientID，client_sercret等）</font>

<font style="color:rgb(51,51,51);">      （2）url指向测试环境时，应使用测试环境的发票云授权参数（clientID，client_sercret等）</font>

2. <font style="color:rgb(51,51,51);">检查开发平台，费用全局配置下的配置项invoicecloud.not_prod</font>

<font style="color:rgb(51,51,51);">       true时连接测试环境 ，false连接正式环境，</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764146435533-9eb34696-9233-4c9b-a03b-753730ea2e4c.png)





#### 星空旗舰版应付单列表上是否可以扩展一个查看发票的按钮？
答：不支持扩展。经与开发确认，目前 星空旗舰版不支持在应付单列表上扩展查看发票按钮（列表会支持多选，查看发票是单选操作）。

点开某张应付单上可以查看发票。







#### 星空旗舰版，进项全票池里的凭证号都为空？点击更新凭证号提示：所选发票中有未关联单据或凭证数据，请检查后重试
答：财务应付单列表有个同步凭证至发票云的按钮，需要扩展出来，修改可见性，手工触发同步凭证数据到发票云。因为星空旗舰是ISV，他们生成凭证后调不了我们的接口把凭证号同步给我们

开发平台带有fpy标识的财务应付单扩展项，<font style="color:#000000;">a089_fpy_ap_finapbill_ext</font>

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225039503-ab433491-f47d-4677-abf4-3f8d7b49e99a.png)





#### 星空旗舰版应付单挂有凭证，但是进项全票池上的凭证一列都为空？
答：

星空旗舰版目前需要手工同步凭证后才能在进项全票池可见。扩展成功后，需要在财务应付单列表上批量操作同步凭证到发票云。

需进开发平台，找到带有fpy标识的相关财务应付单扩展项，将“同步凭证至发票云”或者“同步删除发票云凭证”（看具体 需要再放开显示），修改其可见性，同时表单及列表插件需要添加对相关插件的引用：

标识：fpy_savevoucher

按钮名称：同步凭证至发票云

标识：fpy_deletevoucher

按钮名称：同步删除发票云凭证

表单插件名：<font style="color:#000000;">kd.fpy.rim.formplugin.fpzs.FpyCustomPlugin</font>

列表插件名：<font style="color:#000000;">kd.fpy.rim.formplugin.fpzs.FpyCustomListPlugin</font>

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225041216-74f4df4e-7053-4ebe-a617-83fe7cb8ee5f.png)

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225041541-c0997110-2241-47f7-9f80-3cc6fc227a18.png)

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225041892-159ec781-7b11-444b-8345-cfc7df9f5a58.png)

如有提示权限问题，可修改收票管理微服务的配置项，打开第三方应用授权项，同时关闭第三方应用invoiceupload上的启用代理用户控制 。

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225042222-9bec5ddf-a160-499e-8c55-8f7e17129f41.png)

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225042546-87816e07-7a5c-4998-92f6-0abfc439a510.png)

