# ierp-login Skill

金蝶 iERP 扫码登录 skill，通过云之家通知指定人员完成扫码。

## 部署步骤

### 1. 安装 Python 依赖

进入虚拟环境后安装：
```bash
cd scripts
pip install -r requirements.txt
```

### 2. 创建配置文件

```bash
cp references/config.example.json scripts/config.json
```

编辑 `scripts/config.json`，填写云之家参数：
- `company_id`：企业 ID
- `pub_id`：公共号 ID（XT-xxxx 格式）
- `user_ids`：接收二维码通知的云之家用户 OpenID 列表

### 3. 创建 .env 文件（敏感字段）

```bash
cp references/env.example scripts/.env
```

编辑 `scripts/.env`，填写：
- `YZJ_PUB_SECRET`：云之家公共号 secret
- `YZJ_SESSION_COOKIE`：从浏览器 DevTools 复制的 PLAY_SESSION Cookie

### 4. 确认 browse skill 已安装

```bash
ls ~/.claude/skills/gstack/browse/dist/browse
```

如不存在，按照 gstack browse skill 文档安装。

## 使用方式

直接对 Claude 说：
- "登录 ierp"
- "帮我登一下金蝶"
- "ierp 登录"

## 目录说明

```
ierp-login/
├── SKILL.md              # skill 主入口
├── scripts/
│   ├── notify_yzj.py     # 云之家通知脚本
│   ├── cookie_manager.py # Cookie 管理脚本
│   ├── requirements.txt  # Python 依赖
│   ├── config.json       # 配置文件（需手动创建，参考 references/config.example.json）
│   ├── .env              # 敏感字段（需手动创建，参考 references/env.example）
│   ├── data/             # Cookie 存储（自动创建）
│   └── logs/             # 调试截图（自动创建）
└── references/
    ├── config.example.json  # 配置示例
    └── env.example          # 环境变量示例
```
