| **文档编号** | **适用产品版本** | **使用范围** | **更新内容** | **创建（修改）时间** | **责任人** |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **v25.0.01** | **7.0及以上** | **公开** | **创建** | **2025-09-28** | **欧浩斌** |


# 文档说明
本文档主要介绍了客户内网环境无法直接访问公网发票云场景下，如何使用nginx代理实现内网服务器访问公网发票云。

# 部署要求
1. 如使用步骤二部署包，要求操作系统：CentOS7.X、麒麟v10x86、Redhat7.X
2. 保证代理机器可以直接访问发票云地址
3. 内网机器可以直接访问代理服务器
4. 配置要求2C4G以上（代理软件独立能用的资源，虚拟机、物理机都可以）
5. 生产环境若要实现高可用可以使用负载均衡器或者keepalive+虚ip
6. nginx配置通过server_name来区分转发下游，如需增加代理地址，在配置文件后面添加一段server配置即可。

# 部署nginx
如客户环境还没有部署nginx，则应先部署nginx服务，如已有nginx，则只需添加代理配置文件即可。

部署包下载地址：[http://dl.piaozone.com:18025/download/tools/nginx-install.tar.gz](http://dl.piaozone.com:18025/download/tools/nginx-install.tar.gz)	

    - 账号：fpy
    - 密码：Fpy@piaonzone2025#$

将部署包上传到nginx服务器的 /opt目录下，执行以下命令部署nginx

```shell
#解压安装
cd /opt
tar xf nginx-install.tar.gz
cd nginx-install
sh nginx_install.sh
```

nginx部署完成后，需要再添加代理配置文件，配置文件内容见 3；

将配置文件内容复制，写入到/usr/local/nginx/conf/conf.d 目录下，文件名：proxy.conf

执行命令，重载nginx：

```shell
/usr/local/nginx/sbin/nginx -t 
/usr/local/nginx/sbin/nginx -s reload 
```

nginx部署完成后，需要修改内网机器的hosts文件，操作如下

# 修改内网服务器hosts文件
在内网服务器的 /etc/hosts 文件中，添加以下内容：（nginx-ip改为实际的nginx IP地址）

```shell
nginx-ip	api-dev.piaozone.com
nginx-ip	api.piaozone.com
nginx-ip	api.kingdee.com
nginx-ip	cosmic-pro.piaozone.com
nginx-ip	cosmic-demo.piaozone.com
nginx-ip	cosmic.piaozone.com
nginx-ip	img.piaozone.com
nginx-ip	title.piaozone.com
nginx-ip	api.weixin.qq.com
nginx-ip	img-test.piaozone.com
nginx-ip	oms-test.piaozone.com
nginx-ip	smsyun.kingdee.com
nginx-ip	mcapi.kingdee.com
```

# nginx配置文件
```shell
server {
    listen 80;
    server_name api-dev.piaozone.com;
    
    location / {
        proxy_pass https://api-dev.piaozone.com;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
server {
    listen 80;
    server_name api.piaozone.com;
    
    location / {
        proxy_pass https://api.piaozone.com;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
server {
    listen 80;
    server_name api.kingdee.com;
    
    location / {
        proxy_pass https://api.kingdee.com;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
server {
    listen 80;
    server_name cosmic-pro.piaozone.com;
    
    location / {
        proxy_pass https://cosmic-pro.piaozone.com;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
server {
    listen 80;
    server_name cosmic-demo.piaozone.com;
    
    location / {
        proxy_pass https://cosmic-demo.piaozone.com;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
server {
    listen 80;
    server_name cosmic.piaozone.com;
    
    location / {
        proxy_pass https://cosmic.piaozone.com;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
server {
    listen 80;
    server_name img.piaozone.com;
    
    location / {
        proxy_pass https://img.piaozone.com;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
server {
    listen 80;
    server_name title.piaozone.com;
    
    location / {
        proxy_pass https://title.piaozone.com;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
server {
    listen 80;
    server_name api.weixin.qq.com;
    
    location / {
        proxy_pass https://api.weixin.qq.com;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
server {
    listen 80;
    server_name img-test.piaozone.com;
    
    location / {
        proxy_pass https://img-test.piaozone.com;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
server {
    listen 80;
    server_name oms-test.piaozone.com;
    
    location / {
        proxy_pass https://oms-test.piaozone.com;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
server {
    listen 80;
    server_name smsyun.kingdee.com;
    
    location / {
        proxy_pass https://smsyun.kingdee.com;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
server {
    listen 80;
    server_name mcapi.kingdee.com;
    
    location / {
        proxy_pass https://mcapi.kingdee.com;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```







