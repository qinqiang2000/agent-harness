

**文档说明：**

       该文档主要记录收票配置问题、收票操作报错。每一个FAQ分问题、方案两部分内容。若为咨询类问题，可转至一问一答查看[https://jdpiaozone.yuque.com/nbklz3/tadboa/kn41k126kfdt01pd?singleDoc#NsLS](https://jdpiaozone.yuque.com/nbklz3/tadboa/kn41k126kfdt01pd?singleDoc#NsLS) 《收票》





#### <font style="color:rgb(0, 0, 0);">需启动发票智慧管家客户端</font>
<font style="color:rgb(38, 38, 38);">【问题】：</font><font style="color:rgb(51,51,51);">关键要素同步的时候提示需要启动发票智慧管家客户端</font>

<font style="color:rgb(38, 38, 38);">【方案】：</font>

          路径：开发平台 - 参数配置单据 

          操作：预览-列表，搜索参数“websocket_config_name”是否配置name值，<font style="color:rgb(0, 0, 0);">配了 name 用本地客户端。</font>





#### <font style="color:rgb(0, 0, 0);">获取token异常</font>
<font style="color:rgb(38, 38, 38);">【问题】：</font><font style="color:rgb(51,51,51);">星瀚收票助手，手机上传弹出二维码时报错“获取token异常”，手机扫描后，推送单据报错”未关联单据“</font>

<font style="color:rgb(38, 38, 38);">【方案】：</font>

          路径：开发平台 - 参数配置单据 

          操作：开发平台-rim_config-预览，发票助手-环境【改成生产或者测试，对应环境即可】



#### 自动签收
<font style="color:rgb(38, 38, 38);">【问题】：进项发票怎么配置为自动签收</font>

<font style="color:rgb(38, 38, 38);">【方案】：</font>

<font style="color:rgb(0, 0, 0);">用户上传：看rim_config，einvoice_auto_sign这个配置开启就是默认自动签收</font>

<font style="color:rgb(0, 0, 0);">税局下载：看系统参数：tax_file_auto_sign， 这个开启就会自动签收</font>

![](https://cdn.nlark.com/yuque/0/2024/png/39256605/1728545765809-b1f8589a-a600-4c5a-821d-f93f8602ec06.png)![](https://cdn.nlark.com/yuque/0/2024/png/39256605/1728545775209-1a6c4069-69e2-44a0-974c-26b4e67c738a.png)![](https://cdn.nlark.com/yuque/0/2024/png/39256605/1728545782286-c9baeb9c-5446-4126-939b-76bd1905997b.png)







#### 查看发票
<font style="color:rgb(38, 38, 38);">【问题】：如何修改【查看发票】的标题</font>

<font style="color:rgb(38, 38, 38);">【方案】：</font>

<font style="color:rgb(0, 0, 0);">开发平台，扩展 rim_view_invoice，改名称</font>![](https://cdn.nlark.com/yuque/0/2025/png/39256605/1739181465519-9bd8a86a-933b-489c-97a9-ac5aa2ae515f.png)

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764151296819-3d3f3f17-4a79-4770-966a-84535e20fb0c.png)







#### 星瀚发票助手菜单提示说明
<font style="color:rgb(38, 38, 38);">【问题】：如何修改</font><font style="color:rgb(0, 0, 0);">星瀚发票助手各菜单的提示说明文字</font>

<font style="color:rgb(38, 38, 38);">【方案】：</font>

**<font style="color:rgb(0, 0, 0);">开发平台 搜索 参数配置单据 预览列表 </font>**

<font style="color:rgb(0, 0, 0);">rim_fpzs	rim_fpzs_operate_upload </font><font style="color:#DF2A3F;">提示</font><font style="color:rgb(0, 0, 0);"> </font>

<font style="color:rgb(0, 0, 0);">rim_fpzs	rim_fpzs_operate_qrcode </font><font style="color:#DF2A3F;">提示</font>

<font style="color:rgb(0, 0, 0);">rim_fpzs	rim_fpzs_operate_enter </font><font style="color:#DF2A3F;">提示</font>

![](https://cdn.nlark.com/yuque/0/2025/png/39256605/1741772093150-af107c98-1398-43ab-9e34-5977ea6e571f.png?x-oss-process=image%2Fformat%2Cwebp)







#### 发票助手-个人票夹列表默认展示条数
<font style="color:rgb(38, 38, 38);">【问题】：如何修改发票助手个人票夹展示默认展示条数</font>

![](https://cdn.nlark.com/yuque/0/2025/png/39256605/1742972849378-8a21aab4-1924-4560-8d82-0e35a4121c63.png?x-oss-process=image%2Fformat%2Cwebp)

<font style="color:rgb(38, 38, 38);">【方案】：</font>

<font style="color:rgb(0, 0, 0);">     开发平台搜索rim_fpzs_company_invoice 扩展，修改“分页条数”</font>![](https://cdn.nlark.com/yuque/0/2025/png/39256605/1742972872926-77e301f1-56b0-40b1-9978-308055b0c9c2.png)







#### excel导入全票池
<font style="color:rgb(38, 38, 38);">【问题】：如何关闭全票池导入excel的发票查验</font>

<font style="color:rgb(38, 38, 38);">【方案】：</font>

<font style="color:rgb(0, 0, 0);">开发平台-参数配置单据-预览列表</font>

+ <font style="color:rgb(0, 0, 0);">配置项类型：rim_config</font>
+ <font style="color:rgb(0, 0, 0);">配置项key：rim_config_need_check</font>
+ <font style="color:rgb(0, 0, 0);">配置项值：0</font>







#### 发票同步勾选
<font style="color:rgb(38, 38, 38);">【问题】：如何将异步勾选改为同步勾选</font>

<font style="color:rgb(38, 38, 38);">【方案】：</font>

<font style="color:rgb(0, 0, 0);">开发平台-参数配置单据-预览列表</font>

+ <font style="color:rgb(0, 0, 0);">配置项类型：rim_config</font>
+ <font style="color:rgb(0, 0, 0);">配置项key：rpa_select_syn</font>
+ <font style="color:rgb(0, 0, 0);">配置项值：1</font>

<font style="color:rgb(0, 0, 0);">说明：除1外，其他值均为异步</font>

<font style="color:rgb(0, 0, 0);"></font>

<font style="color:rgb(0, 0, 0);">异步下载税局发票</font>

<font style="color:rgb(38, 38, 38);">【问题】：如何将税局下票设为异步下载</font>

<font style="color:rgb(38, 38, 38);">【方案】：</font>

<font style="color:rgb(0, 0, 0);">开发平台-参数配置单据-预览列表，</font><font style="color:rgb(0, 0, 0);">新增 </font>

<font style="color:rgb(0, 0, 0);">rim_down_async,</font>

<font style="color:rgb(0, 0, 0);">taxnos,</font>

<font style="color:rgb(0, 0, 0);">企业税号,</font>

<font style="color:rgb(0, 0, 0);">启异步下载的税号【多个税号用英文逗号分隔】</font>

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







#### **<font style="color:rgb(51,51,51);">手动激活全量发票同步任务</font>**
<font style="color:rgb(51,51,51);">1、</font><font style="color:rgb(51,51,51);"> </font><font style="color:rgb(51,51,51);">任务：</font><font style="color:rgb(51,51,51);">rim_tableHeadApplyTask_SKDP_S</font><font style="color:rgb(51,51,51);">税局发票同步申请缓存</font><font style="color:rgb(51,51,51);">  </font><font style="color:rgb(51,51,51);">默认执行时间是一天读取两次</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223929564-46c6eda7-8a2d-4286-8200-8333d4cfbfd0.png)

<font style="color:rgb(51,51,51);">这个任务先读取缓存配置</font><font style="color:rgb(51,51,51);">是不是需要下载发票</font><font style="color:rgb(51,51,51);">这里面包括了默认是下载前三天的发票、以及上次失败的发票，不建议更改（不包括当天，税局不允许）</font>

<font style="color:rgb(51,51,51);">2、</font><font style="color:rgb(51,51,51);"> </font><font style="color:rgb(51,51,51);">任务：</font><font style="color:rgb(51,51,51);">rim_invoiceDownloadApply_SKDP_S  rimkey</font><font style="color:rgb(51,51,51);">：</font><font style="color:rgb(51,51,51);">newetax_inputout_days  </font><font style="color:rgb(51,51,51);">如果配置了就当天执行，没有配置就取日期是否模</font><font style="color:rgb(51,51,51);">3</font><font style="color:rgb(51,51,51);">余数，如果是</font><font style="color:rgb(51,51,51);">3</font><font style="color:rgb(51,51,51);">的就执行），执行时间默认是一个小时一次；</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223934045-b8716132-e51a-47f8-86f8-8fd6dbe55bd7.png)

<font style="color:rgb(51,51,51);">3</font><font style="color:rgb(51,51,51);">、执行完这两部发票云</font><font style="color:rgb(51,51,51);">rpa</font><font style="color:rgb(51,51,51);">会根据申请下载进项发票数据，星瀚生成生成</font><font style="color:rgb(51,51,51);">rim_down_log</font><font style="color:rgb(51,51,51);">下载日志</font>

<font style="color:rgb(51,51,51);">4、</font><font style="color:rgb(51,51,51);"> </font><font style="color:rgb(51,51,51);">任务：</font><font style="color:rgb(51,51,51);">rim_inputdowload_SKDJ_S</font><font style="color:rgb(51,51,51);">进销项发票下载</font><font style="color:rgb(51,51,51);">  </font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223939087-d43628ef-5716-4aae-9727-c7b67b0271e4.png)

<font style="color:rgb(51,51,51);">从RPA拿下载好的数据到星瀚，默认十分钟一次</font>

<font style="color:rgb(51,51,51);"></font>

<font style="color:rgb(51,51,51);"></font>

#### **<font style="color:rgb(51,51,51);">全量同步改开始时间</font>**
<font style="color:rgb(51,51,51);">1.</font><font style="color:rgb(51,51,51);">预览</font><font style="color:rgb(51,51,51);">rim_fpzs_test</font><font style="color:rgb(51,51,51);">这个页面，</font>

<font style="color:rgb(51,51,51);">2.</font><font style="color:rgb(51,51,51);">左下角方法名输入</font><font style="color:rgb(51,51,51);">updateDownInit</font><font style="color:rgb(51,51,51);">，右下角参数：</font>

<font style="color:rgb(51,51,51);">{"startTime":"2022-01-01","numbers":"全量发票数据同步设置的方案编码"}</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223948908-c1de708f-2b2a-4019-baff-07cfac28202c.png)

<font style="color:rgb(51,51,51);">3.</font><font style="color:rgb(51,51,51);">点击上面的</font><font style="color:rgb(51,51,51);">’</font><font style="color:rgb(51,51,51);">操作</font><font style="color:rgb(51,51,51);">‘</font><font style="color:rgb(51,51,51);">按钮；</font>

<font style="color:rgb(51,51,51);">4. 刷新这个列表看下这样就行了；</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223958723-c2391adb-c789-42a6-bdde-5c2d2610674b.png)

