| **文档编号** | **适用产品版本** | **使用范围** | **更新内容** | **创建（修改）时间** | **责任人** |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **v25.0.01** | **7.0及以上** | **公开** | **创建** | **2025-11-19** | **欧浩斌** |


# 文档说明
本文档介绍了私有化星瀚发票云环境部署websocket的具体操作步骤。



# 部署配置要求
websocket服务器配置建议： 2c8g  100G   linux系统  jdk1.8

注：系统需要java环境，服务需要连接redis，可共用苍穹系统的redis。

部署作用： 提供消息服务，用于开票客户端和苍穹平台收发消息。



# 参数配置、运行
直接jar包运行，jar包下载地址：

[https://api-dev.piaozone.com/invoice-client/imc/websocket-1.0.jar](https://api-dev.piaozone.com/invoice-client/imc/websocket-1.0.jar)

配置文件： application.yml

### redis单机配置
![](https://cdn.nlark.com/yuque/0/2021/png/22572071/1640773494871-045ce041-688d-4443-98d7-4aeddca37357.png?x-oss-process=image%2Fformat%2Cwebp)

单机rendis复制下面文本：

```shell
server:
  port: 8155
  servlet:
    context-path: /bill-websocket

spring:
  redis:
    port: 16379
    host: 10.0.1.1
    password: Cosmic@2020
  servlet:
    multipart:
      max-file-size: 100MB
      max-request-size: 100MB
  mvc:
    async:
      request-timeout: 1000

#上传文件密码
uploadPassword: Fpy2022Kingdee&@

#组件超时等待时间(秒)
component-time-out: 200
```



### redis哨兵配置
![](https://cdn.nlark.com/yuque/0/2021/png/22572071/1640773456824-a824c371-8d01-4c9c-9957-048385bdbae4.png?x-oss-process=image%2Fformat%2Cwebp)

查看sentinel.conf文件，可以看到master的name是什么，一般部署时默认是mymaster

哨兵复制以下文本：

```shell
server:
  port: 18155
  servlet:
    context-path: /bill-websocket

spring:
  redis:
    lettuce:
      pool:
        max-idle: 10
        max-wait: 500
        max-active: 8
        min-idle: 0
    sentinel:
      master: mymaster
      nodes: 10.110.1.2:7505,10.110.1.6:7505,10.110.1.10:7505
    password: Cosmic@2020
  servlet:
    multipart:
      max-file-size: 100MB
      max-request-size: 100MB

#上传文件密码
uploadPassword: test

#组件超时等待时间(秒)
component-time-out: 200
```



# 运行命令
直接运行（不推荐，内置的jar配置文件可能不是您当前环境的）

```shell
nohup java -jar websocket-1.0.jar &
```

指定配置文件运行：

```shell
nohup java -jar websocket-1.0.jar --spring.config.location=/opt/conf/application.yml &
```

（注意：/opt/conf/application.yml 需要替换为您实际上传配置的 application.yml文件路径）



#  检测是否部署成功
### 检测进程是否运行
执行以下命令，查看进程是否存在：

```shell
ps -ef | grep websocket-1.0.jar 
```

当出现有 java -jar websocket-1.0.jar 时，则表明服务进程已经启动。如果没用，则表明进程挂了或者每没有启动。

![](https://cdn.nlark.com/yuque/0/2022/png/22572071/1660012865326-d40ea180-c10e-4fde-a746-f6251eb43737.png?x-oss-process=image%2Fformat%2Cwebp)

### 打开上传客户端，点击测试
浏览器打开部署的 http://ip:port/路径名/upload.html  （路径名对应配置的context-path，默认是 bill-websocket）

![](https://cdn.nlark.com/yuque/0/2022/png/22572071/1660012584984-110eae99-cc39-4e3a-9881-256687fda05a.png?x-oss-process=image%2Fformat%2Cwebp)

点击测试按钮，当返回 测试websocket部署成功，则部署成功。

![](https://cdn.nlark.com/yuque/0/2021/png/22572071/1640773334471-dbc2248d-2ef9-4611-bcf2-9a359907715b.png?x-oss-process=image%2Fformat%2Cwebp)

### 测试星瀚税控系统云能不能连上websocket
路径： 税控系统云——>发行管理——>系统管理——>参数配置

发票云配置——>远程地址

替换远程地址（ip port为刚刚部署的 websocket java服务的ip和port）

<font style="color:#E8323C;">http://ip:port/bill-websocket/invoicewebsocket/httpPush?name=</font>

![](https://cdn.nlark.com/yuque/0/2021/png/22572071/1639447794865-548a2605-e3fb-4f43-b34f-bff159d0e5be.png?x-oss-process=image%2Fformat%2Cwebp)

发票云连接参数修改

url：修改为生产地址，https://api.piaozone.com

clientid、clientsecret、加密key 同步修改为企业生产授权信息

![](https://cdn.nlark.com/yuque/0/2024/png/21649460/1705559777559-ee584e6e-d1a7-4f6b-8ec0-5dfa74cd0cf5.png?x-oss-process=image%2Fformat%2Cwebp)

最后，点击测试 websocket

![](https://cdn.nlark.com/yuque/0/2022/png/22572071/1661842773565-1c806fac-b320-427f-a851-3f5e11bdbaae.png?x-oss-process=image%2Fformat%2Cwebp)





