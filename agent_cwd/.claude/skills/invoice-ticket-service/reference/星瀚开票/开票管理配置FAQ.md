

文档说明：

       该文档主要记录开票配置问题、开票操作报错。若为咨询类问题，可转至一问一答查看[https://jdpiaozone.yuque.com/nbklz3/tadboa/iallbtawkzq8eegl?singleDoc#8zfK](https://jdpiaozone.yuque.com/nbklz3/tadboa/iallbtawkzq8eegl?singleDoc#8zfK) 《开票》

#### 


#### <font style="color:rgb(38, 38, 38);">未经授权的访问</font>
【问题】：<font style="color:rgb(38, 38, 38);">移动云初始化参数正确还是报错：未经授权的访问</font>

<font style="color:rgb(38, 38, 38);">【方案】：</font>

<font style="color:rgb(38, 38, 38);">           路径：开发平台》发票云》基础资料》缓存清理</font>

<font style="color:rgb(38, 38, 38);">           操作：预览，输入IMAC_APP_TOKEN，点击清理。然后重新点击“移动云初始化”</font>

<font style="color:rgb(38, 38, 38);"></font>

<font style="color:rgb(38, 38, 38);"></font>

#### <font style="color:rgb(38, 38, 38);">内部错误。请稍后再试</font>
<font style="color:rgb(38, 38, 38);">【问题】：数电红冲开票报错“内部错误。请稍后再试”</font>

<font style="color:rgb(38, 38, 38);">【方案】：检查传入的是否为税控发票，是否为红字信息表编号。数电发票不能红冲红字信息表编号，需要申请红字确认单。</font>





#### <font style="color:rgb(51, 51, 51);">没有得到数据中心数据</font>
<font style="color:rgb(38, 38, 38);">【问题】：</font><font style="color:rgb(51, 51, 51);">移动云初始化报错“fapiaoyun没有得到数据中心数据!"</font>

<font style="color:rgb(38, 38, 38);">【方案】：</font><font style="color:rgb(0, 0, 0);">移动云数据中心=发票云公有云数据中心</font>

**正式环境：**

<font style="color:rgb(0, 0, 0);">url：</font>[https://cosmic.piaozone.com/fapiaoyun](https://cosmic.piaozone.com/fapiaoyun)

<font style="color:rgb(0, 0, 0);">数据中心：920172297321448448</font>

**<font style="color:rgb(0, 0, 0);">测试环境：</font>**

<font style="background-color:rgb(255,255,255);">url：https://cosmic-demo.piaozone.com/demo</font>

<font style="background-color:rgb(255,255,255);">数据中心：1640533801123708928</font>![](https://cdn.nlark.com/yuque/0/2024/png/39256605/1720511809322-5f4312a1-687e-43f4-9de9-b960fe0ccb0a.png?x-oss-process=image%2Fformat%2Cwebp)





#### <font style="color:rgb(0, 0, 0);">获取发票云平台app_token异常</font>
<font style="color:rgb(38, 38, 38);">【问题】：</font><font style="color:rgb(0, 0, 0);">移动云初始化报错“初始化移动云失败，移动云无法调用发票云：获取发票云平台app_token异常”</font>

<font style="color:rgb(38, 38, 38);">【方案】：</font><font style="color:rgb(0, 0, 0);">移动云初始化需要填的数据：</font>

<font style="color:rgb(0, 0, 0);">              1、移动云的地址（公有云）和移动云数据中心id</font>

<font style="color:rgb(0, 0, 0);">              2、第三方应用 密钥和手机号</font>

**<font style="color:rgb(0, 0, 0);background-color:#FBDE28;">移动云初始化逻辑：</font>**

<font style="color:rgb(0, 0, 0);">点初始化会访问移动云的地址获取token等-->将苍穹地址头给移动云 -->移动云访问苍穹获取token -->初始化</font>

<font style="color:rgb(0, 0, 0);background-color:#FBDFEF;">发票云访问苍穹（出口ip）：52.82.125.155</font>

<font style="color:rgb(0, 0, 0);background-color:#FBDFEF;">移动云访问私有云星瀚发票云（出口ip）：52.82.125.155</font>

<font style="color:rgb(0, 0, 0);background-color:#FBDFEF;">发票云访问苍穹（出口ip）：52.82.125.155</font>

<font style="color:rgb(0, 0, 0);background-color:#FBDFEF;">苍穹访问发票云（入口ip）：52.83.114.130/82.156.198.152/52.83.103.197</font>

<font style="color:rgb(0, 0, 0);"></font>

**<font style="color:rgb(0, 0, 0);">入口域名：</font>**<font style="color:rgb(0, 0, 0);"> </font>

<font style="color:rgb(0, 0, 0);">api. piaozone.com 443</font>

<font style="color:rgb(0, 0, 0);">api.kingdee.com 443 （苍穹许可）</font>

<font style="color:rgb(0, 0, 0);">cosmic-pro.piaozone.com 443</font>

<font style="color:rgb(0, 0, 0);">cosmic.piaozone.com 443 （税控云）</font>

<font style="color:rgb(0, 0, 0);">cosmic-demo.piaozone.com 80（websocket） </font>

<font style="color:rgb(0, 0, 0);">title.piaozone.com 80/443 (查询发票抬头) </font>

<font style="color:rgb(0, 0, 0);">lqpt.chinatax.gov.cn 8443 （乐企） </font>

<font style="color:rgb(0, 0, 0);">img. piaozone.com 443 </font>

<font style="color:rgb(0, 0, 0);">pi.weixin.qq.com 80、443</font>

![](https://cdn.nlark.com/yuque/0/2024/png/39256605/1721383466427-9cecd483-1019-4a9d-99fd-9b52fca08ebf.png)





#### <font style="color:rgb(0, 0, 0);">查询订单失败</font>
<font style="color:rgb(38, 38, 38);">【问题】：</font>扫码开票失败：<font style="color:rgb(0, 0, 0);">查询订单失败</font>

<font style="color:rgb(38, 38, 38);">【方案】：</font>

<font style="color:rgb(0, 0, 0);">查日志，排查对方系统是否开通网络权限</font>

![](https://cdn.nlark.com/yuque/0/2024/png/39256605/1732092194858-4aafa757-d99e-411e-8246-a811a3069ab7.png)



#### <font style="color:rgb(51,51,51);">未查询到可用的数电账号</font>
<font style="color:rgb(38, 38, 38);">【问题】：</font>

<font style="color:rgb(51,51,51);">税号:[91440300MA5EW1BM6B]未查询到可用的数电账号，请前往基础资料-企业管理-数电配置进>行相关配置</font>

<font style="color:rgb(51,51,51);">税号:[91440300MA5EW1BM6B]未查询到默认的数电账号，请前往基础资料-企业管理-数电配置-进行相关配置</font>

<font style="color:rgb(38, 38, 38);">【方案】：</font>

<font style="color:rgb(51,51,51);">数电配置如果已经配置并设置了默认账号，可检查下企业信息维护里，数电开票通道有无设置"新电子发票服务平台“</font>

<font style="color:rgb(51,51,51);"></font>![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764146364012-5b5f3a86-7738-42c6-8d0f-61862e09e2f5.png)

#### 


#### 销项发票税务组织
<font style="color:rgb(38, 38, 38);">【问题】：如何更新销项全票池的税务组织</font>

<font style="color:rgb(38, 38, 38);">【方案】：刷sql:</font>

<font style="color:rgb(0, 0, 0);">UPDATE t_sim_vatinvoice SET fmaintaxorg = '（组织id）', WHERE fsalertaxno = '税号';</font>

<font style="color:rgb(0, 0, 0);"></font>

<font style="color:rgb(0, 0, 0);"></font>

#### <font style="color:rgb(0, 0, 0);">开红票修改备注</font>
【问题】：开红字发票时是否支持修改备注信息

<font style="color:rgb(38, 38, 38);">【方案】：</font><font style="color:rgb(51,51,51);">电子税局开票时，负数数电发票不支持修改备注</font>

<font style="color:rgb(51,51,51);">（1）电子税局开具数电票</font>

<font style="color:rgb(51,51,51);">开具正数发票：200位，一个汉字、数字、英文、特殊字符算1位</font>

<font style="color:rgb(51,51,51);">开具负数发票：不支持备注</font>

<font style="color:rgb(51,51,51);">（</font><font style="color:rgb(51,51,51);">2</font><font style="color:rgb(51,51,51);">）乐企</font>

<font style="color:rgb(51,51,51);">开具正数、负数发票，最长450位，一个汉字、数字、英文、特殊字符算1位</font>

<font style="color:rgb(38, 38, 38);"></font>

<font style="color:rgb(38, 38, 38);"></font>

<font style="color:rgb(38, 38, 38);"></font>

#### <font style="color:rgb(38, 38, 38);">票面显示销方地址电话，银行账号</font>
【问题】：数电票开票时，希望默认显示销方的地址电话，银行账号等信息到发票的备注上

<font style="color:rgb(38, 38, 38);">【方案】：基础服务云-公共设置-参数配置-系统参数-发票云-基础资料打开下数电票配置参数</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764208067203-16dc7565-1128-474f-968a-a3922131a97f.png)



<font style="color:rgb(38, 38, 38);"></font>

<font style="color:rgb(38, 38, 38);"></font>

#### <font style="color:rgb(38, 38, 38);">未将对象引用设置到对象的实例</font>
【问题】：开票报错：未将对象引用设置到对象的实例

<font style="color:rgb(38, 38, 38);">【方案】：检查运营后台-金税连接设置下所设置的通道类型，一般修改为全电RPA或者乐企</font>

<font style="color:rgb(38, 38, 38);"></font>

<font style="color:rgb(38, 38, 38);"></font>

#### <font style="color:rgb(38, 38, 38);">红字确认单回退</font>
【问题】：已作废的红字确认单无法回退开票申请单

<font style="color:rgb(38, 38, 38);">【方案】：</font>

<font style="color:rgb(38, 38, 38);">红字确认单上只有数据来源为“匹配推送”且“未录入、录入失败、已录入(确认状态为作废)”的才可以回退。</font>

<font style="color:rgb(38, 38, 38);">其他情况直接新增新的红字确认单。</font>

<font style="color:rgb(38, 38, 38);"></font>





#### <font style="color:rgb(51,51,51);">请在发票云进行红冲或作废冲销财务应收单</font>
【问题】：财务应收单AR-241230-212052:根据开票申请单生成，请在发票云进行红冲或作废冲销财务应收单。

<font style="color:rgb(38, 38, 38);">【方案】：</font><font style="color:rgb(51,51,51);">这是应收的判断，请咨询应收老师是否可以去掉该校验。</font>



<font style="color:rgb(51,51,51);"></font>

#### <font style="color:rgb(51,51,51);">企业更名后怎么红冲历史发票</font>
【问题】：企业更名后，红冲之前开具的发票有何要求？

<font style="color:rgb(38, 38, 38);">【方案】：</font><font style="color:rgb(51,51,51);">企业更名后，本企业作为销方/购方，红冲更名前的发票都应该使用原名称</font>

<font style="color:rgb(51,51,51);">企业更改企业名称后，红冲之前的蓝票，确认单数据继承于原蓝票</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223055561-20881f5e-f341-45aa-9e28-0c4abb01531a.png)



<font style="color:rgb(51,51,51);"></font>

#### **<font style="color:rgb(51,51,51);">星瀚销项发票表关系</font>**
【问题】：星瀚开票，不同开票方式，发票关系存储在什么表里？

<font style="color:rgb(38, 38, 38);">【方案】：</font>

**<font style="color:rgb(51,51,51);">正数票</font>**<font style="color:rgb(51,51,51);">直接查询 t_sim_bill_inv_relation 发票id为t_sim_bill_inv_relation中的tbillid</font>



**<font style="color:rgb(51,51,51);">负数普票</font>**<font style="color:rgb(51,51,51);">判断数据来源：</font>

<font style="color:rgb(51,51,51);">数据来源为单据拆合</font><font style="color:rgb(51,51,51);"> : </font><font style="color:rgb(51,51,51);">查询 </font><font style="color:rgb(51,51,51);">t_sim_bill_inv_relation </font><font style="color:rgb(51,51,51);">发票</font><font style="color:rgb(51,51,51);">id</font><font style="color:rgb(51,51,51);">为</font><font style="color:rgb(51,51,51);">t_sim_bill_inv_relation</font><font style="color:rgb(51,51,51);">中的</font><font style="color:rgb(51,51,51);">tbillid</font>

<font style="color:rgb(51,51,51);">数据来源为单张</font><font style="color:rgb(51,51,51);">     : </font><font style="color:rgb(51,51,51);">根据负数发票的原蓝票代码号码找到对应正数发票，根据正数发票的</font><font style="color:rgb(51,51,51);">id</font><font style="color:rgb(51,51,51);">为</font><font style="color:rgb(51,51,51);">t_sim_bill_inv_relation</font><font style="color:rgb(51,51,51);">中的</font><font style="color:rgb(51,51,51);">tbillid</font><font style="color:rgb(51,51,51);">找到对应的开票申请单</font>

<font style="color:rgb(51,51,51);"></font>

**<font style="color:rgb(51,51,51);">负数专票</font>**

<font style="color:rgb(51,51,51);">根据发票红字信息表编号找到对应的红字信息表，判断红字信息表的数据来源</font>

<font style="color:rgb(51,51,51);">数据来源为单据开票</font><font style="color:rgb(51,51,51);"> : </font><font style="color:rgb(51,51,51);">查询 </font><font style="color:rgb(51,51,51);">t_sim_bill_inv_relation </font><font style="color:rgb(51,51,51);">红字信息表</font><font style="color:rgb(51,51,51);">id</font><font style="color:rgb(51,51,51);">为</font><font style="color:rgb(51,51,51);">t_sim_bill_inv_relation</font><font style="color:rgb(51,51,51);">中的</font><font style="color:rgb(51,51,51);">tbillid</font>

<font style="color:rgb(51,51,51);">数据来源为手工新增</font><font style="color:rgb(51,51,51);"> : </font><font style="color:rgb(51,51,51);">根据红字信息表的原蓝票代码号码找到对应正数发票，根据正数发票的</font><font style="color:rgb(51,51,51);">id</font><font style="color:rgb(51,51,51);">为</font><font style="color:rgb(51,51,51);">t_sim_bill_inv_relation</font><font style="color:rgb(51,51,51);">中的</font><font style="color:rgb(51,51,51);">tbillid</font><font style="color:rgb(51,51,51);">找到对应的开票申请单</font>

<font style="color:rgb(51,51,51);"></font>

**<font style="color:rgb(51,51,51);">负数全电票</font>**

<font style="color:rgb(51,51,51);">根据发票红字确认单编号找到对应的红字确认单，判断红字确认单的数据来源</font>

<font style="color:rgb(51,51,51);">数据来源为单据开票</font><font style="color:rgb(51,51,51);"> : </font><font style="color:rgb(51,51,51);">查询 </font><font style="color:rgb(51,51,51);">t_sim_bill_inv_relation </font><font style="color:rgb(51,51,51);">红字确认单</font><font style="color:rgb(51,51,51);">id</font><font style="color:rgb(51,51,51);">为</font><font style="color:rgb(51,51,51);">t_sim_bill_inv_relation</font><font style="color:rgb(51,51,51);">中的</font><font style="color:rgb(51,51,51);">tbillid</font>

<font style="color:rgb(51,51,51);">数据来源为手工新增</font><font style="color:rgb(51,51,51);"> : </font><font style="color:rgb(51,51,51);">根据红字确认单的原蓝票号码找到对应正数发票，根据正数发票的</font><font style="color:rgb(51,51,51);">id</font><font style="color:rgb(51,51,51);">为</font><font style="color:rgb(51,51,51);">t_sim_bill_inv_relation</font><font style="color:rgb(51,51,51);">中的</font><font style="color:rgb(51,51,51);">tbillid</font><font style="color:rgb(51,51,51);">找到对应的开票申请单</font>

<font style="color:rgb(51,51,51);"></font>

**<font style="color:rgb(51,51,51);">没有明细关系</font>**

<font style="color:rgb(51,51,51);">1</font><font style="color:rgb(51,51,51);">、在负数开票申请单中直接填入红字信息表编号</font>

<font style="color:rgb(51,51,51);">2</font><font style="color:rgb(51,51,51);">、红字确认单</font>

<font style="color:rgb(51,51,51);">3</font><font style="color:rgb(51,51,51);">、手工处理，点击编辑，有增删行</font>



**<font style="color:rgb(51,51,51);">根据发票号码和明细查负数开票申请单</font>**

<font style="color:rgb(51,51,51);">1</font><font style="color:rgb(51,51,51);">、查出销方税号发票表所在分表</font>

<font style="color:rgb(51,51,51);">配置工具</font><font style="color:rgb(51,51,51);">-</font><font style="color:rgb(51,51,51);">水平分表</font><font style="color:rgb(51,51,51);">-</font><font style="color:rgb(51,51,51);">分片语句生成，选择税务库，用实际的税号，放进去</font>

<font style="color:rgb(51,51,51);">select * from t_sim_vatinvoice tsv  where fsalertaxno='</font><font style="color:rgb(51,51,51);">销方税号</font><font style="color:rgb(51,51,51);">'</font>

<font style="color:rgb(51,51,51);">2</font><font style="color:rgb(51,51,51);">、查出发票的</font><font style="color:rgb(51,51,51);">ID</font>

<font style="color:rgb(51,51,51);">select fid from t_sim_vatinvoice</font><font style="color:rgb(51,51,51);">（分表） </font><font style="color:rgb(51,51,51);">tsv  where finvoiceno='</font><font style="color:rgb(51,51,51);">发票号码</font><font style="color:rgb(51,51,51);">'</font>

<font style="color:rgb(51,51,51);">3</font><font style="color:rgb(51,51,51);">、根据发票</font><font style="color:rgb(51,51,51);">ID</font><font style="color:rgb(51,51,51);">查出对应的匹配明细</font><font style="color:rgb(51,51,51);">ID</font>

<font style="color:rgb(51,51,51);">select fsbillid from t_sim_match_inv_relation where ftdetailid in (</font>

<font style="color:rgb(51,51,51);">select fentryid from t_sim_red_confirm_items </font>

<font style="color:rgb(51,51,51);">where fid in (2020960653619020800,2020960726583132160)</font>

<font style="color:rgb(51,51,51);">and fgoodsname like  '%</font><font style="color:rgb(51,51,51);">瑞舒伐他汀钙片</font><font style="color:rgb(51,51,51);">')  --</font><font style="color:rgb(51,51,51);">明细</font>

<font style="color:rgb(51,51,51);">4</font><font style="color:rgb(51,51,51);">、根据匹配明细</font><font style="color:rgb(51,51,51);">ID</font><font style="color:rgb(51,51,51);">查出对应单据编号</font>

<font style="color:rgb(51,51,51);">select distinct fsbillno  from t_sim_matchbill_relation where ftdetailid in (</font>

<font style="color:rgb(51,51,51);">select fentryid from t_sim_match_bill_item </font>

<font style="color:rgb(51,51,51);">where fid = 2013145105732481024 and fgoodsname like  '%</font><font style="color:rgb(51,51,51);">瑞舒伐他汀钙片</font><font style="color:rgb(51,51,51);">');</font>

<font style="color:rgb(51,51,51);"></font>

**<font style="color:rgb(51,51,51);">根据正数开票申请单号查发票号码</font>**

<font style="color:rgb(51,51,51);">select distinct inv.finvoiceno from t_sim_original_bill bill</font>

<font style="color:rgb(51,51,51);">join t_sim_bill_inv_relation relation on bill.fid = relation.fsbillid </font>

<font style="color:rgb(51,51,51);">join t_sim_vatinvoice inv on relation.ftbillid = inv.fid </font>

<font style="color:rgb(51,51,51);">where bill.fbillno = '</font><font style="color:rgb(51,51,51);">开票申请单编号</font><font style="color:rgb(51,51,51);">'</font>

<font style="color:rgb(51,51,51);"></font>

<font style="color:rgb(51,51,51);"></font>

<font style="color:rgb(51,51,51);"></font>

#### **<font style="color:rgb(51,51,51);">正负数开票申请单据合并成负数开票申请单失败，报错需补充原蓝票信息</font>**
<font style="color:rgb(51,51,51);">【方案】：负数开票申请单的购销身份信息为空导致，手工维护。</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223117953-f7cdc90d-f821-4e6d-9d24-c698765bdcf9.png)







#### 应收单下推开票申请单
【问题】：应收单下推发票云，没有弹出选择“转换规则”的界面

<font style="color:rgb(51,51,51);"></font>![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223147216-ffb04545-507a-4dab-a736-2a43c4c9bc77.png)

<font style="color:rgb(38, 38, 38);">【方案】：</font>

<font style="color:rgb(51,51,51);">开发平台—>财务应收单：下推按钮的操作代码，关闭“跳过下推界面”。</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764228927641-1f7826ca-6ea2-464b-b786-1e9685efc3b4.png)







#### **<font style="color:rgb(51,51,51);">未配置开票项，请先配置</font>**
【问题】：应收单下推发票云，明细XXXXX未配置开票项，请先配置

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223171439-ca701130-de33-4f3c-99a9-da686134cf98.png)