<font style="color:rgb(51,51,51);">注意不要去改任何配置了，等调度计划处理！禁止点这个配置进去保存！！！</font>

<font style="color:rgb(51,51,51);"></font>

<font style="color:rgb(51,51,51);"></font>

#### **<font style="color:rgb(51,51,51);">发票预览模糊问题</font>**
<font style="color:rgb(51,51,51);">发票预览查看，移动端查看，发票模糊问题</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223980951-43178545-df73-4b5f-9207-0fadf5fb4163.png)

<font style="color:rgb(51,51,51);">【解答】：</font>

<font style="color:rgb(51,51,51);">确认客户是否有切换成国产服务器</font>

<font style="color:rgb(51,51,51);">以此客户为例，近期因信创原因切换为：</font><font style="color:rgb(0,0,0);background-color:rgb(255,255,255);">ARM架构：鲲鹏920：海光7380处理器</font>

**<font style="color:rgb(51,51,51);">核心原因：</font>**<font style="color:rgb(51,51,51);">客户切换为了国产服务器，目前查在PDF查看不兼容问题，研发经几个月多方努力，暂未能完美解决该问题，</font>

**<font style="color:rgb(51,51,51);">处理：</font>**<font style="color:rgb(51,51,51);">确保版本可以在rim_config下见到配置项“电票默认展示pdf”，将其改为是，改为是后，电脑端的展示问题将解决，移动端仍可能模糊，但可以有变动出现查看原文件的按钮，通过 查看原文件变通处理。</font>

