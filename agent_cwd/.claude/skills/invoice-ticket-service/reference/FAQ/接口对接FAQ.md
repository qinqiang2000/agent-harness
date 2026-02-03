【文档说明】：

     本常见问题文档按照产品划分归类，目前收集了标准版开收票接口的常见问题。可通过ctrl+F打开查找页面，输入问题关键字快速查找。



### <font style="color:#117CEE;">一、标准版开票</font>
#### 1.1 接口对接时如何开具测试数电票，虚拟开票，模拟开票？
答：调用接口时需要添加一个参数debugOpenInvoice=1

如：[https://api.piaozone.com/bill-websocket/v3/invoicewebsocket/push?reqid=1xxxxxxxxxxx2&taxNo=xxxxxxxxxxxxxx&clientId=xxxxxxxxxxxxxxxxxxx&0&debugOpenInvoice=1](https://api.piaozone.com/bill-websocket/v3/invoicewebsocket/push?reqid=1xxxxxxxxxxx2&taxNo=xxxxxxxxxxxxxx&clientId=xxxxxxxxxxxxxxxxxxx&0&debugOpenInvoice=1)



https://api-dev.piaozone.com/test/bill-websocket/v3/invoicewebsocket/push?taxNo=当前企业税号&clientId=企业对应的发票云ClientId的值&paperInvoiceFlag=1&debugOpenInvoice=1

不带debugOpenInvoice=1，就会开出真票

标准版v3开票接口，测试环境可以在请求链接上面添加debugOpenInvoice=1这个参数，可以模拟开票。只支持测试环境，正式环境不支持



#### <font style="color:rgb(38, 38, 38);">1.2 未配置全电开票账号，请联系工作人员</font>
<font style="color:rgb(38, 38, 38);">这个是根据租户clientId+税号+登录账号找不到登录人信息。请排查：</font><font style="color:rgb(0, 0, 0);background-color:rgb(241, 244, 249);">  
</font><font style="color:rgb(38, 38, 38);">1、clientId是否为租户账号</font><font style="color:rgb(0, 0, 0);background-color:rgb(241, 244, 249);">  
</font><font style="color:rgb(38, 38, 38);">2、检查税号是否正确</font><font style="color:rgb(0, 0, 0);background-color:rgb(241, 244, 249);">  
</font><font style="color:rgb(38, 38, 38);">3、检查登录账号是否正确（一般是手机号）</font>



#### <font style="color:rgb(0, 0, 0);">1.3 异步开票查询： 未查询该数据</font>
1. <font style="color:rgb(0, 0, 0);">检查税号、开票流水号；</font>
2. <font style="color:rgb(0, 0, 0);">检查token；</font>
3. <font style="color:#DF2A3F;">同步开票不能用异步查询</font>

![](https://cdn.nlark.com/yuque/0/2024/png/40561605/1724913293201-76d53785-b50b-48a4-a600-d41f27b572f2.png)



### <font style="color:#117CEE;">二、标准版收票</font>
#### 2.1 AWS接口-查看分录发票
<font style="color:rgb(0, 0, 0);">1. 客户同一张单据，不同分录id获取userkey是一样的； </font>

**<font style="color:rgb(0, 0, 0);">branch_id</font>**<font style="color:rgb(0, 0, 0);">=AAA14B00-D169-45AB-9331-1FFC9F12B9E5 </font>

**<font style="color:rgb(0, 0, 0);">branch_id</font>**<font style="color:rgb(0, 0, 0);">=38A542F0-896B-42F6-AF14-BB6941B787A0 </font>**<font style="color:rgb(0, 0, 0);">userkey</font>**<font style="color:rgb(0, 0, 0);">=dda807c9e4e4b1d86b1921d0e0619e45 </font>

<font style="color:rgb(0, 0, 0);">2. 查看分录发票的时候，用这个userkey查看返回的所有分录的发票，</font>

<font style="color:rgb(0, 0, 0);">陈焕威回复：</font><font style="color:rgb(0, 0, 0);">在图像视图里面展示的是整个单据的内容，地点视图才是分录要显示的单张发票。逻辑如此，前后端代码仅几年都没有人碰过。如果客户有其他想法，提需求单吧</font>

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1741241578770-7e7802a3-fd34-43ac-bd4f-7ba2b55d1e0e.png)



**<font style="color:#DF2A3F;">EAS图像视图可以看分录发票</font>**：用这个实现的，不是分录功能。

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1741241985497-054bc140-e73f-4b30-9530-01e5413b089c.png)

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1741242020105-989040dc-ecf9-4166-9f1e-e274f6624ce1.png)



### 
