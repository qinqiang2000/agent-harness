# SSH 密钥管理

Agent 运维诊断使用的 SSH 密钥，按云厂商分目录存放。

## 目录结构

```
ssh-keys/
├── aws/          # AWS EC2 实例密钥
│   ├── ubuntu_test.pem
│   ├── rocky_test.pem
│   └── ...
├── tencent/      # 腾讯云 CVM/TKE 实例密钥
│   ├── cosmic_test.pem
│   └── ...
└── README.md
```

## 安全要求

- 密钥文件权限必须为 600：`chmod 600 *.pem`
- 此目录已加入 .gitignore，密钥不会提交到仓库
- 生产部署时通过 Ansible/Rundeck 或手动拷贝密钥到此目录

## 迁移说明

原密钥路径：`/datadisk/rundeck/ssh/`
新密钥路径：`agent_cwd/ssh-keys/{cloud}/`

server-mapping.md 中的 `key_path` 字段已更新为相对路径格式：`aws/ubuntu_test.pem`
SKILL.md 中的密钥基础路径已更新为项目内路径。