<font style="color:rgb(38, 38, 38);">【方案】：</font>

<font style="color:rgb(51,51,51);">发票云->基础资料->开票项管理，维护开票项。</font>

<font style="color:rgb(51,51,51);">维护开票项时，先选择下方的物料信息，选择之后根据需要修改开票项内容。</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223178927-7fcfb958-7a1c-4fd3-bbbc-0b0668ba3902.png)

<font style="color:rgb(51,51,51);"></font>

<font style="color:rgb(51,51,51);"></font>

#### <font style="color:rgb(51,51,51);">发票字段长度限制</font>
<font style="color:rgb(51,51,51);">数电发票，电子税局开票：各开票字段字符长度具体规则如下:</font>

<font style="color:rgb(51,51,51);">①</font><font style="color:rgb(51,51,51);"> 购方名称、销方名称</font><font style="color:rgb(51,51,51);">:</font><font style="color:rgb(51,51,51);">长度不能超过</font><font style="color:rgb(51,51,51);">100</font><font style="color:rgb(51,51,51);">字符</font>

<font style="color:rgb(51,51,51);">②</font><font style="color:rgb(51,51,51);"> 购方税号、销方税号</font><font style="color:rgb(51,51,51);">:</font><font style="color:rgb(51,51,51);">长度不能超过</font><font style="color:rgb(51,51,51);">20</font><font style="color:rgb(51,51,51);">字符</font>

