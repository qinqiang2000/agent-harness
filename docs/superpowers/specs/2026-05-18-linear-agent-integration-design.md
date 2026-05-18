# Linear Agent 集成设计文档

> 版本：1.0 | 日期：2026-05-18

---

## 1. 目标

将当前 agent-harness 项目作为 Linear 的外接 Agent：

1. Linear issue 被分配或 @提及 Agent 时触发 webhook
2. 服务读取 Linear issue 上下文，调用 Product Skill 工作流（①→②→③→④→⑤）生成 PRD
3. 将 PRD 产物写入本地目录，并同步推送到 GitHub 仓库
4. 执行阶段 A（创建父子 Issue 骨架）和阶段 B（PRD 回填 Issue）
5. 通过 Agent Activity 实时向用户反馈进度

---

## 2. 架构总览

```
Linear 用户分配/提及 Agent
        ↓
POST /linear/webhook（HMAC-SHA256 验证）
        ↓ 立即返回 200
        ↓ 后台任务
        ↓
LinearHandler.handle_session_created()
        ↓
  ① 发送 thought activity（10秒内）
  ② issue 状态 → "需求编写中"
  ③ 将自己设为 delegate
  ④ 调用 AgentService（skill: linear-product-prd）
        ↓
  Product Skill ①→②→③→④→⑤
        ↓
  产物写入 data/linear/prd/{issue_identifier}/
        ↓
  同步推送 GitHub: {issue_identifier}/PRD/
        ↓
  阶段 A：解析特性清单 → 创建父子 Issue
        ↓
  阶段 B：PRD 文件 → 回填子 Issue → 状态变"需求编写完成"
        ↓
  发送 response activity（PRD 摘要 + GitHub 链接）
```

---

## 3. 目录结构

```
plugins/bundled/linear/
├── plugin.py           # ChannelPlugin 实现，注册路由
├── plugin.json         # 插件元数据
├── handler.py          # Agent Session 处理主逻辑
├── linear_client.py    # Linear GraphQL API 封装（含 token 自动刷新）
├── token_store.py      # SQLite token 存储
├── issue_creator.py    # 阶段 A：解析特性清单 → 创建父子 Issue
├── prd_backfiller.py   # 阶段 B：PRD 文件 → 回填 Issue
├── artifact_sync.py    # GitHub 产物同步（lichuang-1993 账号）
└── models.py           # Pydantic 数据模型

agent_cwd/.claude/skills/
└── product-ontology/   # Product Skill 文件（从 docs/requirements 复制）
    ├── 01-requirement-analysis/
    ├── 02-ontology-context/
    ├── 03-ontology-update/
    ├── 04-prototype-design/
    ├── 05-generate-prd/
    ├── commands/
    └── linear-product-prd/  # 包装 skill，接收 Linear 上下文
        └── SKILL.md

data/linear/
├── linear_tokens.db    # SQLite token store
└── prd/
    └── {issue_identifier}/  # skill 产物本地目录
```

---

## 4. OAuth 安装流程

```
GET /linear/oauth/install
  → 重定向到 Linear 授权页
    ?client_id=...
    &redirect_uri=.../linear/oauth/callback
    &response_type=code
    &actor=app
    &scope=read,write,app:assignable,app:mentionable
    &state=<secure_random>

GET /linear/oauth/callback?code=xxx&state=xxx
  → 验证 state
  → POST https://api.linear.app/oauth/token 换取 tokens
  → GET viewer { id } 获取 App User ID
  → 存入 SQLite（workspace_id, app_user_id, access_token, refresh_token, expires_at）
  → 返回安装成功页面
```

---

## 5. Webhook 处理

### 5.1 安全验证

```python
# 验证 HMAC-SHA256 签名
computed = hmac.new(webhook_secret, raw_body, sha256).hexdigest()
assert hmac.compare_digest(computed, header_signature)

# 防重放：时间戳在 60 秒内
assert abs(time.time() * 1000 - webhook_timestamp) < 60_000
```

### 5.2 事件处理

| action | 处理方式 |
|--------|---------|
| `created` | 启动新的 Agent 处理循环 |
| `prompted` | 读取对话历史，继续处理 |
| stop 信号 | 立即停止，发送 response 确认 |

### 5.3 状态流转（可配置）

| 时机 | Linear 状态 | 配置项 |
|------|------------|--------|
| 开始处理 | 需求编写中 | `status_on_start` |
| PRD 全部完成 | 需求编写完成 | `status_on_prd_done` |
| 发生错误 | 不变 | `status_on_error`（null） |

---

## 6. Product Skill 调用

### 6.1 包装 skill：linear-product-prd

职责：
1. 接收 Linear issue 标题、描述、评论、promptContext
2. 调用 `/product-workflow` 编排器（①→②→③→④→⑤）
3. 产物统一写入 `data/linear/prd/{issue_identifier}/`
4. 返回 PRD 文件路径列表、摘要、执行状态

### 6.2 调用参数

```
skill: linear-product-prd
query: {issue_title}\n\n{issue_description}\n\n{promptContext}
output_path: data/linear/prd/{issue_identifier}/
```

