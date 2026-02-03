

#### <font style="color:rgb(0, 0, 0);">星空应付单报错接收发票失败，存在非法字符</font>
<font style="color:rgb(0, 0, 0);">A：参数设置-BOS平台 --启用SQL关键字合法性验证，取消即可。</font>

<font style="color:rgb(0, 0, 0);">此参数启用后，BOS字段属性也可按字段配置忽略关键字合法性校验。</font>

<font style="color:rgb(0, 0, 0);"></font>

<font style="color:rgb(0, 0, 0);"></font>

#### <font style="color:rgb(0, 0, 0);">查看发票时，票面部分字段无法正常显示，比如金额、税额、发票号码等</font>
<font style="color:rgb(0, 0, 0);background-color:#FBDE28;">问题分析：</font>

<font style="color:rgb(0, 0, 0);">用户电脑内存不足的时候，使用【上传含多张票的pdf】按钮上传单张发票pdf，就容易失真； </font>

<font style="color:rgb(0, 0, 0);">因为我们这个按钮是把pdf里面的内容按页码切割成图片去展示，这时候内存不足，资源不够，文件就容易出现失真的情况；</font>

<font style="color:rgb(0, 0, 0);background-color:#FBDE28;">解决方案：</font>

<font style="color:rgb(0, 0, 0);"> 一般使用左边第一个按钮重新上传一下就好了</font>

![](https://cdn.nlark.com/yuque/0/2025/png/39256605/1740558654551-7386fe41-7b18-495c-bdf9-6387de3fc4a0.png)![](https://cdn.nlark.com/yuque/0/2025/png/39256605/1740558662493-4dc1c610-8a1a-4bfe-92dc-8e21659ecd1e.png)



<font style="color:rgb(0, 0, 0);"></font>

#### <font style="color:rgb(0, 0, 0);">收票单列表的接收发票按钮中发票类型能否增加全电发票类型?</font>
![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1763622763467-5ff267dd-8029-4ffe-9f6c-03ec7cfc54ea.png)

<font style="color:rgb(0, 0, 0);">方案1:升级至8.1.202304版本以及上能够支持。</font>

<font style="color:rgb(0, 0, 0);">方案2:如不升级，在收票单列表配置四宫格收票，支持直接收全电发票生成收票单(无需经过业务单据收票)配置方法:</font>

<font style="color:rgb(0, 0, 0);">至少是星空2020年11月的补丁，在收票单列表增加一个按钮，按钮标识必须为tbPiaoZoneHelper Dev，通过该按钮可以使用单据上选择发票的功能。</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1763622770736-60b66171-edcc-4e83-885a-3ce2599cbed7.png)





#### 收票提示：未设置CA密码
<font style="color:rgb(0, 0, 0);">CA密码即开票软件登录界面的第二个密码,也叫证书口令、税控密码。全电模式下CA密码字段任意填写。</font>

<font style="color:rgb(0, 0, 0);">打开星空BOS设计器-金税连接设置把CA密码字段显示出来手工填写CA密码,</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1763622884069-56f4eeff-40ae-4b16-a3a4-698b43a490fe.png)





#### 收票单列表里匹配应付时显示来将对象引用设置到对象的实例，或者无法正确匹配到对应的应付单
该报错是星空版本问题，建议升级到8.1.0.202309版本及以上版本。备注:若无法更新标准补丁，可执行临时补丁。![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1763622972617-e6c07d2e-0d00-41eb-b5e5-f645659fcfb1.png)







#### 发票接收失败,原因:发票代码+发票号码唯一
![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764235799386-ab007249-0177-4e0d-bd1d-aed8b4ce7340.png)