<font style="color:rgb(51,51,51);">③</font><font style="color:rgb(51,51,51);"> 购买方、销方地址及电话</font><font style="color:rgb(51,51,51);">:</font><font style="color:rgb(51,51,51);">长度不能超过</font><font style="color:rgb(51,51,51);">100</font><font style="color:rgb(51,51,51);">字符</font>

<font style="color:rgb(51,51,51);">④</font><font style="color:rgb(51,51,51);"> 购买方、销方开户行及账号</font><font style="color:rgb(51,51,51);">:</font><font style="color:rgb(51,51,51);">购买方开户行、账号限</font><font style="color:rgb(51,51,51);">100 </font><font style="color:rgb(51,51,51);">字符</font><font style="color:rgb(51,51,51);">; </font><font style="color:rgb(51,51,51);">销方开户行限</font><font style="color:rgb(51,51,51);">100</font><font style="color:rgb(51,51,51);">字符</font><font style="color:rgb(51,51,51);">,</font><font style="color:rgb(51,51,51);">销售方账号限</font><font style="color:rgb(51,51,51);">60</font><font style="color:rgb(51,51,51);">字符</font>

<font style="color:rgb(51,51,51);">⑤</font><font style="color:rgb(51,51,51);"> 购买方邮箱</font><font style="color:rgb(51,51,51);">:</font><font style="color:rgb(51,51,51);">长度不能超过</font><font style="color:rgb(51,51,51);">72</font><font style="color:rgb(51,51,51);">字符</font>

