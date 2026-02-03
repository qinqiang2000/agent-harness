

文档说明：

       该文档主要记录开票配置问题、开票操作报错。每一个FAQ分问题、方案两部分内容。若为咨询类问题，可转至一问一答查看[https://jdpiaozone.yuque.com/nbklz3/tadboa/wnuovgaug11y9znl?singleDoc#Aw9E](https://jdpiaozone.yuque.com/nbklz3/tadboa/wnuovgaug11y9znl?singleDoc#Aw9E) 《开票》







#### 全额红冲后，销售发票单重新下推
【问题】：全额红冲后，如何允许撤回开票申请单，使销售发票单可以修改

<font style="color:rgb(38, 38, 38);">【方案】：</font><font style="color:rgb(0, 0, 0);">特殊配置开放控制，可撤回申请单，撤回后原已开发票与上游关联解除，</font>

<font style="color:rgb(0, 0, 0);">路径：开发平台→发票云→系统管理→云应用参数配置→参数配置单据，点预览 </font>

<font style="color:rgb(0, 0, 0);">{配置项类型：sim_original_bill}</font>

<font style="color:rgb(0, 0, 0);">{配置项值：bill_withdraw} </font>

<font style="color:rgb(0, 0, 0);">配置项值：1，</font>

<font style="color:rgb(0, 0, 0);">配置为1时，撤回不校验是否已开票，</font>**<font style="color:#DF2A3F;">撤回后删除该参数</font>**

**<font style="color:#DF2A3F;"></font>**

**<font style="color:#DF2A3F;"></font>**

#### <font style="color:rgb(0, 0, 0);">明细商品名称不能为空</font>
【问题】：开票报错：明细商品名称不能为空

<font style="color:rgb(38, 38, 38);">【方案】：</font>

<font style="color:rgb(0, 0, 0);">goodsName商品名称取的“开票名称”字段，销售发票单显示该字段检查是否为空。</font>

[**https://vip.kingdee.com/knowledge/specialDetail/533276336497132544?category=675710227580478464&id=675709504096098560&type=Knowledge&productLineId=40&lang=zh-CN**](https://vip.kingdee.com/knowledge/specialDetail/533276336497132544?category=675710227580478464&id=675709504096098560&type=Knowledge&productLineId=40&lang=zh-CN)

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1758592372673-b1d69c93-ccad-4ba9-943d-f5956a07b93e.png)

#### 


#### 预览开票的开票人
【问题】：预览开票的开票人取得哪里？

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1760952012391-02bfd80c-f7a4-412a-84a0-0102dcad35c1.png?x-oss-process=image%2Fformat%2Cwebp)

<font style="color:rgb(38, 38, 38);">【方案】：</font>

取得发票回调配置的接口授权用户；

若配置了开票人策略，则取策略值。

![](https://cdn.nlark.com/yuque/0/2025/png/40561605/1760952004431-20fef755-b8c5-44be-bc1e-d45b924cbd3a.png)





#### 税收分类编码不一致
【问题】：销售发票单的税收分类编码是A，下推开票申请单税收分类编码是B

<font style="color:rgb(38, 38, 38);">【方案】：</font><font style="color:rgb(0, 0, 0);">检查下税收分类编码基础资料，看编码的名称与简称是不是错的</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764208317127-096a54f6-ed64-4ece-b057-2f186b6f767d.png)





#### **<font style="color:rgb(51,51,51);">星空旗舰版发票查询报：没有维护实体属性中的表名，不能预览</font>**
<font style="color:rgb(51,51,51);">答：该问题为ERP平台的问题，要找ERP端处理</font>

<font style="color:rgb(51,51,51);"></font>

<font style="color:rgb(51,51,51);"></font>

#### **<font style="color:rgb(51,51,51);">星空旗舰版物料的批量修改中如何增加字段？</font>**
<font style="color:rgb(51,51,51);">答：</font>[<u><font style="color:rgb(30,111,255);">https://vip.kingdee.com/knowledge/580808444500610048?lang=zh-CN&location=pageHelp&productLineId=40&productId=93&isKnowledge=2</font></u>](https://vip.kingdee.com/knowledge/580808444500610048?lang=zh-CN&location=pageHelp&productLineId=40&productId=93&isKnowledge=2)

#### 


#### **<font style="color:rgb(51,51,51);">星空旗舰版如何批量维护物料上的税收分类编码</font>**
<font style="color:rgb(51,51,51);">答：</font>

<font style="color:rgb(51,51,51);">物料标准的导入导出模板暂不支持，要到基础资料-公共设置-导入导出模板上修改导入 的字段才能批量导入导出税收分类编码相关字段。</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223347834-9f4a7b26-5ff4-4e69-a5c1-3ef6d9b17c7b.png)

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223352003-87d6f725-0305-48dd-8ea6-7f3201d95359.png)

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764223356909-2056a304-1fa5-4411-98e5-502d00b54f8c.png)





