

#### <font style="color:rgb(0, 0, 0);">星空开票人取值逻辑： </font>
<font style="color:rgb(0, 0, 0);">销售发票单上的开票人，和公众号中电子税局账号点编辑按钮出现的开票人姓名做匹配，匹配上了用对应的账号，没匹配上用默认账号</font>

<font style="color:rgb(0, 0, 0);"></font>

#### <font style="color:rgb(0, 0, 0);">星空企业版开票报错：未将对象引用设置到对象的实例。  </font>
联系发票云服务人员，在【EOP-金税设置】检查托管类型，需要设置为全电RPA

![](https://cdn.nlark.com/yuque/0/2025/png/39256605/1761296515822-be9ba3e4-7ffb-410b-afb9-0db7701a153e.png)



#### <font style="color:rgb(0, 0, 0);">电子发票发送邮件，如何发送多个邮箱?</font>
<font style="color:rgb(0, 0, 0);">1、电子发票发送邮件配置可参考:</font>[https://vip.kingdee.com/article/12103?](https://vip.kingdee.com/article/12103?2)

<font style="color:rgb(0, 0, 0);">2、 8.1.0.202306版本支持同时发送两个邮箱中间用英文逗号隔开，低于此版本会导致设置两个邮箱推送会报错，建议根据需要考虑是否升级处理。</font>

<font style="color:rgb(0, 0, 0);"></font>

<font style="color:rgb(0, 0, 0);"></font>

#### <font style="color:rgb(0, 0, 0);">金税开票单有购货方电子邮箱，但对方收不到发票。</font>
<font style="color:rgb(0, 0, 0);">收票方手机号字段不要为座机或者为手机号即可正常推送。</font>

<font style="color:rgb(0, 0, 0);"></font>

<font style="color:rgb(0, 0, 0);"></font>

#### <font style="color:rgb(0, 0, 0);">电子发票地址为空</font>
<font style="color:rgb(0, 0, 0);">成功开具电子发票后，销售发票单据和金税开票单的电子发票地址为空，没有返回。</font>

<font style="color:rgb(0, 0, 0);">解决方案：</font>

<font style="color:rgb(0, 0, 0);">操作开票时点击金税发票开票按钮，该按钮在星空记录的是开具纸质发票，因此导致无法返回电子开票地址。</font>

<font style="color:rgb(0, 0, 0);">发票云后台存储的是发票文件，登录发票云商户运营平台-进项发票管理选择发票重推，从邮件中将地址维护到星空电子发票地址字段</font>![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1763622217972-1ebcdeb5-74b2-4bdc-8f78-e54ef9989818.png)





#### 开具发票销售金额和折扣金额可以开两行吗?
<font style="color:rgb(0, 0, 0);">发票管理系统参数勾选【分录行折扣按行打印】，折扣额单独显示开票。注意:如果存在负数行，此参数不能勾选。</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1763622451019-e29de112-27dc-4402-a1c6-fa5ce7d3c9ff.png)



#### <font style="color:rgb(51,51,51);">基础授权信息有误</font>
<font style="color:rgb(38, 38, 38);">【问题】：星空企业版开票报错：基础授权信息有误，请联系管理员！</font>

<font style="color:rgb(38, 38, 38);">【方案】：</font>

<font style="color:rgb(51,51,51);">1，检查星空金税连接设置发票云clientid、clientidsecret、加密密钥的配置，注意用授权邮件里第二点的企业授权信息进行配置</font>

<font style="color:rgb(51,51,51);">2</font><font style="color:rgb(51,51,51);">，</font><font style="color:rgb(51,51,51);">若用户需要连接发票云测试环境使用【发票助手】功能，需要完成以下操作步骤：（若不连接测试环境可跳过此步骤）</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764146411140-c692a49d-7693-49a8-975a-8e8e5e4f2550.png)