<font style="color:rgb(51,51,51);">⑥</font><font style="color:rgb(51,51,51);"> 备注</font><font style="color:rgb(51,51,51);">:</font><font style="color:rgb(51,51,51);">长度不能超过</font><font style="color:rgb(51,51,51);">230</font><font style="color:rgb(51,51,51);">字符</font>

<font style="color:rgb(51,51,51);">⑦</font><font style="color:rgb(51,51,51);"> 开票名称</font><font style="color:rgb(51,51,51);">:</font><font style="color:rgb(51,51,51);">长度不能超过</font><font style="color:rgb(51,51,51);">100</font><font style="color:rgb(51,51,51);">字符</font><font style="color:rgb(51,51,51);">,</font><font style="color:rgb(51,51,51);">不含简称和两个</font><font style="color:rgb(51,51,51);">*</font><font style="color:rgb(51,51,51);">字符</font>

<font style="color:rgb(51,51,51);">⑧</font><font style="color:rgb(51,51,51);"> 单位</font><font style="color:rgb(51,51,51);">:</font><font style="color:rgb(51,51,51);">长度不能超过</font><font style="color:rgb(51,51,51);">22</font><font style="color:rgb(51,51,51);">字符</font>

<font style="color:rgb(51,51,51);">⑨</font><font style="color:rgb(51,51,51);"> 单价</font><font style="color:rgb(51,51,51);">:</font><font style="color:rgb(51,51,51);">长度不能超过</font><font style="color:rgb(51,51,51);">16</font><font style="color:rgb(51,51,51);">字符</font><font style="color:rgb(51,51,51);">,</font><font style="color:rgb(51,51,51);">最大保留</font><font style="color:rgb(51,51,51);">13</font><font style="color:rgb(51,51,51);">位小数</font>

<font style="color:rgb(51,51,51);">⑩</font><font style="color:rgb(51,51,51);"> 规格型号</font><font style="color:rgb(51,51,51);">:</font><font style="color:rgb(51,51,51);">长度不能超过</font><font style="color:rgb(51,51,51);">40</font><font style="color:rgb(51,51,51);">字符</font>

<font style="color:rgb(51,51,51);">字段长度统计工具</font><font style="color:rgb(51,51,51);">:https://www.eteste.com/</font>



#### <font style="color:rgb(51,51,51);">登录发票云平台失败:您的账号在系统中不存在!</font>
【问题】：星瀚静态二维码开票提交开票的时候报错“登录发票云平台失败:您的账号在系统中不存在!”

<font style="color:rgb(38, 38, 38);">【方案】：</font><font style="color:rgb(51,51,51);">通过日志查询请求参数里登录用户信息在发票云中是否存在，不存在则新增用户或修改移动云初始化的用户。</font>



<font style="color:rgb(51,51,51);"></font>

#### <font style="color:rgb(51,51,51);">非发票云红冲的发票关联开票申请单</font>
【问题】：税局直接红冲的发票， 怎么跟系统里的负数开票申请单关联，回写应收或业务单据？

<font style="color:rgb(38, 38, 38);">【方案】：红字确认单界面下载，然后负数开票申请单维护红字确认单编号点击开票。（红字确认单界面点红冲则无法关联）</font>







<font style="color:rgb(51,51,51);"></font>

#### **<font style="color:rgb(51,51,51);">开具报废产品发票的特殊要求</font>**
<font style="color:rgb(51,51,51);">报废产品开具比较特殊，购买方地址电话字段需要按以下格式传：</font>

<font style="color:rgb(51,51,51);">填写规范：省</font><font style="color:rgb(51,51,51);">&&</font><font style="color:rgb(51,51,51);">市</font><font style="color:rgb(51,51,51);">&&</font><font style="color:rgb(51,51,51);">区</font><font style="color:rgb(51,51,51);">/</font><font style="color:rgb(51,51,51);">县</font><font style="color:rgb(51,51,51);">&&</font><font style="color:rgb(51,51,51);">行政区划</font><font style="color:rgb(51,51,51);">&&</font><font style="color:rgb(51,51,51);">详细地址，</font>

<font style="color:rgb(51,51,51);"></font>

<font style="color:rgb(51,51,51);">没有区县级别时，可不填写</font>

<font style="color:rgb(51,51,51);">1</font><font style="color:rgb(51,51,51);">、有区县级别（深圳）示例：广东省</font><font style="color:rgb(51,51,51);">&&</font><font style="color:rgb(51,51,51);">深圳市</font><font style="color:rgb(51,51,51);">&&</font><font style="color:rgb(51,51,51);">南山区</font><font style="color:rgb(51,51,51);">&&</font><font style="color:rgb(51,51,51);">粤海街道</font><font style="color:rgb(51,51,51);">&&</font><font style="color:rgb(51,51,51);">沙河西路</font><font style="color:rgb(51,51,51);">1</font><font style="color:rgb(51,51,51);">号</font>

<font style="color:rgb(51,51,51);">2</font><font style="color:rgb(51,51,51);">、无区县级别（中山）示例：广东省</font><font style="color:rgb(51,51,51);">&&</font><font style="color:rgb(51,51,51);">中山市</font><font style="color:rgb(51,51,51);">&&</font><font style="color:rgb(51,51,51);">沙溪镇</font><font style="color:rgb(51,51,51);">&&</font><font style="color:rgb(51,51,51);">宝珠东路</font><font style="color:rgb(51,51,51);">1</font><font style="color:rgb(51,51,51);">号</font>

<font style="color:rgb(51,51,51);">3、直辖市示例：北京市&&顺义区&&东里街道&&东大街1号</font>

<font style="color:rgb(51,51,51);"></font>

<font style="color:rgb(51,51,51);"></font>

#### **<font style="color:rgb(51,51,51);">红字确认单新增时，下拉的发票类型不全</font>**
![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223314595-e96a895a-3446-4162-9ed5-846d4928d69b.png)

<font style="color:rgb(51,51,51);">【方案】：</font>

<font style="color:rgb(51,51,51);">开发平台->红字确认单->发票基本信息,看下是否勾选显示了</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223326820-dd630b5f-75c5-44aa-95e9-0632653145d8.png)

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223330437-cff433e6-803f-42e9-9720-bbaea2dee608.png)









#### **<font style="color:rgb(51,51,51);">当前发票正在开票中，发票流水号为</font>****<font style="color:rgb(51,51,51);">:[4ZRPDWR1DOZYUIIFMPHQ]</font>**
<font style="color:rgb(51,51,51);">【问题】：退回开票申请单时，提示当前发票正在开票中，想退回不再开具。</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223372560-0dc57863-b48e-4dc3-9666-65cfa75afd66.png)

<font style="color:rgb(51,51,51);">【方案】：提供销方税号，报错的发票流水号给发票云客服（</font>[https://tax.piaozone.com/sobot-web/home](https://tax.piaozone.com/sobot-web/home)<font style="color:rgb(51,51,51);">）</font>

#### 
<font style="color:rgb(51,51,51);"></font>

#### **<font style="color:rgb(51,51,51);">第XXX行商品税率:0.09不合法,请使用如下税率：0.13</font>**
<font style="color:rgb(51,51,51);">A：该商品明细的税收分类编码在税局不允许开具该税率，或者需要维护对应优惠政策才可以开具。</font>



<font style="color:rgb(51,51,51);"></font>

#### **<font style="color:rgb(51,51,51);">不动产地址怎么新增</font>**
<font style="color:rgb(51,51,51);">A：输入任意一个错误地址后，会出现新增按钮。</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223402263-64f91584-2b68-4fed-9438-912b7f7f38fd.png)

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223409182-c23d51a7-e88e-4b32-9f9e-1579f636c3a7.png)

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223413599-03bb5ebe-ab70-44d3-95de-780c92e88ca0.png)





