| **文档编号** | **适用产品版本** | **使用范围** | **更新内容** | **创建（修改）时间** | **责任人** |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **v25.0.01** | **标准版发票云** | **公开** | **创建** | **2025-11-19** | **兰茜凤** |


# 环境准备
1. **EAS版本**：8.0版本、8.2版本、8.5版及以上**<font style="color:#E8323C;">（建议购买86版本）</font>**
2. **配套所购EAS模块要求**：85版及以上【应收模块+EAS开票管理模块（税务模块）】，此外80、82版本<font style="color:rgb(0, 0, 0);">需要购买85税务+同等数量的82/80 bos许可</font>
3. **补丁**：8.0和8.2版本需要更新【开票管理】/【收票管理】与【税务管理】的最新全局补丁PTM及开收票补丁 、8.5及以上版本更新对应模块最新补丁号。

对应版本最新税务补丁号可参考ESA补丁帖子进行相关说明查看（具体可联系税务模块老师进行确认）

[EAS Cloud 税务管理知识合辑](https://vip.kingdee.com/knowledge/specialDetail/249195983434059776?category=249267138123885568&id=212586865499843328)

<details class="lake-collapse"><summary id="ub0b3e35a"><strong><span class="ne-text">补丁获取方式：</span></strong></summary><p id="u4117fd6f" class="ne-p" style="text-align: justify"><span class="ne-text">WEB门户——金蝶专区——云客服——客户工单处理，进入KSM提单系统。</span></p><p id="u73930a5a" class="ne-p" style="text-align: justify"><img src="https://cdn.nlark.com/yuque/0/2021/png/2185333/1623822829314-e5a0de84-9ad8-4cba-9631-2d1f65bb69a2.png" width="593" id="iRPMo" class="ne-image"></p><p id="u1141be0d" class="ne-p" style="text-align: justify"><img src="https://cdn.nlark.com/yuque/0/2021/png/2185333/1623822856657-f85d93b6-68ed-413f-9ce5-7617628af53a.png" width="374" id="HsLSE" class="ne-image"></p><p id="uf5b0b469" class="ne-p" style="text-align: justify"><span class="ne-text">进入系统后，在右上角【补丁下载】模块搜索对应补丁。</span></p><p id="ub70732d0" class="ne-p" style="text-align: justify"><img src="https://cdn.nlark.com/yuque/0/2021/png/2185333/1623822921090-952c5f6c-df97-4305-9f75-2ceb40a66120.png" width="472" id="TqpmG" class="ne-image"></p><p id="ua58b0cdc" class="ne-p" style="text-align: justify"><img src="https://cdn.nlark.com/yuque/0/2021/png/2185333/1623822788620-99352d6e-0e6a-4b73-8228-4681886ed912.png" width="533" id="Zck9t" class="ne-image"></p><p id="ufe7b38ae" class="ne-p" style="text-align: justify"><span class="ne-text">✨</span><span class="ne-text">建议下载【开票管理】/【收票管理】和【税务管理】的最新版全局补丁。如对补丁功能有所疑问，请联系EAS同事沟通。</span></p><p id="u0cedbb57" class="ne-p" style="text-align: justify"><br></p><p id="u5a4bdcab" class="ne-p" style="text-align: justify"><strong><span class="ne-text">温馨提示：</span></strong></p><p id="u437ff074" class="ne-p" style="text-align: justify"><span class="ne-text">✨</span><span class="ne-text">使用EAS的金税对接功能之后，开票的信息（例如购货方信息、商品税收分类编码等）以EAS维护的为准</span></p></details>
# 一、发票云产品激活
**<font style="color:#DF2A3F;">是否必需：是</font>**

 [产品激活及参数获取](https://jdpiaozone.yuque.com/nbklz3/tadboa/sf09ttllvsbpkyae)

# 二、ERP配置
## 开票组织税务资料维护
**<font style="color:#DF2A3F;">是否必需：是</font>**

**<font style="color:#117CEE;">GUI：企业建模—组织架构—组织单元—财务实体组织；</font>**

新增/复制新增EAS维护开票组织税务资料，GUI财务实体组织下，维护**<font style="background-color:#FBDE28;">开票企业名称、税号、地址、电话、银行名称及账号</font>**<font style="color:rgb(51,51,51);">（这些信息会带到发票的</font><font style="color:rgb(36,39,41);">销售方</font><font style="color:rgb(51,51,51);">信息栏）</font>，<font style="color:red;">注意企业名称和税号与电子税局上的保持一致</font>；

![](https://cdn.nlark.com/yuque/0/2021/png/21649460/1627456580745-45de504e-1802-4ba1-8ea2-523aa3ba26a4.png)![](https://cdn.nlark.com/yuque/0/2021/png/21649460/1627456307688-3b885f74-8f85-4609-a150-b38ba498c3d5.png)

**<font style="color:#117CEE;">Web：企业建模—组织架构—组织单元—财务实体组织；</font>**

![](https://cdn.nlark.com/yuque/0/2020/png/1580060/1599117425481-8cefde58-9138-41f9-943f-f218228e81a3.png)

## 进入税务管理模块，金税互联设置
**<font style="color:#DF2A3F;">是否必需：是</font>**

**<font style="color:#117CEE;">GUI：税务管理模—增值税发票管理—基础设置—金税互联设置；</font>**

![](https://cdn.nlark.com/yuque/0/2020/png/1580060/1599117425721-e587d952-c200-4a86-b735-2a3aaf48abed.png)

![](https://cdn.nlark.com/yuque/0/2023/png/12881570/1673252274753-a9b9df53-d70c-4f87-85d2-5859b09b0abf.png?x-oss-process=image%2Fformat%2Cwebp)



+ **http地址：**https://api.piaozone.com/bill-websocket/v3/invoicewebsocket/push?taxNo=<font style="color:#DF2A3F;">当前企业税号</font>&clientId=<font style="color:#DF2A3F;">企业对应的发票云ClientId的值</font>&paperInvoiceFlag=1

<details class="lake-collapse"><summary id="uf027a7c2"><span class="ne-text">数电纸票的HTTP地址</span></summary><p id="ub428031a" class="ne-p"><span class="ne-text">【数电纸质专票默认开具（三联），数电纸质普票默认开具（二联）】</span></p><p id="u064b8dd4" class="ne-p"><strong><span class="ne-text" style="color: #117CEE">联次配置说明：</span></strong></p><p id="u3437eeb0" class="ne-p" style="margin-left: 2em"><span class="ne-text"> 1.数电纸质专票支持（三联和六联）、普票支持（二联和五联）</span></p><p id="ub455afc6" class="ne-p" style="margin-left: 2em"><span class="ne-text"> 2.默认情况下（【数电纸质专票默认开具（三联）、数电纸质普票默认开具（二联）】）</span></p><p id="ub11c8798" class="ne-p" style="margin-left: 2em"><span class="ne-text"> </span><span class="ne-text">3.如果需要开具 其他联次类型</span><span class="ne-text">，需要再增加</span><a href="https://api.piaozone.com/bill-websocket/v3/invoicewebsocket/push?taxNo=91310101785875340J&amp;clientId=kiB0ifLgw3aVhPCxWDGd&amp;paperInvoiceFlag=1&amp;invoiceCopyType=5" data-href="https://api.piaozone.com/bill-websocket/v3/invoicewebsocket/push?taxNo=91310101785875340J&amp;clientId=kiB0ifLgw3aVhPCxWDGd&amp;paperInvoiceFlag=1&amp;invoiceCopyType=5" target="_blank" class="ne-link"><span class="ne-text">&amp;invoiceCopyType</span></a><span class="ne-text">参数，具体规则如下：</span></p><p id="u5a624380" class="ne-p" style="margin-left: 6em"><span class="ne-text">普票 五联、专票 六联：</span><a href="https://api.piaozone.com/bill-websocket/v3/invoicewebsocket/push?taxNo=91310101785875340J&amp;clientId=kiB0ifLgw3aVhPCxWDGd&amp;paperInvoiceFlag=1&amp;invoiceCopyType=5" data-href="https://api.piaozone.com/bill-websocket/v3/invoicewebsocket/push?taxNo=91310101785875340J&amp;clientId=kiB0ifLgw3aVhPCxWDGd&amp;paperInvoiceFlag=1&amp;invoiceCopyType=5" target="_blank" class="ne-link"><span class="ne-text">&amp;invoiceCopyType</span></a><span class="ne-text">=56</span></p><p id="uc61810d8" class="ne-p" style="margin-left: 6em"><span class="ne-text">普票 五联、专票 三联</span><span class="ne-text">：</span><a href="https://api.piaozone.com/bill-websocket/v3/invoicewebsocket/push?taxNo=91310101785875340J&amp;clientId=kiB0ifLgw3aVhPCxWDGd&amp;paperInvoiceFlag=1&amp;invoiceCopyType=5" data-href="https://api.piaozone.com/bill-websocket/v3/invoicewebsocket/push?taxNo=91310101785875340J&amp;clientId=kiB0ifLgw3aVhPCxWDGd&amp;paperInvoiceFlag=1&amp;invoiceCopyType=5" target="_blank" class="ne-link"><span class="ne-text">&amp;invoiceCopyType</span></a><span class="ne-text">=53</span></p><p id="u8e221c22" class="ne-p" style="margin-left: 6em"><span class="ne-text">普票 二联、专票 六联</span><span class="ne-text">：</span><a href="https://api.piaozone.com/bill-websocket/v3/invoicewebsocket/push?taxNo=91310101785875340J&amp;clientId=kiB0ifLgw3aVhPCxWDGd&amp;paperInvoiceFlag=1&amp;invoiceCopyType=5" data-href="https://api.piaozone.com/bill-websocket/v3/invoicewebsocket/push?taxNo=91310101785875340J&amp;clientId=kiB0ifLgw3aVhPCxWDGd&amp;paperInvoiceFlag=1&amp;invoiceCopyType=5" target="_blank" class="ne-link"><span class="ne-text">&amp;invoiceCopyType</span></a><span class="ne-text">=26</span></p><p id="ua303a7f1" class="ne-p" style="margin-left: 6em"><span class="ne-text">普票 二联、专票 三联：</span><a href="https://api.piaozone.com/bill-websocket/v3/invoicewebsocket/push?taxNo=91310101785875340J&amp;clientId=kiB0ifLgw3aVhPCxWDGd&amp;paperInvoiceFlag=1&amp;invoiceCopyType=5" data-href="https://api.piaozone.com/bill-websocket/v3/invoicewebsocket/push?taxNo=91310101785875340J&amp;clientId=kiB0ifLgw3aVhPCxWDGd&amp;paperInvoiceFlag=1&amp;invoiceCopyType=5" target="_blank" class="ne-link"><span class="ne-text">&amp;invoiceCopyType</span></a><span class="ne-text">=23</span></p><p id="u179b6df3" class="ne-p" style="margin-left: 2em"><span class="ne-text"></span></p><p id="u3daa2551" class="ne-p" style="margin-left: 2em"><span class="ne-text">示例：（客户需要开具数电纸质发票，专票为三联，普票为五联）</span></p><p id="ue3ea4f5f" class="ne-p" style="margin-left: 2em"><span class="ne-text">https://api.piaozone.com/bill-websocket/v3/invoicewebsocket/push?taxNo=91310*********&amp;clientId=kiB0if***********</span><span class="ne-text" style="color: #DF2A3F">&amp;paperInvoiceFlag=1&amp;invoiceCopyType=53</span></p><p id="ub67c3538" class="ne-p" style="margin-left: 2em"><span class="ne-text">组装成功，填入开票地址中。</span></p><p id="u0543501b" class="ne-p"><br></p></details>
+ **发票云ID、发票云密钥、加密密钥：**从发票云授权邮件中获取（<font style="color:#DF2A3F;">请使用税号对应的企业授权，不要用租户授权！！</font>）



**<font style="color:red;">Web</font>****<font style="color:red;">：</font>****税务管理模—增值税发票管理—基础设置—金税互联设置**

![](https://cdn.nlark.com/yuque/0/2020/png/1580060/1599117426122-be619204-0ec0-44c7-a7c8-c229bb90e1ed.png)

# 三、用户操作手册
## 开票组织的客户税务资料维护
[【客商开票资料】操作手册](https://vip.kingdee.com/link/s/ZTnoH)

## 开票商品名称维护
[开票—商品名称匹配详解](https://vip.kingdee.com/link/s/ZTnUs)

## 开票参数设置
[【开票参数配置】操作手册](https://vip.kingdee.com/link/s/ZTnCB)

## 开票分组合并规则设置
[【合并规则】操作手册](https://vip.kingdee.com/link/s/ZTnNZ)

## 开票单开票
[【开票申请单（增值税）新增】操作手册](https://vip.kingdee.com/link/s/ZTnIU)

[【开票单（增值税）新增】操作手册](https://vip.kingdee.com/link/s/ZTn9W)

[【开票数据分析表】操作手册](https://vip.kingdee.com/link/s/ZTn9I)

[实操详解-开票基础功能](https://vip.kingdee.com/link/s/ZTnEU)







