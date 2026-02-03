| **文档编号** | **适用产品版本** | **使用范围** | **更新内容** | **创建/更新时间** | **责任人** |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **v25.0.01** | **/** | **公开** | 创建 | **2025-10-10** | **欧浩斌** |


# 文档说明
本文档适用于nginx的ssl证书替换操作，证书替换将重启（热加载）web服务，可能导致短暂的服务中断（约1-3秒）。请在业务低峰期执行。如操作后服务异常，请立即使用哦高备份的旧证书文件按照相同流程进行回滚。

# 准备工作
+ 获取新证书文件：准备好新的证书文件（一般为 .pem 或 .crt 文件）和私钥文件（ .key 文件）。
+ 确认目标服务器： 确认所有需要更换证书的应用服务器。如有负载均衡，需逐台操作，并建议在负载均衡器上先将该节点置为维护模式。
+ 上传文件：将新证书文件（例如 new.domain.pem） 和新私钥文件（例如 new.domain.key） 上传至服务器的 /opt 目录。

# 定位证书路径
nginx配置文件通常位于 /usr/local/nginx/conf/conf.d/ 目录下，以 .conf 结尾。请根据实际项目找到对应的配置文件，例如，配置文件为： /usr/local/nginx/conf/conf.d/ierp.conf

在配置文件中，定位 ssl_certificate 和 ssl_certificate_key 指令，以确定当前证书和密钥的精确路径。示例：

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1760061025942-905d264a-dcbb-4ee0-ae69-a2794c68fae1.png)

请记录下你的实际路径：

+ 当前证书路径：
+ 当前密钥路径：

# 替换操作流程
## 备份旧证书（至关重要！）
```shell
#!/bin/bash
#进入证书目录
cd /usr/local/nginx/ssl/

#备份证书和密钥，使用 .bak 后缀并添加操作日期，避免覆盖和混淆
cp gdlkjt.cn_cert_chain.pem gdlkjt.cn_cert_chain.pem.bak.$(date +%Y%m%d)
cp gdlkjt.cn_key.key gdlkjt.cn_key.key.bak.$(date +%Y%m%d)
```

## 部署新证书
将准备好的新证书文件复制到指定位置，并覆盖旧文件。

```shell
#!/bin/bash
#将 /opt 目录下的新证书文件复制并重命名为配置中指定的文件名
cp /opt/new_domain.pem /usr/local/nginx/ssl/gdlkjt.cn_cert_chain.pem
cp /opt/new_domain.key /usr/local/nginx/ssl/gdlkjt.cn_key.key
```

## 设置正确权限
确保私钥文件权限严格，防止未授权访问。

```shell
#!/bin/bash
chmod 600 /usr/loca/nginx/ssl/gdlkjt.cn_key.key
```

# 验证与加载
严禁直接加载！必须经过验证流程。

+ 语法测试： 执行如下命令，检查nginx配置语法是否正确。

```shell
#!/bin/bash
/usr/local/nginx/sbin/nginx -t 

#预期结果：显示 syntax is ok  和   test is successful
```

+ 重载服务：语法测试通过后，进行热加载，是新证书生效。

```shell
#!/bin/bash
/usr/local/nginx/sbin/nginx -s reload
```

+ 验证证书： 通过以下方式确认新证书已生效。

**方式一：命令行**

```shell
#!/bin/bash
echo | openssl s_client -servername YOUR_DOMAIN -connect YOUR_DOMAIN:443 2>/dev/null | openssl x509 -noout -dates

#YOUR_DOMAIN 替换为实际域名，端口替换为实际端口。 检查命令输出中的 notAfter日期，确认是否为新证书的有效期。
```

**方式二：浏览器**

使用浏览器访问服务地址，点击地址栏锁图标，检查证书有效期和详细信息。

# 回滚预案
若证书更换后，服务异常，立即使用备份文件回滚。

```shell
#!/bin/bash
#回滚证书文件
cp /usr/local/nginx/ssl/gdlkjt.cn.cert.chain.pem.bak.$(date +%Y%m%d) /usr/local/nginx/ssl/gdlkjt.cn.cert.chain.pem
cp /usr/local/nginx/ssl/gdlkjt.cn.key.key.bak.$(date +%Y%m%d) /usr/local/nginx/ssl/gdlkjt.cn.key.key

#重新加载配置
/usr/local/nginx/sbin/nginx -t && /usr/local/nginx/sbin/nginx -s reload
```