#### **<font style="color:rgb(51,51,51);">更新</font>****<font style="color:rgb(51,51,51);">aws</font>****<font style="color:rgb(51,51,51);">企业默认账号失败</font>****<font style="color:rgb(51,51,51);">:can't parse argument number</font>**
![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764231402314-6fb94b5d-fd56-4153-b628-e4021a33e4b8.png)

<font style="color:rgb(51,51,51);">A：查看发票云版本，某固定版本出现此问题，升级最新版本。</font>







#### **<font style="color:rgb(51,51,51);">红冲维护了收件邮箱，但没有自动发送邮件</font>**
【方案】：检查以下两个配置：

<font style="color:rgb(51,51,51);">配置路径：开发平台</font><font style="color:rgb(51,51,51);">→</font><font style="color:rgb(51,51,51);">发票云</font><font style="color:rgb(51,51,51);">→</font><font style="color:rgb(51,51,51);">系统管理</font><font style="color:rgb(51,51,51);">→</font><font style="color:rgb(51,51,51);">云应用参数配置</font><font style="color:rgb(51,51,51);">→</font><font style="color:rgb(51,51,51);">参数配置单据</font>

<font style="color:rgb(51,51,51);">新增：红票邮件发送</font>

<font style="color:rgb(51,51,51);"></font><font style="color:rgb(51,51,51);">配置项类型：</font><font style="color:rgb(51,51,51);">push_sms_config</font>

<font style="color:rgb(51,51,51);"></font><font style="color:rgb(51,51,51);">配置项</font><font style="color:rgb(51,51,51);">key</font><font style="color:rgb(51,51,51);">：</font><font style="color:rgb(51,51,51);">red_push_sms</font>

<font style="color:rgb(51,51,51);">配置项值：</font><font style="color:rgb(51,51,51);">1</font>

<font style="color:rgb(51,51,51);"></font>

<font style="color:rgb(51,51,51);">新增：匹配单来源</font>

<font style="color:rgb(51,51,51);"></font><font style="color:rgb(51,51,51);">配置项类型：</font><font style="color:rgb(51,51,51);">bdm_send_setting</font>

<font style="color:rgb(51,51,51);"></font><font style="color:rgb(51,51,51);">配置项</font><font style="color:rgb(51,51,51);">key</font><font style="color:rgb(51,51,51);">：</font><font style="color:rgb(51,51,51);">match_inv_send_config</font>

<font style="color:rgb(51,51,51);"></font><font style="color:rgb(51,51,51);">配置项值：</font><font style="color:rgb(51,51,51);">1</font>

<font style="color:rgb(51,51,51);"></font>

<font style="color:rgb(51,51,51);"></font>

#### **<font style="color:rgb(51,51,51);">星瀚的自动匹配红字确认单，匹配不到销方申请的</font>**
<font style="color:rgb(51,51,51);">【方案】：</font>

<font style="color:rgb(51,51,51);">配置路径：开发平台</font><font style="color:rgb(51,51,51);">→</font><font style="color:rgb(51,51,51);">发票云</font><font style="color:rgb(51,51,51);">→</font><font style="color:rgb(51,51,51);">系统管理</font><font style="color:rgb(51,51,51);">→</font><font style="color:rgb(51,51,51);">云应用参数配置</font><font style="color:rgb(51,51,51);">→</font><font style="color:rgb(51,51,51);">参数配置单据</font>

<font style="color:rgb(51,51,51);">列表-预览，新增：</font>

<font style="color:rgb(51,51,51);"></font><font style="color:rgb(51,51,51);">配置项类型：</font><font style="color:rgb(51,51,51);">matchRedConfirm</font>

<font style="color:rgb(51,51,51);"></font><font style="color:rgb(51,51,51);">配置项</font><font style="color:rgb(51,51,51);">key</font><font style="color:rgb(51,51,51);">：</font><font style="color:rgb(51,51,51);">containsBuyerApply</font>

<font style="color:rgb(51,51,51);">配置项值：1</font>

#### 
<font style="color:rgb(51,51,51);"></font>

#### **<font style="color:rgb(51,51,51);">发票明细第1行，未选择商品分类编码</font>**
<font style="color:rgb(51,51,51);">A：单张开票时，输入商品名称后，需回车键，弹出选择框，选择税收分类编码。</font>

<font style="color:rgb(51,51,51);"></font>

#### **<font style="color:rgb(51,51,51);">红字确认单的状态不满足开具条件，无法开具红字发票</font>**
<font style="color:rgb(51,51,51);">A：检查对应的红字确认单的状态，如果是需要对方确认的，需要对方确认后方能开具。</font>



<font style="color:rgb(51,51,51);"></font>

#### **<font style="color:rgb(51,51,51);">原蓝票明细行序号从1开始</font>**
<font style="color:rgb(51,51,51);">A：1，部分红冲，负数开票申请单，一键开票，原蓝票序号手动填1开具</font>

<font style="color:rgb(51,51,51);">      2，部分红冲，先手动申请红字确认单，再手动关联到开票申请单再下推开票</font>

<font style="color:rgb(51,51,51);">     3，使用自动匹配功能开具红字发票。</font>

<font style="color:rgb(51,51,51);"></font>

<font style="color:rgb(51,51,51);"></font>

#### **<font style="color:rgb(51,51,51);">扫码开票失败，qrkey不存在，请检查是否同步移动云或者二维码超过有效期</font>**
<font style="color:rgb(51,51,51);">A：【发票云】→【基础资料】→【开票参数设置】→【扫码开票设置】→【动态二维码设置】，点击“同步移动云”</font>

<font style="color:#117CEE;">（注意，点击同步移动云后，虽提示成功，但后台有缓存，需要等一会才会生效）</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223461266-1c51dcb4-ab88-46a1-b25a-afe764415481.png)







#### **<font style="color:rgb(51,51,51);">【开票管理-待开发票】的“自动重开”中的失败原因怎么新增</font>**
<font style="color:rgb(51,51,51);">A：可参考：</font>

<font style="color:rgb(51,51,51);">https://www.yuque.com/piaozone/implement/po9t0t0f6x7azz1h?singleDoc# </font><font style="color:rgb(51,51,51);">《【开票管理</font><font style="color:rgb(51,51,51);">-</font><font style="color:rgb(51,51,51);">待开发票】的</font><font style="color:rgb(51,51,51);">“</font><font style="color:rgb(51,51,51);">自动重开</font><font style="color:rgb(51,51,51);">”</font><font style="color:rgb(51,51,51);">中的原因新增办法》</font>

<font style="color:#117CEE;">注：报错原因支持正则表达式</font>

#### 
<font style="color:rgb(51,51,51);"></font>

#### **<font style="color:rgb(51,51,51);">请求接口失败:单据编号[SOINV20250716000001]开票人[发票云标准业务接口授权账户]不合法-包含非GBK编码或是超最大长度[16]字节</font>**
<font style="color:rgb(51,51,51);">A：开票人传值异常，检查是否存在空格或者特殊字符等，可检查基础资料里的开票人设置。</font>

<font style="color:rgb(51,51,51);"></font>

#### **<font style="color:rgb(51,51,51);">第1行商品简称不合法,合法值为:其他软件服务,请检查！</font>**
<font style="color:rgb(51,51,51);">A：近期税局更新了税收分类编码简称，需要更新开票项所选择的税收分类编码，选择更精确的层级。</font>

<font style="color:rgb(51,51,51);">spbmjc='</font><font style="color:rgb(51,51,51);">软件维护服务</font><font style="color:rgb(51,51,51);">' where spbm='3040201030000000000';</font>

<font style="color:rgb(51,51,51);">spbmjc='</font><font style="color:rgb(51,51,51);">软件测试服务</font><font style="color:rgb(51,51,51);">' where spbm='3040201040000000000';</font>