<font style="color:rgb(51,51,51);">（</font><font style="color:rgb(51,51,51);">1</font><font style="color:rgb(51,51,51);">）若星空为</font><font style="color:rgb(51,51,51);">7.6.0.202105</font><font style="color:rgb(51,51,51);">及以上版本（若没有</font><font style="color:rgb(51,51,51);">H5</font><font style="color:rgb(51,51,51);">移动端参数，则移动端参考（</font><font style="color:rgb(51,51,51);">2</font><font style="color:rgb(51,51,51);">）设置）</font>

<font style="color:rgb(51,51,51);"></font><font style="color:rgb(51,51,51);">（</font><font style="color:rgb(51,51,51);">1.1</font><font style="color:rgb(51,51,51);">）将发票管理系统参数中的三个参数设置为可见</font>

<font style="color:rgb(51,51,51);"></font><font style="color:rgb(51,51,51);">（</font><font style="color:rgb(51,51,51);">1.2</font><font style="color:rgb(51,51,51);">）相关参数为数据中心级参数，需使用</font><font style="color:rgb(51,51,51);">Administrator</font><font style="color:rgb(51,51,51);">账号登录星空进行赋值：</font>

<font style="color:rgb(51,51,51);">【使用发票云测试环境】：勾选</font>

<font style="color:rgb(51,51,51);">【发票云发票助手</font><font style="color:rgb(51,51,51);">Url</font><font style="color:rgb(51,51,51);">】：</font><font style="color:rgb(51,51,51);">https://api-dev.piaozone.com/test</font>

<font style="color:rgb(51,51,51);">【发票云接口</font><font style="color:rgb(51,51,51);">Url</font><font style="color:rgb(51,51,51);">】：</font><font style="color:rgb(51,51,51);">https://api-dev.piaozone.com/test</font>

<font style="color:rgb(51,51,51);">【发票云</font><font style="color:rgb(51,51,51);">H5</font><font style="color:rgb(51,51,51);">接口</font><font style="color:rgb(51,51,51);">Url(</font><font style="color:rgb(51,51,51);">移动端</font><font style="color:rgb(51,51,51);">)</font><font style="color:rgb(51,51,51);">】：</font><font style="color:rgb(51,51,51);">https://api-dev.piaozone.com/test/m4-web/dd/wap/index</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764146418222-5d870aec-370b-431d-a802-66988cf152ba.png)

<font style="color:rgb(51,51,51);"></font>

<font style="color:rgb(51,51,51);"></font><font style="color:rgb(51,51,51);">（</font><font style="color:rgb(51,51,51);">1.3</font><font style="color:rgb(51,51,51);">）保存即生效，无需重启</font><font style="color:rgb(51,51,51);">IIS</font><font style="color:rgb(51,51,51);">。如需还原指向正式环境，则取消</font><font style="color:rgb(51,51,51);">/</font><font style="color:rgb(51,51,51);">清空这三个字段的内容即可。</font>

<font style="color:rgb(51,51,51);">（</font><font style="color:rgb(51,51,51);">2</font><font style="color:rgb(51,51,51);">）旧版本星空私有化部署，则自行修改服务器配置文件</font>

<font style="color:rgb(51,51,51);">在星空的应用服务器上，星空的安装目录</font><font style="color:rgb(51,51,51);">Kingdee--K3Cloud--WebSite--App_Data</font><font style="color:rgb(51,51,51);">下，如图有个</font><font style="color:rgb(51,51,51);">common.config</font><font style="color:rgb(51,51,51);">文件，在文件里的</font><font style="color:rgb(51,51,51);">appSettings</font><font style="color:rgb(51,51,51);">节点下如图粘贴如下内容：</font>

<font style="color:rgb(51,51,51);"><add key="IsUsingGoldenTaxTestURL" value="1" /></font>

<font style="color:rgb(51,51,51);"><add key="PiaozoneHelperBaseUrl" value="https://api-dev.piaozone.com/test" /></font>

<font style="color:rgb(51,51,51);"><add key="PiaozoneApiBaseUrl" value="https://api-dev.piaozone.com/test" /></font>

<font style="color:rgb(51,51,51);"><add key="PiaozoneH5BaseUrl" value="https://api-dev.piaozone.com/test/m4-web/dd/wap/index" /></font>

