# 服务器映射表

SSH 连接信息。根据目标 IP 查找对应配置。

SSH 密钥基础目录: `ssh-keys/`（相对于 agent_cwd）

云之家 Webhook（所有服务器统一）: 从环境变量 `$YZJ_ALERT_WEBHOOK_TOKEN` 获取，完整 URL 为 `https://www.yunzhijia.com/gateway/robot/webhook/send?yzjtype=0&yzjtoken=$YZJ_ALERT_WEBHOOK_TOKEN`

---

## AWS 环境

密钥目录: `ssh-keys/aws/`

| IP | 描述 | SSH用户 | 密钥文件 |


## tencent 环境

密钥目录: `ssh-keys/tencent/`

认证方式说明：
- **密钥登录**：`密钥文件` 列填写 pem/key 路径，`密码变量` 列为 `-`
- **密码登录**：`密钥文件` 列为 `-`，`密码变量` 列填写环境变量名（密码存于 `.env`，不提交 git）

| IP | 描述 | SSH用户 | 密钥文件 | 密码变量 |
|----|------|---------|---------|---------|
| 172.31.6.46 | Prometheus监控机 | root | tencent/rocky_test.pem | - |
| 172.31.6.56 | 支付网关测试机 | root | tencent/rocky_test.pem | - |
| 172.31.6.17 | jumpserver | root | tencent/rocky_test.pem | - |
| 172.31.6.67 | Clickhouse统计 | root | tencent/rocky_test.pem | - |
| 172.31.16.20 | cosmic-k8s-master | ubuntu | tencent/cosmic_test.pem | - |
| 172.31.16.21 | cosmic-k8s-node01 | ubuntu | tencent/cosmic_test.pem | - |
| 172.31.16.22 | cosmic-k8s-node02 | ubuntu | tencent/cosmic_test.pem | - |
| 172.31.16.28 | cosmic-elk | ubuntu | tencent/cosmic_test.pem | - |
| 172.31.16.30 | cosmic-mysql | ubuntu | tencent/id_rsa | - |
| 172.31.16.40 | cosmic-nginx | ai_reader | - | `$SSH_PASS_TENCENT_172_31_16_40` |
| 172.31.16.29 | cosmic-pg-sandbox-1 | root | tencent/cosmic_test.pem | - |
| 172.31.16.27 | cosmic-pg-内部测试 | root | tencent/cosmic_test.pem | - |
| 172.31.16.100 | cicd | root | tencent/rocky_test.pem | - |
| 172.31.16.137 | cosmic-pg-sandbox-2 | root | tencent/rocky_test.pem | - |
| 172.31.16.157 | 票据沙箱 | root | tencent/rocky_test.pem | - |
| 172.31.36.20 | sit-mysql | ubuntu | tencent/ubuntu_test.pem | - |
| 172.31.36.22 | sit-mid | ubuntu | tencent/ubuntu_test.pem | - |
| 172.31.36.25 | sit-nginx | root | tencent/rocky_test.pem | - |
| 172.31.36.31 | tke-sit-node01 | ubuntu | tencent/ubuntu_test.pem | - |
| 172.31.36.32 | tke-sit-node02 | ubuntu | tencent/ubuntu_test.pem | - |
| 172.31.36.33 | tke-sit-node03 | ubuntu | tencent/ubuntu_test.pem | - |
| 172.31.36.34 | tke-sit-node04 | ubuntu | tencent/ubuntu_test.pem | - |
| 172.31.36.35 | tke-sit-node05 | ubuntu | tencent/ubuntu_test.pem | - |
| 172.31.36.36 | tke-sit-node06 | ubuntu | tencent/ubuntu_test.pem | - |
| 172.31.36.41 | tke-test-node01 | ubuntu | tencent/ubuntu_test.pem | - |
| 172.31.36.42 | tke-test-node02 | ubuntu | tencent/ubuntu_test.pem | - |
| 172.31.36.43 | tke-test-node03 | ubuntu | tencent/ubuntu_test.pem | - |
| 172.31.36.44 | tke-test-node04 | ubuntu | tencent/ubuntu_test.pem | - |
| 172.31.36.45 | tke-test-node05 | ubuntu | tencent/ubuntu_test.pem | - |
| 172.31.36.49 | test-mysql | ubuntu | tencent/ubuntu_test.pem | - |
| 172.31.36.50 | at-mysql | ubuntu | tencent/ubuntu_test.pem | - |