<font style="color:rgb(51,51,51);">spbmjc='</font><font style="color:rgb(51,51,51);">其他软件服务</font><font style="color:rgb(51,51,51);">' where spbm='3040201990000000000';</font>

<font style="color:rgb(51,51,51);">spbmjc='</font><font style="color:rgb(51,51,51);">电路设计服务</font><font style="color:rgb(51,51,51);">' where spbm='3040202010000000000';</font>

<font style="color:rgb(51,51,51);">spbmjc='</font><font style="color:rgb(51,51,51);">电路测试服务</font><font style="color:rgb(51,51,51);">' where spbm='3040202020000000000';</font>

<font style="color:rgb(51,51,51);">spbmjc='</font><font style="color:rgb(51,51,51);">相关电路技术支持服务</font><font style="color:rgb(51,51,51);">' where spbm='3040202030000000000';</font>

<font style="color:rgb(51,51,51);">spbmjc='</font><font style="color:rgb(51,51,51);">业务流程管理服务</font><font style="color:rgb(51,51,51);">' where spbm='3040204000000000000';</font>

<font style="color:rgb(51,51,51);">spbmjc='</font><font style="color:rgb(51,51,51);">信息系统增值服务</font><font style="color:rgb(51,51,51);">' where spbm='3040205000000000000';</font>

<font style="color:rgb(51,51,51);">spbmjc='</font><font style="color:rgb(51,51,51);">信息系统服务</font><font style="color:rgb(51,51,51);">' where spbm='3040203000000000000';</font>

<font style="color:rgb(51,51,51);">发票云统一更新以前可自行调整下税收分类编码表</font>

<font style="color:rgb(51,51,51);"></font>

<font style="color:rgb(51,51,51);">7月14日晚，电子税务局电票平台按照总局货劳司意见对商品和服务税收分类编码中的部分编码简称进行了修改，其中【其他软件服务（304020199）】这一常用税收分类，原简称【信息技术服务】修改为【其他软件服务】</font>

<font style="color:rgb(51,51,51);">[</font><font style="color:rgb(51,51,51);">会议</font><font style="color:rgb(51,51,51);">]</font><font style="color:rgb(51,51,51);">具体变动如下：</font>

<font style="color:rgb(51,51,51);">1</font><font style="color:rgb(51,51,51);">、蓝字发票开具：</font>

<font style="color:rgb(51,51,51);">（</font><font style="color:rgb(51,51,51);">1</font><font style="color:rgb(51,51,51);">）当前开具</font><font style="color:rgb(51,51,51);">6%</font><font style="color:rgb(51,51,51);">服务发票使用的税收分类编码并无变化，仍为【其他软件服务（</font><font style="color:rgb(51,51,51);">304020199</font><font style="color:rgb(51,51,51);">）】</font>

<font style="color:rgb(51,51,51);">（</font><font style="color:rgb(51,51,51);">2</font><font style="color:rgb(51,51,51);">）该税收分类的简称变化，导致发票上显示的简称从【</font>_<font style="color:rgb(51,51,51);">信息技术服务</font>_<font style="color:rgb(51,51,51);">】变为了【</font>_<font style="color:rgb(51,51,51);">其他软件服务</font>_<font style="color:rgb(51,51,51);">】。</font>

<font style="color:rgb(51,51,51);">现开具【其他软件服务】蓝字发票，票面展示均为【</font>_<font style="color:rgb(51,51,51);">其他软件服务</font>_<font style="color:rgb(51,51,51);">XXXX</font><font style="color:rgb(51,51,51);">】</font>

<font style="color:rgb(51,51,51);">旧简称开具发票：</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223479398-157709da-8df6-4e2e-b29a-7e9b1b8faf7a.png)

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223484614-98640a64-fd66-43ee-a01d-80e0da730b79.png)

<font style="color:rgb(51,51,51);">2、红字发票开具：对变更前的发票进行红冲时，红字确认单及红字发票的编码简称与原发票相同，即旧编码简称【</font>_<font style="color:rgb(51,51,51);">信息技术服务</font>_<font style="color:rgb(51,51,51);">】</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223500860-1c66598a-c302-474e-8dd0-50f11f84784f.png)

#### 
<font style="color:rgb(51,51,51);"></font>

#### **<font style="color:rgb(51,51,51);">销方税号与授权税号不一致，无法开票</font>**
<font style="color:rgb(51,51,51);">【方案】：</font>

<font style="color:rgb(51,51,51);">1</font><font style="color:rgb(51,51,51);">，当前销方配置的销方税号错误</font>

<font style="color:rgb(51,51,51);">2</font><font style="color:rgb(51,51,51);">，当前销方配置的授权参数在发票云后台实际对应 另外的税号 </font>

<font style="color:rgb(51,51,51);">3</font><font style="color:rgb(51,51,51);">，配置的参数可能使用了</font><font style="color:rgb(51,51,51);">TN_</font><font style="color:rgb(51,51,51);">开头的租户授权参数 ，应改用企业授权参数</font>



<font style="color:rgb(51,51,51);"></font>

#### **<font style="color:rgb(51,51,51);">第[X]行增值税专用发票不允许开具0税率发票</font>**
<font style="color:rgb(51,51,51);">A：专票不能零税率，如是赠品，可做100%折扣处理</font>

#### 
<font style="color:rgb(51,51,51);"></font>

#### **<font style="color:rgb(51,51,51);">如何隐藏开票管理界面，乐企汇总按钮</font>**
<font style="color:rgb(51,51,51);">A：</font>

<font style="color:rgb(51,51,51);">开发平台动态表单把功能权限打开，然后配一个查询权限，再去平台的安全管理里，把用户的汇总确认权限去掉，因为动态表单的权限也打开了，应该能看到两个汇总确认的权限，两个都移除就看不到了</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223535324-6d4cd3be-3f71-49b3-bc24-df34a71639f9.png)

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223538735-a174f89c-79be-4b2f-95bc-795053b05637.png)







#### **<font style="color:rgb(51,51,51);">批量设置：开票其他信息设置</font>****<font style="color:rgb(51,51,51);">-</font>****<font style="color:rgb(51,51,51);">单价超长截取</font>**
<font style="color:rgb(51,51,51);">方式一：刷</font><font style="color:rgb(51,51,51);">sql</font>

<font style="color:rgb(51,51,51);">update t_bdm_issue_inv_setttting set fpricetolong = '2' where 1 = 1;</font>

<font style="color:rgb(51,51,51);">方式二：开发平台</font><font style="color:rgb(51,51,51);">-</font><font style="color:rgb(51,51,51);">导入数据</font>

<font style="color:rgb(51,51,51);">（</font><font style="color:rgb(51,51,51);">1</font><font style="color:rgb(51,51,51);">）</font><font style="color:rgb(51,51,51);">“</font><font style="color:rgb(51,51,51);">批量开票设置</font><font style="color:rgb(51,51,51);">”</font><font style="color:rgb(51,51,51);">的扩展应用上，列表界面：</font>

<font style="color:rgb(51,51,51);">新增列表字段</font><font style="color:rgb(51,51,51);">[</font><font style="color:rgb(51,51,51);">组织编码</font><font style="color:rgb(51,51,51);">]</font><font style="color:rgb(51,51,51);">、</font><font style="color:rgb(51,51,51);">[</font><font style="color:rgb(51,51,51);">组织名称</font><font style="color:rgb(51,51,51);">]</font><font style="color:rgb(51,51,51);">、</font><font style="color:rgb(51,51,51);">[</font><font style="color:rgb(51,51,51);">单价超长处理规则</font><font style="color:rgb(51,51,51);">]</font><font style="color:rgb(51,51,51);">；</font>

<font style="color:rgb(51,51,51);">新增按钮【引入数据】、【保存】；</font>

<font style="color:rgb(51,51,51);">然后保存设置，预览界面</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223549656-a95c9ecf-cc7a-4552-836b-f6633fe18f57.png)

