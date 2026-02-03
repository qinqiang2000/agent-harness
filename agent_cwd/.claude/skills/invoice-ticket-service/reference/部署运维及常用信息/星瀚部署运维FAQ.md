| 文档版本 | 更新内容 | 使用范围 | 创建（修改）时间 | 变更人 |
| :---: | :---: | :---: | :---: | :---: |
| v25.0.01 | 初始版本 | 公开 | 2025-09-28 | 欧浩斌 |
|  |  |  |  |  |




# 苍穹安装器部署后，不显示访问地址
<font style="color:black;background-color:#FFFFFF;">停掉安装器singularity/bin/stop.sh，删掉singularity/bin/kdos 文件，再启动安装器</font>

```shell
#安装目录以/data 为例，请替换为实际目录
cd /data/singularity/bin
sh stop.sh
rm -rf /data/singularity/bin/kdos
sh startup.sh
```

# 环境部署报错：机器需至少16核64G内存
增加服务器资源。

苍穹安装服务器资源限制脚本：

<font style="color:black;background-color:#FFFFFF;">singularity/scripts/k8s/ansible/12-check_cosmic_config.yaml</font>

# 星瀚登录ierp密码重置-administrator
<font style="color:black;background-color:#FFFFFF;">//激活已存在账户，密码:Admin@223344 </font>

```sql
update t_sec_user_u set FPASSWORD = '4b78071038273c0d7e2337c6c71e91c0be2ee75f7cfadd8cf444b8f045ab465bba6e2dfd46d76b5b4b58a7b13e47dfdfed866e69fcfd997eca3e2cff3a303765',fpsweffectivedate = now(),FISREGISTED=1,FISACTIVED=1 where FUSERNAME='administrator';
```



# 同步更新许可提示“改访问方式存在安全风险”
![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1763452344315-1c142e90-dc0e-49a5-9a3c-b76edfa564f5.png)

<font style="color:black;background-color:#FFFFFF;">mc增加了安全认证，把mc容器环境变量最后一行删掉，重启mc和mservice容器</font>

![](https://cdn.nlark.com/yuque/0/2025/png/21778712/1763452361780-25914878-cd90-43a8-a9e3-5f7795f94c91.png)







