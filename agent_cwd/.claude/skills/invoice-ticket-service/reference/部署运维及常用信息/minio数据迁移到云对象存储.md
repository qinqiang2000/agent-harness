| **文档编号** | **适用产品版本** | **使用范围** | **更新内容** | **创建/更新时间** | **责任人** |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **v25.0.01** | **标准版影像** | **公开** | 创建 | **2025-11-18** | **欧浩斌** |


# 文档说明
本文档提供了将自建MinIO对象存储中的数据迁移至阿里云OSS（对象存储服务）的标准化操作流程。其核心原理同样适用于华为云OBS、亚马逊S3等其他兼容S3协议的对象存储服务。

迁移策略采用 **<font style="color:rgb(15, 17, 21);">“全量迁移 + 增量同步”</font>**<font style="color:rgb(15, 17, 21);"> </font>的方式，以确保业务数据的完整性与一致性。

# 迁移准备
在开始迁移前，请务必完成以下准备工作：

+ 资源评估：确认源MinIO集群中的总数据量及文件数量。
+ 目标环境准备：

在阿里云OSS中创建好目标存储桶（如 oss_temp, oss_pro）。

获取OSS的 Access Key (AK)、Secret Key (SK) 和 Endpoint (访问域名)。

+ 网络与权限：

确保迁移执行服务器与Minio、OSS之间的网络连通性。

确认Minio用户具备桶的读取权限，OSS的AK/SK具备桶的读写权限。

+ 业务窗口：全量迁移会占用大量源站读取带宽，强烈建议在业务低峰期执行。

#  迁移步骤
## 创建原minio环境与迁移目标oss别名
使用 `mc` (MinIO Client) 工具为源和目标配置别名，简化后续命令。

```shell
mc alias set minio_local http://127.0.0.1:9000 admin Kd@Archive2022Minio --api s3v4
#minio_local：原minio别名，可自定义
#http://127.0.0.1:9000：minio连接地址
#admin： minio用户名
#Kd@Archive2022Minio：minio密码
mc alias set oss_pro https://chengshi-oss.oss.cn-north-4.myalicloud.com:443 5UHRUNG2RLVOBQTKSQXH HxJ6Xg3Hg80LdAlOm8YwifEd12ykfpZ5ET2MWdTX 
#oss_pro：oss别名，可自定义
#https://chengshi-oss.oss.cn-north-4.myalicloud.com:443： oss连接地址
#5UHRUNG2RLVOBQTKSQXH： AK
#HxJ6Xg3Hg80LdAlOm8YwifEd12ykfpZ5ET2MWdTX：SK
```

##  启动全量迁移进程
此步骤将桶内所有数据一次性同步至目标OSS。数据量较大时，请使用 `nohup` 在后台运行。

```shell
mc mirror --remove minio_local/archive-temp oss_pro/oss_temp
#--remove： 删除目标位置中源目录中不存在的文件
#archive-temp：原minio中临时桶
#oss_temp：oss中临时桶
mc mirror --remove minio_local/archive-pro oss_pro/oss_pro
#--remove： 删除目标位置中源目录中不存在的文件
#archive-pro：原minio中正式桶
#oss_pro：oss中正式桶
```

##  启动增量迁移（实时复制）
全量迁移完成后，立即执行此步骤。通过 `--watch` 参数启动监听模式，持续同步新增或变更的文件<font style="color:rgb(15, 17, 21);">。</font>

```shell
mc mirror --watch --remove minio_local/archive-temp oss_pro/oss_temp
#--watch： 持续监控
#--remove： 删除目标位置中源目录中不存在的文件
#archive-temp：原minio中临时桶
#oss_temp：oss中临时桶
mc mirror --watch --remove minio_local/archive-pro oss_pro/oss_pro
#--watch： 持续监控
#--remove： 删除目标位置中源目录中不存在的文件
#archive-pro：原minio中正式桶
#oss_pro：oss中正式桶
```

关键点：

+ <font style="color:rgb(15, 17, 21);">此进程需要</font>**<font style="color:rgb(15, 17, 21);">持续运行</font>**<font style="color:rgb(15, 17, 21);">，建议在</font><font style="color:rgb(15, 17, 21);"> </font>`<font style="color:rgb(15, 17, 21);background-color:rgb(235, 238, 242);">screen</font>`<font style="color:rgb(15, 17, 21);"> </font><font style="color:rgb(15, 17, 21);">或</font><font style="color:rgb(15, 17, 21);"> </font>`<font style="color:rgb(15, 17, 21);background-color:rgb(235, 238, 242);">tmux</font>`<font style="color:rgb(15, 17, 21);"> </font><font style="color:rgb(15, 17, 21);">会话中启动，防止因SSH断开而终止。</font>
+ **<font style="color:rgb(15, 17, 21);">增量同步的持续时间应至少大于全量迁移所花费的时间</font>**<font style="color:rgb(15, 17, 21);">，以确保全量期间产生的所有增量数据都被捕获。</font>

