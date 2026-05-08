# 服务器映射表

SSH 连接信息。根据目标 IP 查找对应配置。

SSH 密钥目录: `/datadisk/rundeck/ssh/`

云之家 Webhook（所有服务器统一）: `https://www.yunzhijia.com/gateway/robot/webhook/send?yzjtype=0&yzjtoken=e74c5794699d43b1b8beeabc6d5bc8f7`

---

## 测试环境

| IP | 描述 | SSH用户 | 密钥文件 |
|----|------|---------|---------|
| 172.31.6.46 | Prometheus监控机 | root | rocky_test.pem |
| 172.31.6.56 | 支付网关测试机 | root | rocky_test.pem |
| 172.31.6.17 | jumpserver | root | rocky_test.pem |
| 172.31.6.67 | Clickhouse统计 | root | rocky_test.pem |
| 172.31.16.20 | cosmic-k8s-master | ubuntu | cosmic_test.pem |
| 172.31.16.21 | cosmic-k8s-node01 | ubuntu | cosmic_test.pem |
| 172.31.16.22 | cosmic-k8s-node02 | ubuntu | cosmic_test.pem |
| 172.31.16.28 | cosmic-elk | ubuntu | cosmic_test.pem |
| 172.31.16.30 | cosmic-mysql | ubuntu | id_rsa |
| 172.31.16.40 | cosmic-nginx | ubuntu | id_rsa |
| 172.31.16.29 | cosmic-pg-sandbox-1 | root | cosmic_test.pem |
| 172.31.16.27 | cosmic-pg-内部测试 | root | cosmic_test.pem |
| 172.31.16.100 | cicd | root | rocky_test.pem |
| 172.31.16.137 | cosmic-pg-sandbox-2 | root | rocky_test.pem |
| 172.31.16.157 | 票据沙箱 | root | rocky_test.pem |
| 172.31.36.20 | sit-mysql | ubuntu | ubuntu_test.pem |
| 172.31.36.22 | sit-mid | ubuntu | ubuntu_test.pem |
| 172.31.36.25 | sit-nginx | root | rocky_test.pem |
| 172.31.36.31 | tke-sit-node01 | ubuntu | ubuntu_test.pem |
| 172.31.36.32 | tke-sit-node02 | ubuntu | ubuntu_test.pem |
| 172.31.36.33 | tke-sit-node03 | ubuntu | ubuntu_test.pem |
| 172.31.36.34 | tke-sit-node04 | ubuntu | ubuntu_test.pem |
| 172.31.36.35 | tke-sit-node05 | ubuntu | ubuntu_test.pem |
| 172.31.36.36 | tke-sit-node06 | ubuntu | ubuntu_test.pem |
| 172.31.36.41 | tke-test-node01 | ubuntu | ubuntu_test.pem |
| 172.31.36.42 | tke-test-node02 | ubuntu | ubuntu_test.pem |
| 172.31.36.43 | tke-test-node03 | ubuntu | ubuntu_test.pem |
| 172.31.36.44 | tke-test-node04 | ubuntu | ubuntu_test.pem |
| 172.31.36.45 | tke-test-node05 | ubuntu | ubuntu_test.pem |
| 172.31.36.49 | test-mysql | ubuntu | ubuntu_test.pem |
| 172.31.36.50 | at-mysql | ubuntu | ubuntu_test.pem |
| 172.31.36.51 | tke-at-node01 | ubuntu | ubuntu_test.pem |
| 172.31.36.52 | tke-at-node02 | ubuntu | ubuntu_test.pem |
| 172.31.36.53 | tke-at-node03 | ubuntu | ubuntu_test.pem |
| 172.31.36.54 | tke-at-node04 | ubuntu | ubuntu_test.pem |
| 172.31.36.59 | at-middleware | ubuntu | ubuntu_test.pem |
| 172.31.26.46 | sit-es | root | rocky_test.pem |
| 172.31.26.52 | defectdojo | root | rocky_test.pem |
| 172.31.26.63 | 研究院01 | ubuntu | ubuntu_test.pem |
| 172.31.26.64 | qdrant | root | rocky_test.pem |
| 172.31.26.201 | 研究院01 | ubuntu | ubuntu_test.pem |
| 172.31.26.202 | 研究院02 | ubuntu | ubuntu_test.pem |
| 172.31.26.203 | 研究院03 | ubuntu | ubuntu_test.pem |
| 172.31.7.3 | gpu服务器 | ubuntu | ubuntu_test.pem |
| 172.31.66.201 | kiro-LiteLLM | root | rocky_test.pem |
| 172.31.76.11 | minio01 | ubuntu | ubuntu_test.pem |
| 172.31.76.22 | minio-mid | ubuntu | ubuntu_test.pem |

---

## 默认配置

如果 IP 不在上表中，使用以下默认值：

- SSH 用户: `root`
- 密钥文件: `rocky_test.pem`