#### **<font style="color:rgb(51,51,51);">星空旗舰版，应收单下推销售发票单-开票后，在销售发票单上税控红冲了蓝票，想再修改应收单该如何处理？</font>**
<font style="color:rgb(51,51,51);">答：</font>

<font style="color:rgb(51,51,51);">有下游关联发票，上游数据理论上不可以修改了。如果要修改数据，应收那边的建议是去做负数单，后用新的正确单据重新下推开票。如存在特殊场景已开票仍需反审核销售发票单，可通过特殊配置开放控制，可撤回申请单，撤回后原已开发票与上游关联解除，配置路径如下：开发平台</font><font style="color:rgb(51,51,51);">→</font><font style="color:rgb(51,51,51);">发票云</font><font style="color:rgb(51,51,51);">→</font><font style="color:rgb(51,51,51);">系统管理</font><font style="color:rgb(51,51,51);">→</font><font style="color:rgb(51,51,51);">云应用参数配置</font><font style="color:rgb(51,51,51);">→</font><font style="color:rgb(51,51,51);">参数配置单据，点预览</font>

<font style="color:rgb(51,51,51);">{</font><font style="color:rgb(51,51,51);">配置项类型：</font><font style="color:rgb(51,51,51);">sim_original_bill}    </font>

<font style="color:rgb(51,51,51);">{</font><font style="color:rgb(51,51,51);">配置项值：</font><font style="color:rgb(51,51,51);">bill_withdraw}</font>

<font style="color:rgb(51,51,51);">配置项值：1，配置为1时，撤回不校验是否已开票</font>

<font style="color:rgb(51,51,51);"></font>

<font style="color:rgb(51,51,51);"></font>

#### **<font style="color:rgb(51,51,51);">星空旗舰版，方案配置，点新增方案时，报堆栈异常：</font>****<font style="color:rgb(51,51,51);">For Input string :"null"</font>**
<font style="color:rgb(51,51,51);">答：确认是否私有化环境，产研增修复过的BUG，需获取版本信息JSON文件后给研发，提升私包升级版本。</font>

<font style="color:rgb(51,51,51);"></font>

<font style="color:rgb(51,51,51);"></font>

#### **<font style="color:rgb(51,51,51);">星空企业版是否支持开具特定业务类型的数电发票</font>**
<font style="color:rgb(51,51,51);">答：部分版本支持，</font><font style="color:rgb(51,51,51);">本次版本新增支持开具下述</font><font style="color:rgb(51,51,51);">6</font><font style="color:rgb(51,51,51);">类特定业务类型发票：成品油发票 、建筑服务发票、货物运输服务发票、不动产销售服务发票、不动产租赁服务发票 、卷烟发票</font>

<font style="color:rgb(51,51,51);">发布版本：</font><font style="color:rgb(51,51,51);">V8.1</font>

<font style="color:rgb(51,51,51);">上线日期：</font><font style="color:rgb(51,51,51);">2023-09-21</font>

<font style="color:rgb(51,51,51);">补丁号：</font><font style="color:rgb(51,51,51);">PT-151002</font>

<font style="color:rgb(51,51,51);">详见星空发版说明：</font>

[<u><font style="color:rgb(30,111,255);">https://vip.kingdee.com/knowledge/490245269964084992?productLineId=1&isKnowledge=2&lang=zh-CN</font></u>](https://vip.kingdee.com/knowledge/490245269964084992?productLineId=1&isKnowledge=2&lang=zh-CN)

<font style="color:rgb(51,51,51);">由于税局平台下述规定，针对特定类型下禁止填写的要求，同时基于不干预原有销售发票单据的输入考虑，星空系统在销售发票下推金税开票单时会将对应开票明细字段清空处理。具体规则如下：</font>

<font style="color:rgb(51,51,51);">单位：特定业务类型为建筑服务、不动产销售服务、不动产经营租赁为禁止填写</font>

<font style="color:rgb(51,51,51);">数量：特定业务类型为为建筑服务为禁止填写</font>

<font style="color:rgb(51,51,51);">单价：特定业务类型为为建筑服务为禁止填写</font>

<font style="color:rgb(51,51,51);"></font>