A：[https://vip.kingdee.com/knowledge/specialDetail/349586136861371648?category=349586385532960000&id=398279419590006272&type=Knowledge&productLineId=1&lang=zh-CN](https://vip.kingdee.com/knowledge/specialDetail/349586136861371648?category=349586385532960000&id=398279419590006272&type=Knowledge&productLineId=1&lang=zh-CN#tdsub)





#### 【星空企业版】销售发票上开票方式税控和手工的区别
[https://vip.kingdee.com/knowledge/specialDetail/349586136861371648?category=349586385532960000&id=603390996952474368&type=Knowledge&productLineId=1&lang=zh-CN](https://vip.kingdee.com/knowledge/specialDetail/349586136861371648?category=349586385532960000&id=603390996952474368&type=Knowledge&productLineId=1&lang=zh-CN)



#### 【星空企业版】星空销售普通发票和销售增值税专用发票的区别
[https://vip.kingdee.com/knowledge/specialDetail/349586136861371648?category=349586385532960000&id=614625019158518528&type=Knowledge&productLineId=1&lang=zh-CN](https://vip.kingdee.com/knowledge/specialDetail/349586136861371648?category=349586385532960000&id=614625019158518528&type=Knowledge&productLineId=1&lang=zh-CN)



#### 【星空企业版】什么情况下费用应付单和发票开票核销会产生应付调整单
[https://vip.kingdee.com/knowledge/specialDetail/349586136861371648?category=349586385532960000&id=626946318392558080&type=Knowledge&productLineId=1&lang=zh-CN](https://vip.kingdee.com/knowledge/specialDetail/349586136861371648?category=349586385532960000&id=626946318392558080&type=Knowledge&productLineId=1&lang=zh-CN)



#### 【星空企业版】费用报销单关联发票后如何实现申请报销金额大于发票金额不允许保存
[https://vip.kingdee.com/knowledge/specialDetail/349586136861371648?category=349586385532960000&id=472931358407614464&type=Knowledge&productLineId=1&lang=zh-CN](https://vip.kingdee.com/knowledge/specialDetail/349586136861371648?category=349586385532960000&id=472931358407614464&type=Knowledge&productLineId=1&lang=zh-CN)



#### 【星空企业版】应付单/采购发票与实际开票的税额不一致要如何处理
[https://vip.kingdee.com/knowledge/specialDetail/349586136861371648?category=349586385532960000&id=616436900773161984&type=Knowledge&productLineId=1&lang=zh-CN](https://vip.kingdee.com/knowledge/specialDetail/349586136861371648?category=349586385532960000&id=616436900773161984&type=Knowledge&productLineId=1&lang=zh-CN)



【星空企业版】发票红冲/开具红字发票相关问题的汇总贴

应收单当做发票使用,应收需要红冲如何处理

暂估应收模式红冲应收单怎么处理?

业务应收模式,退换票业务如何处理?

购买了发票云,开具纸质发票开错了,还没跨月,怎么处理

暂估应收模式,购买了发票云,开具纸质普通发票开错了,跨月了,怎么处理,电子普票开错了怎么处理

业务应收模式,购买了发票云,开具纸质普通发票开错了,跨月了,怎么处理,电子普票开错了怎么处理

暂估应收模式,购买了发票云,开具纸质专用发票开错了,跨月了,怎么处理,电子专票开错了怎么处理

业务应收模式,购买了发票云,开具纸质专用发票开错了,跨月了,怎么处理,电子专票开错了怎么处理

答：

[https://vip.kingdee.com/knowledge/specialDetail/349586136861371648?category=349586385532960000&id=433431110735910400&type=Knowledge&productLineId=1&lang=zh-CN](https://vip.kingdee.com/knowledge/specialDetail/349586136861371648?category=349586385532960000&id=433431110735910400&type=Knowledge&productLineId=1&lang=zh-CN)





#### The Image could not be loaded，查看发票黑色背景？
【问题】: 客户部分发票在星空客户端查看发票没问题，但星空轻应用在钉钉的业务审批中查看发票看不了或者掌上报销看不了，电脑、安卓手机无法查看预览界面、苹果手机查看都是黑色的背景？

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225023470-f0196f2e-ed51-49f9-9ba2-0df28f1ecd76.png)![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225023852-a93aa2f9-285b-428a-8148-9d2cfd6bee8d.png)

【方案】：此为星空的问题，星空针对此问题的答复为：<font style="color:#000000;">移动单据启用设置里设置的查看发票绑定的按钮不对导致，业务对象需要选择“关联发票列表”</font>

<font style="color:#000000;"></font>

<font style="color:#000000;"></font>

#### <font style="color:#000000;">星空企业版收票单列表接收发票时，发票类型没有全电发票类型可选？</font>
![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225027873-19ae5753-cf7a-4620-adb2-110f4afa03b5.png)

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225028835-fd45c81a-bb42-4eca-aa37-e3d68be5b32e.png)

<font style="color:#000000;">需更新星空版本，可参考：</font>

[https://vip.kingdee.com/knowledge/434087732113947136?productLineId=1&isKnowledge=2&lang=zh-CN](https://vip.kingdee.com/knowledge/434087732113947136?productLineId=1&isKnowledge=2&lang=zh-CN)





#### 星空企业版从税局下载发票提示发票抬头与企业名称不一致？
![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225029920-e537555e-08e4-4423-8c75-c1b754d25ffe.png)

关键要素同步下载的发票都没有购方名称。

出现这个提示就去星空的参数设置里面把抬头税号一致性校验关掉

