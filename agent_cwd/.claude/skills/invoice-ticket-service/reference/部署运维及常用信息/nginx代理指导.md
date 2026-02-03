| **文档编号** | **适用产品版本** | **使用范围** | **更新内容** | **创建/更新时间** | **责任人** |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **v25.0.01** | **/** | **公开** | 创建 | **2025-09-22** | **欧浩斌** |
| **v25.0.02** | **/** | **公开** | 新增 | **2025-09-24** | **欧浩斌** |


# 文档说明
主要介绍如何使用 Nginx 进行代理服务的部署，针对常见的代理场景提供解决方案和配置示例。

# nginx部署
如果尚未部署nginx，可参考以下方式部署nginx。如已有nginx，需要添加代理配置，请参考第二部分内容。

#### 源码包部署
```shell
#!/bin/bash
#安装依赖
yum install -y wget gcc-c++ pcre pcre-devel zlib zlib-devel openssl openssl-devel
#创建nginx用户和组
groupadd nginx
useradd -g nginx -s /sbin/nologin nginx

#下载源码包
cd /opt
wget http://nginx.org/download/nginx-1.26.0.tar.gz
#解压
tar -zxvf nginx-1.26.0.tar.gz
cd nginx-1.26.0

#编译安装nginx
./configure --prefix=/usr/local/nginx --user=nginx --group=nginx --with-http_ssl_module --with-http_stub_status_module --with-stream --with-threads
make && make install

#创建nginx配置文件
cat /usr/local/nginx/conf/nginx.conf << 'EOF'
worker_processes        4;
worker_cpu_affinity     0001 0010 0100 1000;

error_log       /usr/local/nginx/logs/error.log;
pid             /usr/local/nginx/logs/nginx.pid;
worker_rlimit_nofile 51200;

events {
        worker_connections  1024;
        multi_accept on;
        use epoll;
}

http {
        include  /usr/local/nginx/conf/mime.types;
        charset  utf-8;
        default_type  application/octet-stream;
        log_format  main    '{'
                             '"time":"$time_iso8601",'
                             '"remote_addr":"$remote_addr",'
                             '"remote_user":"$remote_user",'
                             '"request_uri":"$request_uri",'
                             '"request_time":"$request_time",'
                             '"upstream_time":"$upstream_response_time",'
                             '"upstream_addr":"$upstream_addr",'
                             '"upstream_status":$upstream_status,'
                             '"request_method":"$request_method",'
                             '"http_referrer":"$http_referer",'
                             '"body_bytes_sent":"$body_bytes_sent",'
                             '"status":$status,'
                             '"server_name":"$server_name",'
                             '"request_protocol":"$server_protocol",'
                             '"host":"$host",'
                             '"args":"$args",'
                             '"uri":"$uri",'
                             '"server_ip":"$server_addr",'
                             '"https":"$https",'
                             '"http_x_forwarded_for":"$http_x_forwarded_for",'
                             '"http_user_agent":"$http_user_agent",'
                             '"request_body":"$request_body"'
                             '}';

        access_log  /usr/local/nginx/logs/access.log  main;

        proxy_ssl_server_name on;
        client_header_buffer_size 64M;
    large_client_header_buffers 4 64M;
        sendfile        on;
        keepalive_timeout  30;
      server_tokens off;
        gzip  on;
        gzip_min_length 3k;
        gzip_buffers    4 16k;
        gzip_http_version       1.1;
        gzip_comp_level 5;
        gzip_types      application/javascript text/pain application/x-javascript text/css application/xml text/javascript;
        gzip_vary       on;
        gzip_disable "MSIE [1-6]\.";
        include /usr/local/nginx/conf/conf.d/*.conf;
      }
EOF

# 创建systemd服务文件
cat > /usr/lib/systemd/system/nginx.service << EOF
[Unit]
Description=The nginx HTTP and reverse proxy server
After=network.target remote-fs.target nss-lookup.target

[Service]
Type=forking
PIDFile=/usr/local/nginx/logs/nginx.pid
ExecStartPre=/usr/local/nginx/sbin/nginx -t
ExecStart=/usr/local/nginx/sbin/nginx
ExecReload=/bin/kill -s HUP \$MAINPID
ExecStop=/bin/kill -s QUIT \$MAINPID
PrivateTmp=true
User=nginx
Group=nginx

[Install]
WantedBy=multi-user.target
EOF

# 创建环境配置文件
cat > /etc/sysconfig/nginx << EOF
# NGINX environment variables
NGINX_CONF_FILE="/usr/local/nginx/conf/nginx.conf"
EOF

# 启动Nginx服务
systemctl daemon-reload
systemctl enable nginx
systemctl start nginx


```



#### 使用安装脚本部署
```shell
#!/bin/bash
#下载安装包
cd /opt
wget --http-user=fpy --http-password=Fpy@piaonzone2025#$ http://dl.piaozone.com:18025/download/tools/nginx-install.tar.gz

#解压安装
tar xf nginx-install.tar.gz
cd nginx-install
sh nginx_install.sh
```



#  nginx代理配置场景
####  内网机器通过nginx代理访问公网
客户的内网无法直接连接互联网，需要通过 Nginx 作为代理服务器来实现访问外部网络的需求。

代理类型选择

+ 四层代理（TCP代理）：当 Nginx 作为反向代理服务器时，可以选择四层代理来处理不带有 HTTP 协议的数据流。
+ 七层代理（HTTP代理）：对于 HTTP 请求，七层代理可以处理浏览器请求和与 Web 服务的交互。

