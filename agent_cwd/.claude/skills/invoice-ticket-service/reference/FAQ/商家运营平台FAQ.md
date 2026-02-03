

#### <font style="color:rgb(0, 0, 0);">单张开票没有“数电平台”</font>
<font style="color:rgb(0, 0, 0);">联系发票云服务人员，在EOP新增税号对应的金税连接设置</font>

<font style="color:rgb(0, 0, 0);">（1）托管类型选“全电RPA”</font>

<font style="color:rgb(0, 0, 0);">（2）开票地址：https://api.piaozone.com/bill-websocket/v2/invoicewebsocket/push</font>![](https://cdn.nlark.com/yuque/0/2025/png/39256605/1745910407533-3718c7f8-bebb-4b56-8a05-e962459c2f43.png?x-oss-process=image%2Fformat%2Cwebp)





#### 开票查询-发票同步没有数电平台，无法同步数电发票
![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1763623290445-4eb0a85f-8d63-4f85-a47e-a44c4654956f.png)

商户运营平台不支持同步数电发票，可调接口查询非发票云开具的销项发票：[https://open-standard.piaozone.com/api-144977121](https://open-standard.piaozone.com/api-144977121)







#### 下载发票时无法选择下载文件类型
![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1763623372355-82d8ade1-5deb-462e-8376-0ebe130e28b0.png)

解决方案：

1. 检查单张开票是否可以选择数电平台，若不能，参照手册问题1处理；
2. 如果可以选择仍然下载不到其他文件类型，切换右上角的组织为销方组织即可。





# 
#### 4，商家运营平台下载电票时有三种类型可以选择？
答：

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225061933-b5cfa7ce-8bcb-4499-b941-71750b809144.png)

需要在发票云星瀚运维平台上的金税设置管理上修改托管类型为全电RPA（9）

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225062142-31229a46-51b0-4aaa-a60c-37ed97df431a.png)



#### 5，登录商户运营平台时选择租户后提示：当前租户下无可用企业，请先激活
![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225062479-c90401d9-77ad-4e8c-98a7-2b8ffe0ef3d9.png)

答：

1，检查该租户在运营平台的状态是否为启用状态

2，检查该租户下是否有关联的企业

3，检查租户下的管理员手机号是否存在或者与当前登录的手机号是否一致（如中途更换过云之家账号的手机号，则租户管理员下的手机号要删除后再新增）









# 