<font style="color:rgb(51,51,51);"><add key="IsTestVersion" value="true" /></font>

<font style="color:rgb(51,51,51);">保存配置文件后即生效。后续需使用发票云正式环境，将这些节点删除即可</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764146425625-efca4035-11bb-420a-93a3-d4cf4a4a2e3b.png)

<font style="color:rgb(51,51,51);"></font>

<font style="color:rgb(51,51,51);">（</font><font style="color:rgb(51,51,51);">3</font><font style="color:rgb(51,51,51);">）旧版本公有云星空，单租户的模式下，需要提单给星空运维同事处理</font>

<font style="color:rgb(51,51,51);">（</font><font style="color:rgb(51,51,51);">4</font><font style="color:rgb(51,51,51);">）如果客户是租赁星空的公有云，但是是多租户的模式时，这时候就无法进行这个切换了，会影响其他租户</font>

<font style="color:rgb(51,51,51);">完成上述操作后，再按照正常实施流程完成配置即可</font>

<font style="color:rgb(51,51,51);">https://www.yuque.com/piaozone/implement/pyopkq?singleDoc# 《金蝶云星空【财税一体综合收票服务】实施文档》</font>

<font style="color:rgb(0, 0, 0);"></font>

<font style="color:rgb(0, 0, 0);"></font>

#### **<font style="color:rgb(51,51,51);">发票[当前开票设备开具电子发票,明细行数最大上限不允许超100行,建议调整销售发票单据的明细行数在范围内,再重新发起开票]生成金税开票单失败</font>**
<font style="color:rgb(51,51,51);">答：</font>[<u><font style="color:rgb(30,111,255);">https://vip.kingdee.com/article/585561675361592320?productLineId=1&isKnowledge=2&lang=zh-CN</font></u>](https://vip.kingdee.com/article/585561675361592320?productLineId=1&isKnowledge=2&lang=zh-CN)

<u><font style="color:rgb(30,111,255);"></font></u>

<u><font style="color:rgb(30,111,255);"></font></u>

#### **<font style="color:rgb(51,51,51);">未配置全电开票账号，请联系工作人员</font>**
![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223225013-cfaca830-169e-4b73-bec4-a1b807054c86.png)

<font style="color:rgb(51,51,51);">答：</font>

<font style="color:rgb(51,51,51);">1</font><font style="color:rgb(51,51,51);">，检查是否有做过数电升级以及在金蝶发票云公众号上配置客户的电子税局账号</font>

<font style="color:rgb(51,51,51);">2，检查金税连接设置，所设置的发票云参数是否是用的企业授权（不要用租户授权），同时检查业务组织与设置的企业名称 是否一致。</font>

<font style="color:rgb(51,51,51);"></font>

<font style="color:rgb(51,51,51);"></font>

#### **<font style="color:rgb(51,51,51);">税局系统返回：您当前无可用发票代码号码</font>****<font style="color:rgb(51,51,51);">,</font>****<font style="color:rgb(51,51,51);">请联系主管税务机关申领</font>****<font style="color:rgb(51,51,51);">或者未将对象引用设置到对象的实例</font>**
<font style="color:rgb(51,51,51);">答：</font>

<font style="color:rgb(51,51,51);">星空：大概率是错点了业务操作菜单下的按钮</font><font style="color:rgb(51,51,51);">，如需要开具数电发票，需要点电子发票开具</font><font style="color:rgb(51,51,51);">那个选项。</font>

<font style="color:rgb(51,51,51);">其它：如果要开具数电纸票，需要先向税务机关申领。</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223264073-3b8694a1-05e1-43f6-b57c-76fe0dc80f08.png)

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223267835-33fadd94-563a-43c5-ab1c-e9b22ea422c9.png)