<font style="color:rgb(51,51,51);">（2）点击【引入数据】—>【立即下载】—>创建一个新的模板？</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223557346-fb5e79c6-4cc0-4e2e-98c8-db099764d444.png)

<font style="color:rgb(51,51,51);">设置引入引出模板：维护模板名称，选择引入必填字段[组织]、[单价超长处理规则]，保存模板。</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223566103-ecc99d12-9215-4daf-9a78-eba0dd0749e2.png)

<font style="color:rgb(51,51,51);">（3）勾选设置的模板，点击【下载】。打开下载的模板：维护需要批量修改的组织和规则，保存。</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223592119-9cd08e46-41fe-4af9-ae47-17b3fc90f724.png)

<font style="color:rgb(51,51,51);">（</font><font style="color:rgb(51,51,51);">4</font><font style="color:rgb(51,51,51);">）引入弹窗中：【更新已有数据】</font><font style="color:rgb(51,51,51);">—></font><font style="color:rgb(51,51,51);">【组织】</font><font style="color:rgb(51,51,51);">—></font><font style="color:rgb(51,51,51);">上传</font><font style="color:rgb(51,51,51);">excel</font><font style="color:rgb(51,51,51);">（上一步保存的文档）</font><font style="color:rgb(51,51,51);">—></font><font style="color:rgb(51,51,51);">【开始引入】</font>

<font style="color:rgb(51,51,51);">引入成功后：勾选所有数据，点击【保存】。</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223612121-ef7e5b9e-0e49-4e4b-98cc-25cb733b6b21.png)







#### **<font style="color:rgb(51,51,51);">存在相同核心单据</font>****<font style="color:rgb(51,51,51);">XXXXXX</font>****<font style="color:rgb(51,51,51);">的销售出库单，不允许通过开票申请单确认应收</font>**
<font style="color:rgb(51,51,51);">答：确认应收按钮</font><font style="color:rgb(51,51,51);">可下推生成应收单。先开票后生成应收单时</font><font style="color:rgb(51,51,51);">才</font><font style="color:rgb(51,51,51);">可使用</font><font style="color:rgb(51,51,51);">该按钮。</font>

<font style="color:rgb(51,51,51);">确认应收参考：</font>

[<u><font style="color:rgb(30,111,255);">https://club.kdcloud.com/knowledge/428130154909646592?productLineId=2&isKnowledge=2&lang=zh-CN</font></u>](https://club.kdcloud.com/knowledge/428130154909646592?productLineId=2&isKnowledge=2&lang=zh-CN)

<font style="color:rgb(51,51,51);">根据开票申请确认的财务应收单，只允许全额确认应收，不允许部分确认应收</font>

<font style="color:rgb(51,51,51);">已确认应收的开票申请单所关联的发票红冲时，只允许全额红冲，不允许部分红冲。</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223626272-1b7a01aa-3090-43ab-ae53-fc15cb702e70.png)

<font style="color:rgb(51,51,51);">具体为什么相同的不能下推，需要咨询应收那边</font>

<font style="color:rgb(51,51,51);">方案：</font>

<font style="color:rgb(51,51,51);">开发平台-应付-事中控制，禁用“开票申请单下推财务应收校验核心单据编号”这个参数即可。</font>



<font style="color:rgb(51,51,51);"></font>

<font style="color:rgb(51,51,51);"></font>

<font style="color:rgb(51,51,51);"></font>

#### **<font style="color:rgb(51,51,51);">未查询到xml地址</font>**
<font style="color:rgb(51,51,51);">【问题】：发票查询处下载发票XML格式时提示“未查询到xml地址”</font>

<font style="color:rgb(51,51,51);">【方案】：开发平台进列表单预览sim_vatinvoice_file</font>

<font style="color:rgb(51,51,51);">重新生成（注意回调地址类型看是</font><font style="color:rgb(51,51,51);">S3</font><font style="color:rgb(51,51,51);">还是文件服务器），本地文件生成状态改成未生成，回调地址类型改成文件服务器，保存后再重试。</font>

<font style="color:rgb(51,51,51);"></font>

<font style="color:rgb(51,51,51);">select * from t_sim_vatinvoice</font>

<font style="color:rgb(51,51,51);">select * from t_sim_vatinvoice_file</font>

<font style="color:rgb(51,51,51);">select fxmlfileurl from t_sim_vatinvoice_e where fid=(select fid from t_sim_vatinvoice where finvoiceno='</font><font style="color:rgb(51,51,51);">发票号码</font><font style="color:rgb(51,51,51);">');</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223679996-387a1238-3c9c-45be-87bb-05b3478ef683.png)

**<font style="color:#DF2A3F;">注：需关注配置项：</font>**

<font style="color:rgb(51,51,51);">数电票配置不上传S3文件服务器配置</font>

<font style="color:rgb(51,51,51);"></font><font style="color:rgb(51,51,51);">○ </font><font style="color:rgb(51,51,51);">配置项类型 </font><font style="color:rgb(51,51,51);">: invoicefile_config</font>

<font style="color:rgb(51,51,51);"></font><font style="color:rgb(51,51,51);">○ </font><font style="color:rgb(51,51,51);">配置项</font><font style="color:rgb(51,51,51);">key : not_upload_s3</font>

<font style="color:rgb(51,51,51);"></font><font style="color:rgb(51,51,51);">○ </font><font style="color:rgb(51,51,51);">配置项值 </font><font style="color:rgb(51,51,51);">: notUploadS3 </font>

<font style="color:rgb(51,51,51);"></font><font style="color:rgb(51,51,51);">○ </font><font style="color:rgb(51,51,51);">配置描述 </font><font style="color:rgb(51,51,51);">: </font><font style="color:rgb(51,51,51);">配置后，数电票上传到星瀚文件服务器，后续回调返回的是星瀚文件服务器地址，无法发送邮件与短信</font>

<font style="color:rgb(51,51,51);"></font>

<font style="color:rgb(51,51,51);">数电票文件生成后回调配置</font>

<font style="color:rgb(51,51,51);"></font><font style="color:rgb(51,51,51);">○ </font><font style="color:rgb(51,51,51);">配置项类型 </font><font style="color:rgb(51,51,51);">: invoicefile_config</font>

<font style="color:rgb(51,51,51);"></font><font style="color:rgb(51,51,51);">○ </font><font style="color:rgb(51,51,51);">配置项</font><font style="color:rgb(51,51,51);">key : file</font>

<font style="color:rgb(51,51,51);"></font><font style="color:rgb(51,51,51);">○ </font><font style="color:rgb(51,51,51);">配置项值 </font><font style="color:rgb(51,51,51);">:  pdf,ofd,xml</font>

<font style="color:rgb(51,51,51);">○ 配置描述 : pdf(有pdf即回调) ofd(有ofd即回调) xml(有xml即回调) pdf,xml(有pdf、xml即回调) ofd,xml(有ofd、xml即回调) ofd,pdf(有ofd、pdf即回调) pdf,ofd,xml(有pdf、ofd、xml即回调)</font>

<font style="color:rgb(51,51,51);"></font>

<font style="color:rgb(51,51,51);"></font>

<font style="color:rgb(51,51,51);"></font>

#### **<font style="color:rgb(51,51,51);">动态二维码设置新增扫码开票设置时，税号怎么修改</font>****<font style="color:rgb(51,51,51);">?</font>**
![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764232472779-259ff5db-2612-4535-9cb8-e03449fa69c9.png)

<font style="color:rgb(51,51,51);">A：右上角切换组织后关闭动态二维码设置页签再重新打开。</font>

<font style="color:rgb(51,51,51);"></font>

<font style="color:rgb(51,51,51);"></font>

<font style="color:rgb(51,51,51);"></font>

#### **<font style="color:rgb(51,51,51);">静态二维码设置有个字段配置分录，怎么用？</font>**
![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764232500155-45db7516-4bfb-4de6-81d0-b5bbdd09d069.png)

<font style="color:rgb(51,51,51);">【解答】：</font>