代理配置完成之后，如何使内网机器通过代理访问公网？

在需要通过代理访问公网的内网机器上添加host解析：

host文件： /etc/hosts

格式：  代理服务器IP   需要访问的域名

（假设代理服务器IP为： 192.168.1.11）

```shell
127.0.0.1   localhost localhost.localdomain localhost4 localhost4.localdomain4
::1         localhost localhost.localdomain localhost6 localhost6.localdomain6
#新增以下内容
192.168.1.11 api.kingdee.com
192.168.1.11 api.piaozone.com

```

##### 七层代理配置：
通过server_name 来区分访问公网的不同地址，将以下配置文件复制到nginx服务器的 /usr/local/nginx/conf/conf.d 目录下，命名为 proxy.conf，再热加载nginx即可。

热加载nginx命令：

/usr/local/nginx/sbin/nginx -t

/usr/local/nginx/sbin/nginx -s reload

```shell
server {
    listen 80;
    # 针对域名 api-dev.piaozone.com 代理请求到 api-dev.piaozone.com
    server_name api-dev.piaozone.com;

    # SSL证书配置 - 如果需要配置证书，需添加以下注释内容
    #ssl_certificate /path/to/your/certificate.pem;
    #ssl_certificate_key /path/to/your/private.key;
    #ssl_protocols TLSv1.2 TLSv1.3;
    #ssl_ciphers ECDHE-RSA-AES128-GCM-SHA256:ECDHE:ECDH:AES:HIGH:!NULL:!aNULL:!MD5:!ADH:!RC4;
    #ssl_prefer_server_ciphers on;
    
    location / {
        proxy_pass http://api-dev.piaozone.com;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

server {
    listen 80;
    # 针对域名 api.piaozone.com 代理请求到 api.piaozone.com
    server_name api.piaozone.com;
    
    location / {
        proxy_pass http://api.piaozone.com;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

根据需求，新增一段server配置，修改server_name 和 proxy_pass 即可

例如：

如需要通过代理服务器访问 www.baidu.com   则新增以下内容：

```shell
server {
    listen 80;
    # 针对域名 www.baidu.com 代理请求到 www.baidu.com
    server_name www.baidu.com;
    
    location / {
        proxy_pass http://www.baidu.com;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```



##### 四层代理配置
<font style="color:rgb(15, 17, 21);">基于客户端请求的</font>**<font style="color:rgb(15, 17, 21);">SNI（Server Name Indication）</font>**<font style="color:rgb(15, 17, 21);">信息，将请求代理到不同的上游服务器（公网地址）。</font>

<font style="color:rgb(15, 17, 21);">如使用nginx四层代理，需要在nginx配置文件 /usr/local/nginx/conf/nginx.conf 中添加以下内容：</font>

<font style="color:rgb(15, 17, 21);">添加位置： http 模块前</font>

```shell
#四层TCP代理
stream {
#定义上游服务器
    upstream api_piaozne {
    	server api.piaozone.com:443;
    }
    upstream api_kingdee {
    	server api.kingdee.com:443;
    }

#根据客户端请求host选择对应的上游服务器
    map $ssl_preread_server_name $chosen_upstream {
    	"api.piaozone.com"  api_piaozne;
    	"api.kingdee.com"   api_kingdee;
    }
		# 日志
    log_format basic '$remote_addr [$time_local] '
                     '$protocol $status $bytes_sent $bytes_received '
                     '$session_time';
  	server {
  		listen 443;
  		proxy_pass $chosen_upstream;
  		proxy_timeout 10m;		 		# 连接超时10分钟
      proxy_connect_timeout 5s;		# 连接建立超时5秒
  		
  		# 解析客户端请求的 SNI
      ssl_preread on;
  
      access_log /usr/local/nginx/logs/tcp_access.log basic;
	  }
}
```

根据代理的公网地址，添加upstream模块内容和map关联。

例如：需要新增 api-dev.piaozone.com  的代理

新增upstream 模块

```shell
upstream api_dev_piaozne {			#api_dev_piaozne  自定义名称
	server api-dev.piaozone.com:443;			#公网域名
}
```

添加map关联：

```shell
map $host $chosen_upstream {
	"api.piaozone.com"  api_piaozne;
	"api.kingdee.com"   api_kingdee;
  "api-dev.piaozone.com"  api_dev_piaozone;
}
```

添加配置后，需要重启nginx使配置生效。



#### 办公域&公网通过代理服务器访问内网服务
客户内网网络限制严格，不允许直接访问，需要通过代理服务器访问内网服务。

应用服务代理一般使用七层代理，代理配置如下：

```shell
server {
    listen 80;					#自定义端口
    server_name localhost;	#可配置域名
    
    # SSL证书配置，如需使用https协议，需增加以下配置，并使用对应证书
    #ssl_certificate /etc/ssl/certs/app.company.com.crt;
    #ssl_certificate_key /etc/ssl/private/app.company.com.key;
    #ssl_protocols TLSv1.2 TLSv1.3;

    location / {
    proxy_pass http://backend_servers;		#后端服务器地址
    
    # 重要头部设置
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    
    # 超时设置
    proxy_connect_timeout 5s;
    proxy_send_timeout 60s;
    proxy_read_timeout 60s;
    
    # 错误处理
    proxy_next_upstream error timeout invalid_header http_500 http_502 http_503;
    proxy_intercept_errors on;
    error_page 500 502 503 504 /50x.html;
    }
}
```