<font style="color:rgb(51,51,51);">如看不到该配置项，请检查版本，</font><font style="color:rgb(51,51,51);">6.0</font><font style="color:rgb(51,51,51);">早期版本看不到该配置项，如是私有化部署项目，需要导出版本信息后，让星瀚研发同事出具升级私包。</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223996854-f0c84379-6f17-47f4-9807-c9a5b8cd84e2.png)





#### **<font style="color:rgb(51,51,51);">增值税电子普通发票和数电普票，当且仅当满足以下</font>****<font style="color:rgb(51,51,51);">5</font>****<font style="color:rgb(51,51,51);">个条件则发票为可抵扣</font>**
<font style="color:rgb(51,51,51);">1</font><font style="color:rgb(51,51,51);">、蓝字发票</font>

<font style="color:rgb(51,51,51);">2</font><font style="color:rgb(51,51,51);">、非区块链发票</font>

<font style="color:rgb(51,51,51);">3</font><font style="color:rgb(51,51,51);">、发票状态非红冲、作废、异常、失控、全额红冲</font>

<font style="color:rgb(51,51,51);">4</font><font style="color:rgb(51,51,51);">、开票时间</font><font style="color:rgb(51,51,51);">2019-4-1</font><font style="color:rgb(51,51,51);">之后</font>