#### **<font style="color:rgb(51,51,51);">星空</font>****<font style="color:rgb(51,51,51);">7.5</font>****<font style="color:rgb(51,51,51);">版本，销售发票上点了金税开票按钮，没有点电子发票开具按钮，导致生成的数电发票没有显示开票地址链接，如何处理？</font>**
<font style="color:rgb(51,51,51);">答：登录商家平台（</font><font style="color:rgb(51,51,51);">https://www.kdfpy.com</font><font style="color:rgb(51,51,51);">）账号是激活产品时使用的手机号，如找不到也可以通过客服在内部运营平台上查找租户管理员。 注意登录 后，右上角的公司要切换到对应的公司。可以批量操作下载等，导出</font><font style="color:rgb(51,51,51);">excel</font><font style="color:rgb(51,51,51);">里包含有发票的下载链接，也可以直接重发发票到邮箱 。</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223434773-891e0334-8e36-4d7f-b293-6377390ab453.png)





#### **<font style="color:rgb(51,51,51);">请求链接上面的clientId不正确，请联系工作人员</font>**
<font style="color:rgb(51,51,51);">答：环境要相应对</font>

<font style="color:rgb(51,51,51);">目前发票云正在完善授权信息的校验，之前部分信息配置错误但仍能正常使用，排查步骤：</font>

<font style="color:rgb(51,51,51);">1</font><font style="color:rgb(51,51,51);">、检查</font><font style="color:rgb(51,51,51);">clientid</font><font style="color:rgb(51,51,51);">、</font><font style="color:rgb(51,51,51);">clientSecret</font><font style="color:rgb(51,51,51);">、</font><font style="color:rgb(51,51,51);">encrypeKey</font><font style="color:rgb(51,51,51);">参数与该税号是否匹配</font>

<font style="color:rgb(51,51,51);">2</font><font style="color:rgb(51,51,51);">、检查</font><font style="color:rgb(51,51,51);">“</font><font style="color:rgb(51,51,51);">开票地址</font><font style="color:rgb(51,51,51);">”</font><font style="color:rgb(51,51,51);">长链接中的</font><font style="color:rgb(51,51,51);">clientid</font><font style="color:rgb(51,51,51);">是否为该税号的</font>

<font style="color:rgb(51,51,51);">3</font><font style="color:rgb(51,51,51);">、</font><font style="color:rgb(51,51,51);">clientid</font><font style="color:rgb(51,51,51);">可通过订单激活邮件中查询，注意</font><font style="color:rgb(51,51,51);">clientid</font><font style="color:rgb(51,51,51);">为非</font><font style="color:rgb(51,51,51);">“TN_”</font><font style="color:rgb(51,51,51);">开头的，此</font><font style="color:rgb(51,51,51);">clientid</font><font style="color:rgb(51,51,51);">为租户</font><font style="color:rgb(51,51,51);">ID</font><font style="color:rgb(51,51,51);">，请使用对应的企业授权</font>

<font style="color:rgb(51,51,51);">4</font><font style="color:rgb(51,51,51);">、检查长链接格式是否正确，注意</font><font style="color:rgb(51,51,51);">“clientId”</font><font style="color:rgb(51,51,51);">中的</font><font style="color:rgb(51,51,51);">“Id”</font><font style="color:rgb(51,51,51);">第一个字母为大写，如为</font><font style="color:rgb(51,51,51);">“clientid”</font><font style="color:rgb(51,51,51);">请修正为</font><font style="color:rgb(51,51,51);">“clientId”</font>

<font style="color:rgb(51,51,51);">5</font><font style="color:rgb(51,51,51);">、如以上信息都检查无误，可在长链接后面加上</font><font style="color:rgb(51,51,51);">“&request_path=”</font><font style="color:rgb(51,51,51);">，用于兼容部分版本，如：</font><font style="color:rgb(51,51,51);">“https://api.piaozone.com/bill-websocket/v3/invoicewebsocket/push?taxNo=914400000000000001&clientId=enky3VkdMZixrxXXXXXX&request_path=”</font>

<font style="color:rgb(51,51,51);"></font>

<font style="color:rgb(51,51,51);">正式和测试环境的长链接</font>