<font style="color:rgb(51,51,51);">先在开发平台增加字段，再通过这个配置配到扫码开票小程序的页面上</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223715783-fbd0bde3-37ff-4109-a7b8-ae317edcf1c6.png)

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223719430-3ed722cf-a12e-484b-8022-494201dfe79f.png)

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223723692-b2757de0-fc9d-48c1-81ca-7f831415cc32.png)

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223727783-68575955-5ef4-4676-86cd-561c2ca5b1f7.png)

<font style="color:rgb(51,51,51);">如果列表要显示，需要在开发平台列表上进行操作</font>

**<font style="color:rgb(51,51,51);">补充：</font>**<font style="color:rgb(51,51,51);">就是用来做备注之类的，客户扫码提交抬头的时候，可以在这个字段维护内容，开票员可以在静态二维码开票看着这个字段信息</font>



<font style="color:rgb(51,51,51);"></font>

#### **<font style="color:rgb(51,51,51);">红字确认单开票，提示：开票异常!开票人不能为空!</font>**
<font style="color:rgb(51,51,51);">A：疑似版本问题，需要升级，如果是新版本，协调研发排查</font>

<font style="color:rgb(51,51,51);"></font>

#### **<font style="color:rgb(51,51,51);">非增值税一般纳税人或者辅导期一般纳税人，不进行增值税税款所属期初始化</font>**
<font style="color:rgb(51,51,51);">A：在发票云-基础资料-企业信息处，检查下企业所设置的企业性质是一般纳税人还是小规模纳税人，小规模没有抵扣勾选能力，企业性质配置下，避免后台空跑下载任务</font>



<font style="color:rgb(51,51,51);"></font>

<font style="color:rgb(51,51,51);"></font>

#### **<font style="color:rgb(51,51,51);">通过匹配结果推送生成红字确认单再开具的红字发票关联关系查询？</font>**
<font style="color:rgb(51,51,51);">答：</font>

<font style="color:rgb(51,51,51);">select * from t_sim_matchbill_relation tsmr where tsmr.fsbillno IN ('INV-20250619-010979');</font>

<font style="color:rgb(51,51,51);">select * from t_sim_match_inv_relation tsmir where tsmir.ftbillid in (2240706369030216704);  </font>

<font style="color:rgb(51,51,51);">这两个表</font>







#### **<font style="color:rgb(51,51,51);">开票报错：单价超过税局长度限制</font>**
【方案】：<font style="color:rgb(51,51,51);">电子税局开票时：单价最长16位（含小数点），整数位最多12位，精度最多13位。</font>

<font style="color:rgb(51,51,51);">路径：基础资料-开票参数设置-开票其它设置</font>

<font style="color:rgb(51,51,51);">操作：批量开票规则设置中，选择单价“超长截取”。</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764233741952-0453d7ba-ea46-4386-b92e-3cbae86d156f.png)

【补充说明】：该配置按组织生效，去当前登录用户的所属组织。（可切换组织后关闭界面重新打开，以此切换规则所属组织）



<font style="color:rgb(51,51,51);"></font>

#### **<font style="color:rgb(51,51,51);">发票查询，点击下载时弹出的文件默认格式怎么设置？</font>**
![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223849159-37a9933a-afc8-40dc-a8a5-58e4bbadfb1f.png)

<font style="color:rgb(51,51,51);">【方案】: 开发平台-发票云-开票管理，扩展sim_choose_invoice_type 表单；</font>

<font style="color:rgb(51,51,51);">选中发票类型，设置对应的缺省值为PDF或者OFD等，缺省值可多选。</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223860763-beee4617-44cb-450b-9df8-d04062bb6c20.png)

<font style="color:rgb(51,51,51);"></font>

<font style="color:rgb(51,51,51);"></font>

#### **<font style="color:rgb(51,51,51);">只有暂存或无需审批的单据才能保存</font>**
<font style="color:rgb(51,51,51);">A：</font>

<font style="color:rgb(51,51,51);">如想跳过这个校验，需要</font><font style="color:rgb(51,51,51);">在</font><font style="color:rgb(51,51,51);">参数配置单据列表</font><font style="color:rgb(51,51,51);"> invsm_param_configuration</font><font style="color:rgb(51,51,51);">里面去配</font><font style="color:rgb(51,51,51);">，</font><font style="color:rgb(51,51,51);">配置个</font><font style="color:rgb(51,51,51);">1</font><font style="color:rgb(51,51,51);">就可以了</font>

<font style="color:rgb(51,51,51);">提示：只有暂存或无需审批的单据才能保存</font><font style="color:rgb(51,51,51);">   </font>

<font style="color:rgb(51,51,51);">参数配置单据列表</font><font style="color:rgb(51,51,51);"> invsm_param_configuration</font>

<font style="color:rgb(51,51,51);">配置项类型：</font><font style="color:rgb(51,51,51);">checkBillStateWhileSave</font>

<font style="color:rgb(51,51,51);">配置项</font><font style="color:rgb(51,51,51);">key</font><font style="color:rgb(51,51,51);">：</font><font style="color:rgb(51,51,51);">checkBillStateWhileSave</font>

<font style="color:rgb(51,51,51);">配置项值：</font><font style="color:rgb(51,51,51);">1</font>

<font style="color:rgb(51,51,51);">值为1表示跳过校验，非1 或者删除此配置项表示校验，系统默认会校验</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223877733-2c1820ed-f4c3-4cdc-9925-25669ba424ef.png)





#### **<font style="color:rgb(51,51,51);">授信额度不在有效期内</font>****<font style="color:rgb(51,51,51);">请先申报或者调整授信额度有效期</font>**
<font style="color:rgb(51,51,51);">A：</font>

<font style="color:rgb(51,51,51);">1</font><font style="color:rgb(51,51,51);">，联系税局确认额度有且在有效期内，否则与税局沟通并调整</font>

<font style="color:rgb(51,51,51);">2</font><font style="color:rgb(51,51,51);">，到开票异常列表处尝试重新开票（开票前可到单张开票那确认下是否有正常带出授信额度）</font>



<font style="color:rgb(51,51,51);"></font>

#### **<font style="color:rgb(51,51,51);">开票失败的结果也需要回调怎么处理？</font>**
<font style="color:rgb(51,51,51);">现状：默认是匹配到了自动重开设置的失败原因，再次重开失败不会再次回调</font>

<font style="color:rgb(51,51,51);">方案：配置路径：开发平台</font><font style="color:rgb(51,51,51);">→</font><font style="color:rgb(51,51,51);">发票云</font><font style="color:rgb(51,51,51);">→</font><font style="color:rgb(51,51,51);">系统管理</font><font style="color:rgb(51,51,51);">→</font><font style="color:rgb(51,51,51);">云应用参数配置</font><font style="color:rgb(51,51,51);">→</font><font style="color:rgb(51,51,51);">参数配置单据</font>

<font style="color:rgb(51,51,51);">新增：</font>

<font style="color:rgb(51,51,51);"></font><font style="color:rgb(51,51,51);">配置项类型：</font><font style="color:rgb(51,51,51);">sim_error_callback</font>

<font style="color:rgb(51,51,51);"></font><font style="color:rgb(51,51,51);">配置项</font><font style="color:rgb(51,51,51);">key</font><font style="color:rgb(51,51,51);">：</font><font style="color:rgb(51,51,51);">sim_error_force_callback</font>

<font style="color:rgb(51,51,51);"></font><font style="color:rgb(51,51,51);">配置值：</font><font style="color:rgb(51,51,51);">1</font>

<font style="color:rgb(51,51,51);">说明：对应失败原因配置了自动重开，也支持回调</font>







#### **<font style="color:rgb(51,51,51);">红冲报错：原蓝票开票日期不能为空</font>**
<font style="color:rgb(51,51,51);">【问题】：调用接口红冲发票时提示，接口文档上该字段为可选字段，</font>

<font style="color:rgb(51,51,51);">【方案】：开票管理-销售全票池-发票查询，检查蓝票是否存在。不存在则发票同步 ，能查询原蓝票后再重新 发起红冲。</font>