<font style="color:rgb(51,51,51);">5</font><font style="color:rgb(51,51,51);">、（所有商品明细中至少一行商品明细含简称</font><font style="color:rgb(51,51,51);">“</font>_<font style="color:rgb(51,51,51);">运输服务</font>_<font style="color:rgb(51,51,51);">”</font><font style="color:rgb(51,51,51);">）且（该行明细星号外的商品名不含</font><font style="color:rgb(51,51,51);">“</font><font style="color:rgb(51,51,51);">货物</font><font style="color:rgb(51,51,51);">”“</font><font style="color:rgb(51,51,51);">港澳台</font><font style="color:rgb(51,51,51);">”</font><font style="color:rgb(51,51,51);">或</font><font style="color:rgb(51,51,51);">“</font><font style="color:rgb(51,51,51);">国际</font><font style="color:rgb(51,51,51);">”</font><font style="color:rgb(51,51,51);">字样）</font>

<font style="color:rgb(51,51,51);">6、 特定业务类型为农产品收购、资产农产品销售</font>

<font style="color:rgb(51,51,51);"></font>

<font style="color:rgb(51,51,51);"></font>

#### **<font style="color:rgb(51,51,51);">预勾选上，税款所属期的可选择范围是由什么条件决定？</font>**
<font style="color:rgb(51,51,51);">A：不是权限；是因为如果是从通道那里查询到的税期，那么就是不可编辑的，只展示当前税期；如果查询不到税期，那么就是展示当前月，并且可编辑。</font>

<font style="color:rgb(51,51,51);"></font>

<font style="color:rgb(51,51,51);"></font>

#### **<font style="color:rgb(51,51,51);">当前公司没有可一键报销的流程</font>**
<font style="color:rgb(51,51,51);">A：移动端的一个功能，非发票云功能，非发票云提示。建议联系单据费报方处理。</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764224028833-7bff4d0d-2116-458e-b597-b83b6ad34b6a.png)





#### AWS代开发票，备注取代销售方关闭方法
AWS代开发票，备注取代销售方关闭方法（合规性校验可能会提示个人发票）：

找到该客户clientId提单给运维，内容写“企业关闭代开发票功能” ，执行“redis key ‘filterNotNeedProxyClient’ value 后面拼接clientId”







#### 全票池上显示两个凭证号的原因：
A：单据方调用发票云两次，因此保存有多个凭证号，根据之前 产品与单据方的约定，发票云会将单据方调用 的全部予以显示（如只需要显示一个需要单据方主动调用删除前一个）。

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225020381-7ecf71e6-4967-4644-9275-61dd559affd8.png)



#### 发票导入单据成功，等待单据处理中
【方案】：

第一，在群里看看是不是大面积瘫痪，推送系统没有歧视没有例外，要么全瘫，要么全正常，不会针对客户例外。第二，排除自身原因，找到ERP（一般是二开、新接容易出现此种情况）的研发，告诉他们接到推送数据之后，务必按文档所述，自行关闭页面。需要日志可在ELK 搜 “推送” + 发票信息任意内容，截图即可

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225020728-56235666-3639-439b-8d92-fc966fa89697.png)

#### 


#### 费用核算-发票类型（发票云）上添加自定义规则时，可选条件是哪一方维护的？
![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225021061-e483ba85-7ec9-4b42-b261-8818fc62bc84.png)

A：这个页面的基础资料是费报维护的。特定业务类型等是2024年底让费报添加的。





#### 税局用票操作日志列表怎么进入？
A：开发平台搜索rim_select_log

点开后，切换到列表，再点预览即可

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225022812-116337f9-bb0a-4530-8a08-a045cbfe34f3.png)



#### 发票操作日志列表怎么进入？
A：开发平台搜索rim_invoice_log

点开后，切换到列表，再点预览即可

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225023074-afa17999-5ad5-4359-9021-e1731fdab7ba.png)





#### 识别失败，识别接口返回:【1130】  税号:9113100MADNM7JF4N,不在租户:366045674239990272 范围内 
A：通过后台运营平台查询该税号 ，一般会发现盖税号 为禁用状态或者是不存在，

或者税号 确实不在提示的租户范围内，应在客户现场调整配置的税号参数 





#### 同步勾选参数配置单据
路径：开发平台，搜索“参数配置单据”，列表-预览，新增参数：

类型：rim_config

key：rpa_select_syn

值：1





#### 查验失败暂不支持此类发票查验
A：检查该企业是否申请过测试授权或者购买生产授权并激活分配 ，再到运营平台售后操作企业权益处通过税号查看是否有查验的权限 ，需要为能查验才可。识别修改为睿琪，查验方式修改为长软。

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225025684-d6726776-fd7f-4b1d-acdf-96957e1693ea.png)