### 6.3 Agent Activity 进度反馈

| 阶段 | Activity 类型 | 内容 |
|------|-------------|------|
| 收到请求 | thought | 已收到需求，开始分析... |
| ① 需求分析 | action | 正在执行需求分析 |
| ② 本体映射 | action | 正在执行本体查询与映射 |
| ③ 本体更新 | action | 正在执行本体更新 Gate |
| ④ 页面设计 | action | 正在执行页面设计 |
| ⑤ PRD 生成 | action | 正在生成 PRD |
| 阶段 A | action | 正在创建 Linear Issue 骨架 |
| 阶段 B | action | 正在回填 PRD 到 Issue |
| 完成 | response | PRD 已生成，GitHub 链接：... |

---

## 7. GitHub 产物同步

- 仓库：`git@github-lichuang:invagent/develop-workflow-artifacts.git`
- 账号：`lichuang-1993`（SSH key: `~/.ssh/id_ed25519_lichuang1993`）
- 路径映射：`data/linear/prd/{issue_identifier}/a/b.md` → `{issue_identifier}/PRD/a/b.md`
- commit message：`feat({issue_identifier}): add PRD artifacts`
- 推送失败：记录日志，不影响 Linear 回写，activity 中提示 GitHub 同步失败

---

## 8. 阶段 A：Issue 骨架创建

触发条件：skill 产物目录下出现 `stage: confirmed` 的特性清单文件

执行步骤：
1. 解析特性清单 frontmatter + 表格
2. 创建父 Issue（Epic）：title = frontmatter.title，description = 需求分析报告 + 特性清单
3. 批量创建子 Issue 骨架：title = `{id} {title}`，description = 对应本体映射报告
4. 设置 parent + blocking 关系
5. 回写 `linear_result.yaml` 到产物目录

幂等处理：通过 frontmatter.id 去重，重复触发不重复创建。

---

## 9. 阶段 B：PRD 回填

触发条件：产物目录下出现 `{特性ID}_*_用户故事设计规格说明书_v*.md` 文件

执行步骤：
1. 从文件名提取特性 ID
2. 读取 `linear_result.yaml`，查找对应 Linear Issue ID
3. 上传 PRD 文件为 Issue 附件
4. 读取 PRD 摘要（一、特性概述 + 二、用户故事.主故事）
5. 更新子 Issue 描述（追加 PRD 摘要）
6. 子 Issue 状态 → `需求编写完成`
7. 更新 `linear_result.yaml` 中的 `backfill_status`

---

## 10. 数据存储

### SQLite token store

```sql
CREATE TABLE IF NOT EXISTS linear_installations (
  workspace_id   TEXT PRIMARY KEY,
  workspace_name TEXT,
  app_user_id    TEXT,
  access_token   TEXT NOT NULL,
  refresh_token  TEXT,
  expires_at     INTEGER,
  scopes         TEXT,
  created_at     INTEGER NOT NULL,
  updated_at     INTEGER NOT NULL
);
```

Token 刷新：access_token 有效期 24 小时，过期前自动用 refresh_token 刷新；30 分钟宽限期内失败可重试。

---

## 11. 插件配置（plugins/config.json）

```json
{
  "enabled": ["linear"],
  "plugins": {
    "linear": {
      "client_id": "${LINEAR_CLIENT_ID}",
      "client_secret_env": "LINEAR_CLIENT_SECRET",
      "webhook_secret_env": "LINEAR_WEBHOOK_SECRET",
      "default_skill": "linear-product-prd",
      "session_timeout": 3600,
      "prd_output_root": "data/linear/prd",
      "github_repo": "git@github-lichuang:invagent/develop-workflow-artifacts.git",
      "github_ssh_key": "~/.ssh/id_ed25519_lichuang1993",
      "status_on_start": "需求编写中",
      "status_on_prd_done": "需求编写完成",
      "status_on_error": null
    }
  }
}
```

### .env 新增项

```bash
LINEAR_CLIENT_ID=...
LINEAR_CLIENT_SECRET=...
LINEAR_WEBHOOK_SECRET=...
LINEAR_REDIRECT_URI=https://your-service.example.com/linear/oauth/callback
```

---

## 12. 错误处理

| 场景 | 处理方式 |
|------|---------|
| webhook 签名验证失败 | 返回 401，不处理 |
| Linear API 调用失败 | 重试 3 次，失败后发送 error activity |
| skill 执行失败 | 发送 error activity，issue 状态不变 |
| GitHub 推送失败 | 记录日志，activity 中提示，不阻断主流程 |
| token 过期 | 自动刷新，30 分钟宽限期内重试 |
| 收到 stop 信号 | 立即停止，发送 response 确认 |
| 映射报告文件不存在 | 子 Issue 描述留空，标记警告，继续创建其他 |
| PRD 特性 ID 在 linear_result 中找不到 | 报错跳过，activity 中提示 |

---

## 13. 测试策略

- 单元测试：特性清单解析器、PRD 文件名匹配、token store CRUD
- 集成测试：webhook 签名验证、Linear API mock、GitHub 同步 mock
- 手动验证：在 Linear 中分配 issue 给 Agent，观察完整链路