<font style="color:rgb(51,51,51);">https://api.piaozone.com/bill-websocket/v3/invoicewebsocket/push?taxNo=91370725575490266A&clientId=5pIlaZnl2obuAxtlaVWg&debugOpenInvoice=1</font>

<font style="color:rgb(51,51,51);"></font>

<font style="color:rgb(51,51,51);">https://api-dev.piaozone.com/test/bill-websocket/v3/invoicewebsocket/push?taxNo=91370725575490266A&clientId=5pIlaZnl2obuAxtlaVWg&debugOpenInvoice=1</font>

<font style="color:rgb(51,51,51);"></font>

<font style="color:rgb(51,51,51);"></font>

#### **<font style="color:rgb(51,51,51);">星空企业版如何开具0%税率发票或者零税率发票</font>**
<font style="color:rgb(51,51,51);">答：</font><font style="color:rgb(51,51,51);">0%</font><font style="color:rgb(51,51,51);">，零税率与免税发票有差差异，可参考：</font>

<font style="color:rgb(51,51,51);">怎么设置单据取零税率</font>

[<u><font style="color:rgb(30,111,255);">https://vip.kingdee.com/knowledge/375811460641218816?productLineId=1&isKnowledge=2&lang=zh-CN</font></u>](https://vip.kingdee.com/knowledge/375811460641218816?productLineId=1&isKnowledge=2&lang=zh-CN)

<font style="color:rgb(51,51,51);">单据录入时，如何录入税率为</font><font style="color:rgb(51,51,51);">0</font><font style="color:rgb(51,51,51);">（税率为</font><font style="color:rgb(51,51,51);">0</font><font style="color:rgb(51,51,51);">与税率为空）</font>

[<u><font style="color:rgb(30,111,255);">https://vip.kingdee.com/article/292606896286817024?get_from=article-id&lang=zh-CN&productLineId=1</font></u>](https://vip.kingdee.com/article/292606896286817024?get_from=article-id&lang=zh-CN&productLineId=1)

<font style="color:rgb(51,51,51);">根据不同的客户设置不同的物料税率</font>

[<u><font style="color:rgb(30,111,255);">https://vip.kingdee.com/article/113725224494610944?productLineId=1&lang=zh-CN</font></u>](https://vip.kingdee.com/article/113725224494610944?productLineId=1&lang=zh-CN)

<u><font style="color:rgb(30,111,255);"></font></u>

<u><font style="color:rgb(30,111,255);"></font></u>

<u><font style="color:rgb(30,111,255);"></font></u>

#### **<font style="color:rgb(51,51,51);">新增星空零售扫码开票的门店信息时，公众号标志要怎么设置？</font>**
<font style="color:rgb(51,51,51);">答：</font><font style="color:rgb(51,51,51);">新增星空零售</font><font style="color:rgb(51,51,51);">pos</font><font style="color:rgb(51,51,51);">开票的门店信息时，公众号标志需要选择</font><font style="color:rgb(51,51,51);">“</font><font style="color:rgb(51,51,51);">直营</font><font style="color:rgb(51,51,51);">”</font>

<font style="color:rgb(51,51,51);">后续大家新增数据的时候注意一下</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223640619-6e466635-5d26-403a-9730-dfad657e6c3e.png)

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223645643-d6e5e262-9c87-4290-ad59-52b3989a19ad.png)





#### **<font style="color:rgb(51,51,51);">星空企业版：金税开票单存在明细行的金额乘以税率的值与税额的误差</font>****<font style="color:rgb(51,51,51);">  </font>****<font style="color:rgb(51,51,51);">于</font>****<font style="color:rgb(51,51,51);">0.0600000000</font>****<font style="color:rgb(51,51,51);">，具体数据为：项目名称</font>****<font style="color:rgb(51,51,51);">XXXXX</font>**
<font style="color:rgb(51,51,51);">答：</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223832849-edb4a6d5-866a-4581-b336-84dd86363c14.png)

<font style="color:rgb(51,51,51);">此应为星空企业版金蝶开票单的提示信息，提示可能有误，建议提KSM工单反馈给星空处理，</font>