#### 进项全票池下载发票文件的文件名称支持自定义吗？
A：支持，如下配置，在公共设置-系统参数-发票云-收票管理下予以设置

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225026002-efa87e25-6201-4e5d-84f6-cd45358175c1.png)





#### 数电航空票通过收票助手上传提示：未上传源文件
A：数电票目前判断不出来是不是源文件，只是数电飞机的话对接了凭证 如果提取不到xbrl就认为不是原文件

 在基础资料-企业信息-是否凭证试点企业，关掉后重试。

另，如果上传的是数电票的图片，也会有此提示。



#### 发票助手上的企业票夹打开时默认的过滤规则是怎么样的？
A: 通过单据打开发票助手采集发票时：此处过滤显示费用核算组织采集的发票；

   通过发票签收入口采集发票：此处过滤显示右上角登录组织采集的发票。

#### 


#### 打开发票助手报错：与发票云建立连接失败！或者 基础授权信息有误，请联系管理员！或者  非法的客户ID，请联系管理员
![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225026408-b079b264-6ce4-4bae-ae56-9c77a58dab7e.png)

【方案】：

1. 检查发票云授权配置
2. 检查开发平台-费用全局配置，列表-预览：配置项invoicecloud.not_prod

参数与环境需要相互匹配才可以正确打开收票助手 。

即指向生产环境 时，应使用生产环境 的发票云授权参数（clientID，client_sercret等）

指向测试环境 时，应使用测试环境 的发票云授权参数（clientID，client_sercret等）







#### 星瀚收票助手移动端调整正式环境或者测试环境？
A：开发平台-rim_config-预览，发票助手-环境【改成生产或者测试，对应环境即可】。

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225027365-6c87f05d-ca67-4d8d-9597-b512e769a485.png)



#### 费用报销怎么查看生效的发票云配置是哪个？
开发平台>费用全局配置>预览列表>invoicecloud.configpattern

A：发票云配置模式，1为发票云配置（组织模式）， 2为发票云配置（集团管控模式）

[https://club.kdcloud.com/knowledge/172662699892219392?productLineId=2&isKnowledge=2&lang=zh-CN](https://club.kdcloud.com/knowledge/172662699892219392?productLineId=2&isKnowledge=2&lang=zh-CN)![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225027517-9e7644de-e642-45ac-a87d-a455442edd99.png)







#### 上传发票的时候提示发票已被单据使用,如何解除占用
A：[https://vip.kingdee.com/knowledge/360925808870649088?productLineId=1&isKnowledge=2&lang=zh-CN](https://vip.kingdee.com/knowledge/360925808870649088?productLineId=1&isKnowledge=2&lang=zh-CN)

#### 


#### 旗舰版收票助手上传pdf的页数限制能放开吗？
开发平台-->参数配置单据invsm_param_configuration，新增参数：

参数类型：rim_fpzs

key：maxpdfpage

值：自行输入，

注意：不要配太大，如果文件过大会影响识别准确率。

#### 


#### 星瀚文件操作日志-单据附件日志
A：客户端类型显示“移动端”说明客户是通过移动端上传附件，

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225031597-df044de6-9692-4d64-8ad3-8d88984f69bf.png)

#### 




#### 星瀚生成的底账图片有问题，怎么重新生成？没看到重新生成的按钮？
【方案】：开发平台，搜索“发票文件”，列表-预览

操作： 发票流水号过滤发票文件，删除pdfurl、快照url，缩略图，点击“生成快照”按钮重新生成。

select * from t_rim_invoice_file

update t_rim_invoice_file set fpdf_url = '' , fofd_url = '', fimage_url = '' , fsnapshot_url = '' where fserial_no = ''

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225032257-104311ed-2d88-41ca-9707-28325cec431b.png)





#### 地方税局网络不稳定，请稍后再试
A：一般为当地税局的查验服务异常导致 ，需要等当地税局恢复，建议隔天再重试。

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225033479-99c47283-040f-4df5-99ac-0b6c3d05828c.png)





#### 必填字段为空，请补充！
1，必要的字段未正常识别，需要手动补充完整

2，假票，可到国家税务总局全国增值税发票查验平台进行验证。

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225034058-d1949614-d45a-4a19-9ebc-2f213848130c.png)





#### 查看发票时，发票上有一个水印：非税局正式发票文件，仅供预览
A：2025年6月更新内容：因之前总有客户拿截图充当正式发票用，并咨询为什么有“底账数据”四个字。

这种预览图仅做预览发票数据使用，不应做别的用途，所以加上水印用以规避。

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225035651-2a44310e-8d1e-4bd9-9361-c59444ec4ddd.png)

#### 


#### 税号：XXXXXXX，没有开启软证书模式
A：软证书收票方式为税控时期收费下票模式，现已停用。