# 应用切换
增量迁移一段时间后（不低于全量迁移时间），可以准备停机、切换应用连接。

##  应用停机
为保证数据的一致性，切换对象存储连接时，需要先暂停业务，避免数据写入。可通过应用启停脚本停止业务服务。

```shell
cd /安装目录/kingdee/script/
sh stop.sh
```

##  停止增量复制进程
应用停机后，不能立即停止增量复制进程，避免数据操作延迟同步；通过对比存储桶中文件数来确认迁移数据的完整性。

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764227029935-88cc7c8c-6c38-40ec-8cbb-193536cac4d1.png)

##  切换应用连接
通过修改zookeeper配置来切换对象存储的连接，修改内容如下：

<font style="color:black;background-color:#FFFFFF;">##storeType说明：1-aws、2-minio、3-obs、4-oss，</font>

<font style="color:black;background-color:#FFFFFF;">/api-archive/pri=storeType=4</font>

<font style="color:black;background-color:#FFFFFF;">/api-archive/pri=ACCESS_KEY_ID=5UHRUNG2RLVOBQTKSQXH </font>

<font style="color:black;background-color:#FFFFFF;">/api-archive/pri=SECRET_KEY_ID=HxJ6Xg3Hg80LdAlOm8YwifEd12ykfpZ5ET2MWdTX </font>

<font style="color:black;background-color:#FFFFFF;">/api-archive/pri=ERP_ARCHIVE_BUCKET_NAME=chengshi-oss</font>

<font style="color:black;background-color:#FFFFFF;">/api-archive/pri=SCAN_BUCKET_NAME=chengshi-oss</font>

<font style="color:black;background-color:#FFFFFF;">/api-archive/pri=endPoint=chengshi-oss.oss.cn-north-4.myalicloud.com </font>

<font style="color:black;background-color:#FFFFFF;">/api-archive-scan/pri=storeType=4</font>

<font style="color:black;background-color:#FFFFFF;">/api-archive-scan/pri=ACCESS_KEY_ID=5UHRUNG2RLVOBQTKSQXH </font>

<font style="color:black;background-color:#FFFFFF;">/api-archive-scan/pri=SECRET_KEY_ID=HxJ6Xg3Hg80LdAlOm8YwifEd12ykfpZ5ET2MWdTX </font>

<font style="color:black;background-color:#FFFFFF;">/api-archive-scan/pri=ERP_ARCHIVE_BUCKET_NAME=chengshi-oss </font>

<font style="color:black;background-color:#FFFFFF;">/api-archive-scan/pri=SCAN_BUCKET_NAME=chengshi-oss </font>

<font style="color:black;background-color:#FFFFFF;">/api-archive-scan/pri=endPoint=chengshi-oss.oss.cn-north-4.myalicloud.com </font>

<font style="color:black;background-color:#FFFFFF;">/api-archive-invoice/pri=BUCKET_NAME=chengshi-oss</font>

## <font style="color:black;background-color:#FFFFFF;"> 启动应用服务</font>
```shell
cd /安装目录/kingdee/script/
sh start.sh
```

#  测试
+  **<font style="color:rgb(15, 17, 21);">历史数据验证</font>**<font style="color:rgb(15, 17, 21);">：在业务系统中随机抽查一批历史影像文件，确认能够正常打开和查看。</font>
+ **<font style="color:rgb(15, 17, 21);"> 新数据上传验证</font>**<font style="color:rgb(15, 17, 21);">：执行一次新的影像上传操作，确认文件能成功存入OSS，并能被正确访问。</font>

# <font style="color:rgb(15, 17, 21);">迁移后收尾</font>
+ **<font style="color:rgb(15, 17, 21);">监控与观察</font>**<font style="color:rgb(15, 17, 21);">：切换后，建议对OSS的流量、请求次数和存储容量进行为期几天的监控。</font>
+ **<font style="color:rgb(15, 17, 21);">源端资源处理</font>**<font style="color:rgb(15, 17, 21);">：确认业务在新环境下稳定运行一段时间（如一周）后，可按计划对原MinIO集群中的数据进行归档或下线处理。</font>

