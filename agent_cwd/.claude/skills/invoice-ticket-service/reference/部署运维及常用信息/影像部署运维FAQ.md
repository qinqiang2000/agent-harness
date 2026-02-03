#  mysql安装报错
![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764205285305-d10fa71c-033e-4001-bbe2-5bf3bebbb9c1.png)

缺少依赖，手动安装一下依赖库后再执行安装：

libssl.so.10、libcrypto.so.10、libtinfo.so.5、libncurses.so.5



# 从节点后台服务容器一直重启
检查zk连接配置是否正确，jar包中的BOOT-INF/classes/bootstrap.properties

zk连接地址一般为主节点IP

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764205465741-44c5f2ac-33cb-464a-932a-75100e09f877.png)



# 影像上传报错（The specified bucket does not exist）
![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764205581032-0d6cb42f-537c-493f-8221-5c6c16352514.png)

对象存储没有创建存储桶，给minio服务创建存储桶即可

mc alias set minio_local [http://127.0.0.1:9000](http://127.0.0.1:9000) admin Kd@Archive2022Minio --api s3v4

mc mb minio_local/archive-temp 

mc mb minio_local/archive-pro



# 发票识别失败
![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764205806044-16ac8ab1-9f5c-4720-9724-34afc0307d6f.png)

在影像服务的info日志中搜索关键字："区分"、"开始查验"

区分：查看base-ai的部署情况

开始查验：查看权益是否过期



# SELECT list is not in GROUP BY clause
![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1764206196415-cba65f2e-8d81-40cf-9e75-dde8082e80bf.png)

全局sql模式不能设置 only_full_group_by，可以执行下列sql语句：

```sql
set @@global.sql_mode='STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION';
```

<font style="color:black;background-color:#FFFFFF;"></font>

<font style="color:black;background-color:#FFFFFF;"></font>