基础资料--企业管理--企业信息，修改收票通道为电子税局或乐企即可。

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225036123-5765be0f-5a48-4b0e-98f3-5b23dc419abc.png)



#### 星空旗舰版费用报销单上看不到导入发票的按钮？星空旗舰版看不到发票服务的菜单？
答：如看不到导入发票的按钮，检查发票云配置有无完成，如看不到发票服务的菜单 ，联系星空运维王秀珩，一般在下单激活后<font style="color:#000000;">1-2个工作日处理部署（晚六点部署）。未部署前 </font>

不会有相关菜单。



发票云配置:https://vip.kingdee.com/link/s/ZhklR

并且注意组织要与单据单头费用承担公司一致。

发票云配置项上，发票云三个配置参数可从发票云的产品激活成功后的授权邮件中获取，注意要使用企业授权，勿使用租户授权。

其对应关系分别是：

发票云授权标识：填发票云的ClientID

客户端标识：填发票云的ClientSecret

接入标识：填发票云的EncryptKey(EncryKey)

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225036412-aa5cf750-3431-4500-acc6-af6188c84a00.png)



#### 使用发票智慧管家进行收票后怎么切换回发票无忧助手进行收票或者客户端收票小程序未启用，请启用。
答：可参考：

[https://vip.kingdee.com/knowledge/463871659284518400?productLineId=1&isKnowledge=2&lang=zh-CN](https://vip.kingdee.com/knowledge/463871659284518400?productLineId=1&isKnowledge=2&lang=zh-CN)



#### 公有云数据的任务怎么强制停止？
答：开发平台-参数配置单据，

在列表界面选中右上方的搜索按钮，搜索“rim_config ”，看列表中是否有“rim_config_sync_his”参数，如没有，点击【新增】

配置项类型：rim_config

配置项key：rim_config_sync_his

配置项值：1 

如需要终止任务，就把配置项值设为0

公有云数据迁移可参考：

[https://jdpiaozone.yuque.com/nbklz3/ga8nuk/zp79w1rx0qq5c34e](https://jdpiaozone.yuque.com/nbklz3/ga8nuk/zp79w1rx0qq5c34e)



#### 勾选中的任务处理失败或者处理中，想强制停止怎么处理？
答：收集税号及批次号反馈研发处理（比如金帆，具体待定）

黄潮鑫：通道提供作废接口对接，可以用批次号，批量停止待处理的批次（正在操作税局、已经成功完成、或明确失败终止的批次不能作废）



#### 保存发票关系失败，null，请联系管理员
答：

1，检查配置的参数是否正确

2，检查发票云运营后台，客户所订购的产品有无正确激活，租户名下是否有对应企业等。

3，重点检查第三方应用上设置的密码，一般建议全部重置后，更新到发票云回调配置上。

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225036701-5ebfd4be-12e2-4b26-9e1a-1d72795e58f5.png)

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225036963-b4a60f21-628a-4c89-a7fd-de7e364d413c.png)



#### 邮箱取票，收邮件的固定邮箱地址是多少
答：

正式环境：fp@piaozone.cn

演示环境：fp_test@piaozone.cn

sit环境：[fp_sit@piaozone.cn](fp_sit@piaozone.cn)



#### 超过企业设置的报销期限
答：检查收票管理--基础设置--合规性校验配置

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225037205-aeb3f447-6da0-48f5-bd20-c355c6e667b0.png)



#### 发票云收票不可抵扣的判断标准是什么？改签费能否抵扣？
答：改签费是可抵扣的，发票云是根据业务类型=退并且税率=0.06 判断不可抵扣的，改签费的税率是0.09

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225037434-fba55c2c-6080-491f-b32d-a2c697517893.png)

[https://shenzhen.chinatax.gov.cn/sztax/zcwj/rdwd/202503/b519be84cda24bf7b35719efd741675b.shtml](https://shenzhen.chinatax.gov.cn/sztax/zcwj/rdwd/202503/b519be84cda24bf7b35719efd741675b.shtml)



#### 二开的单据打开发票助手提示：没有发票采集相关权限，请联系管理员
答：解决方案是否可行待定

排查方向：

看下二开的单据，打开发票助手传过来的单据类型是什么，这个单据类型在我们收票助手配置里面有没有对应的配置。



#### 星空企业版收票时能否合并明细收票
答：可参考：

[https://vip.kingdee.com/knowledge/603223036720012800?productLineId=1&isKnowledge=2&lang=zh-CN](https://vip.kingdee.com/knowledge/603223036720012800?productLineId=1&isKnowledge=2&lang=zh-CN)

主要对应以下三种合并规则：

1、不合并：一条发票明细生成一行费用明细；

2、单张发票合并：对单张发票按照税率、费用项目、差旅费类型、是否实名一致的合并生成费用明细

1. 跨发票合并：按照发票类型、差旅类型、费用项目、税率、是否实名一致的合并生成费用明细（针对当次导入的发票满足条件的合并生成明细）



#### er_stdconfig, invoicecloud.configpattern
发票云配置模式，1为发票云配置（组织模式）， 2为发票云配置（集团管控模式）

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225037744-4750964a-7e58-4451-9bea-aaf3a9f88ec0.png)



####  无预勾选权限，请配置发票主表的提交预勾选权限
答：检查下该账号的授权分配 



#### 未上传源文件
答：

1，可能原因：基础资料-企业信息-电子凭证会计数据试点企业  这个改为否 数电票就不提示了

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225038135-9f8f1dbc-231c-4c2d-8639-5b798b677ac7.png)



#### 发票数据不能为空
答：2025年7月份已知BUG，待排期修复，发票反馈给研发临时处理。

表现为导入后不可见发票，浏览器或者后台日志见此提示。

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225038438-49423963-484b-44de-8b1a-b23cae7ff414.png)



#### 预勾选没法选择数电火车票
答：确认是否私有化部署，如是，确认下版本，2024年11月之后的版本才支持。





#### 文件服务器多实例，请联系管理员调整文件流配置
![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225038766-69213086-0d4b-49c3-8cce-2353f3f3b61c.png)

A：rim_config配置下，识别查验方式下的文件服务器多实例改为是，等一两个小时待同步后再重试。





#### 应付单的收票信息页签的选择发票菜单项是灰色
答：是否启用应付暂估？ 启用了则在财务应付单上面收票







#### 匿名用户操作错误：非法参数
1，检查收票助手配置的移动端配置是不是云之家的码用微信扫码了，如果需要微信扫码，需要到收票助手配置处予以修改。

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225039908-30ece790-a9c8-4a82-afff-e9bcfe775844.png)

2，如果码类型与扫码方式均正确，进一步排查

因是权限问题，收票助手配置改成按权限后，再扫码会提示没有采集发票和采集附件的权限，请先配置好权限后再进行采集

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225040197-65897441-e926-4496-a92b-44f7d37e475b.png)

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225040424-c034e590-3129-4f25-be07-565c22326594.png)

收票助手配置移动端改成微信不会有这个问题





#### 发票校验流量包计费规则
(1)按发票张数统计计算票量，同时使用识别和查验服务，每张扣1个票量，只使用识别或只使用查验每张扣减0.5个票量；

(2)同一个租户下不同企业重复采集同一张发票不重复扣减票量；

(3)再次采集历史被删除发票不重复扣减票量；

(4)税局下载的发票，通过查验补齐发票数据不扣减票量；非税局下载的发票调用查验服务补全数据，正常扣减票量；

(5)税局下载的发票，再次通过收票助手采集，调用识别服务正常扣减票量；

(6)采集发票合规性校验不通过没入票池的发票不扣减票量；

(7)采集发票调用识别、查验服务失败，不扣减票量；

1. 删除已识别、查验的发票，已经扣减的票量正常累计计算。





#### 进项全票池和进项明细列表上同一张发票所属核算组织不一致
A：升级最新版本，历史数据需要在更新包后重新导入才可修复 。





#### 已下载表头待查验
答：数据同步日志查询和发票同步台账列表都可能会显示该处理状态。

该任务无法暂停。

处理：

1，点同步账号列表的批量处理，处理状态才能变更为处理完成（未自动查验）。批量处理触发调度计划：rim_InputInvoiceDownDealTask_SKDP_S

这个调度开启没，这里的批量处理，实际上就是执行这个调度的逻辑，实现的就是将台账表的数据，同步到全票池。

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225043180-97f99af4-eac3-49a1-b1f4-2214616b11c1.png)

可同步检查该调度计划的执行日志，看有无异常。



随便用一张目前没处理的发票，去查一下这个临时表t_rim_down_input，条件是fserial_no  like '%发票号码%'

看一下其中的fhandle_num，处理次数看看

2，检查全量数据同步下载设置那添加任务时，进项状态更新的发票是否查验入库的设置

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225043379-cc8e5cfc-150a-4023-aa5f-b7f595dd3e51.png)

3，rim_config页面检查关键要素下载是否查验入库的设置项

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225043899-8de8f8bf-08e6-444e-86ad-b9494192dfda.png)





#### 如何配置企业微信、钉钉及云之家对接发票云
参考

[https://vip.kingdee.com/knowledge/378215482416984576?productLineId=2&isKnowledge=2&lang=zh-CN](https://vip.kingdee.com/knowledge/378215482416984576?productLineId=2&isKnowledge=2&lang=zh-CN)







#### 未对接发票云，不允许操作
原因：【发票云配置】新增时，当前登录用户的所属组织需与配置新增的组织不一致，不生效。

方案：删除配置后，退出界面。切换用户的当前所属组织，重新打开界面配置【发票云配置】



#### 保存发票关系失败，发票XXXXXX使用金额超出剩余可用金额0元，保存失败
发票被其它单据占用，全票池查询发票绑定单据信息，





#### 当前税号无文档智能取数服务权益，请联系销售处理
发票云支持开具海外形式发票，但需要购买发票云的【文档智能取数服务流量包】才能识别和处理这些海外发票。标准版的收票助手不支持此功能

该产品目前没有在kbc上架，需要走一下第三方采购协议。



#### 未关联单据，请从单据上【选择发票】，扫描二维码
发票云小程序除个人票夹外，需要先通过单据点击或者扫二维码绑定单据后，扫描的发票才能推送到单据上。





#### 星瀚上识别查验的Monitor日志查询方案
A：可确认匹配的合规性规则是哪一个

先搜索：识别查验file

取最新traceid，再用Traceid查询

可获取具体使用哪条规则，对应哪个单据类型等

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225044324-444e1598-fcc6-455d-8b70-7515d8f69a48.png)

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225044750-c36d40d1-8164-4fe2-ae8a-989272ddd1fc.png)

对比的结果关键字：compare_scriptEngine

compare_scriptEngine:true&&(false&&false)

注：查询规则性校验规则数据库表：

税务库

select * from t_rim_verify







#### 请核对用户信息或重新调用登录接口
向税局请求进行数据下载时，登录失效导致 。

1，该企业账号可能对应管理多家企业，同一时间只进行其中一个企业的下载操作。

2，账号多端登录

处理建议：误在别的渠道或者别的企业有登录动作。

电子税局账号登录认证的问题



#### 该应用查验权限过期
收票的权限过期 ，应进行续费或者重新申请延期测试环境的测试授权，

[https://jdpiaozone.yuque.com/nbklz3/tadboa/kob4eqaeil3fed2l?singleDoc#](https://jdpiaozone.yuque.com/nbklz3/tadboa/kob4eqaeil3fed2l?singleDoc#) 《2.1申请测试环境》



#### 小规模纳税人不支持抵扣类勾选数据下载，可根据企业在税局的信息，在星瀚发票云企业基础资料修改。
A：企业性质如果是小规模纳税人，则不支持下载抵扣类勾选数据。如果不是小规模，可到基础资料-企业信息处修改企业为一般纳税人





#### 进项全票池列表上发票信息上的状态标签图标怎么做个性化设置？
答：扩展发票主表rim_invoice,  把相关不要的标签的图标叉掉

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225045133-d91599b5-a30a-40ac-8547-51954ccbc371.png)

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225045578-06e6d2ed-fff3-40bc-8124-0728c110e312.png)





#### 无收票特性分组许可，请联系管理员
可能原因：

基础服务云-许可管理-许可分配用户，点下同步许可，同步成功后再试

可以到许可分组明细查询 里看下有无开收票的分组许可

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225045760-66c21f17-e0fe-48f8-9ce1-63bf505d61de.png)



#### ISV环境的发票云配置保存报：功能异常
![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1764225045985-43a29d7b-db42-44c5-8629-8d0cb497a710.png)

需要通过找研发及运维刷SQL解决，自营公有云没办法操作费用模块的发票云配置，刷完sql就可以保存了

INSERT INTO t_er_stdconfig (fid, fvalue, fdesc, fkey) VALUES(1180243559601724416, 'true', '是否集成星瀚发票云，true: 启用，false: 不启用，默认值：false', 'invoicecloud.invoicecloudxh');

需要提供测试环境地址：[https://cosmic-sandbox.piaozone.com/XXXXX](https://cosmic-sandbox.piaozone.com/XXXXX)





#### **<font style="color:rgb(51,51,51);">发票查询，点击下载时弹出的文件默认格式怎么设置？</font>**
![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223849159-37a9933a-afc8-40dc-a8a5-58e4bbadfb1f.png)

<font style="color:rgb(51,51,51);">【方案】: 开发平台-发票云-开票管理，扩展sim_choose_invoice_type 表单；</font>

<font style="color:rgb(51,51,51);">选中发票类型，设置对应的缺省值为PDF或者OFD等，缺省值可多选。</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223860763-beee4617-44cb-450b-9df8-d04062bb6c20.png)

<font style="color:rgb(51,51,51);">在进项全票池做相关下载时，也可根据类似方法设置默认格式，对应的表单为rim_filetype_selected</font>









