# Audit Plugin - AI 财务审核助手

AI-native 财务单据审核插件。用户上传财务文档（PDF/图片），配置自然语言审核规则，Claude 自动逐条校验并输出可视化审核报告。

## 架构

```
Browser (SPA at /audit/)
├── 文件上传区（拖拽/粘贴/多文件）
├── 规则侧边栏（自然语言规则，开关/编辑/增删）
├── Chat 面板（SSE 流式输出，支持追问）
└── 审核报告视图（结构化对比卡片 + PDF 页面预览）
         │
         ▼
audit plugin (FastAPI routes via PluginAPI)
         │
         ▼
AgentService.process_query() → Claude SDK (Sonnet 4.6)
         │
         ▼
Skill: financial-audit (SKILL.md)
   Read tool 原生读取 PDF/图片
   输出 Markdown 报告 + JSON 结构化数据
```

## 文件结构

```
plugins/bundled/audit/
├── plugin.json          # 插件清单
├── plugin.py            # AuditChannelPlugin + register() + 所有 API 路由
├── handler.py           # AuditHandler: prompt 组装、调用 AgentService
├── models.py            # Pydantic 数据模型
├── file_manager.py      # 文件上传/列表/删除
├── rule_store.py        # 规则 CRUD（JSON 文件存储，含 7 条默认规则）
└── static/
    └── index.html       # 完整 SPA（Alpine.js + Tailwind，无构建步骤）

agent_cwd/.claude/skills/financial-audit/
└── SKILL.md             # 通用审核 Skill（规则和文档类型均为动态）
```

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/audit/` | GET | 前端 SPA |
| `/audit/upload` | POST | 文件上传（multipart/form-data: `file` + `tenant_id`） |
| `/audit/files/{tid}` | GET | 列出租户已上传文件 |
| `/audit/files/{tid}/{name}` | DELETE | 删除文件 |
| `/audit/files/{tid}/{name}/preview` | GET | 原始文件预览 |
| `/audit/files/{tid}/{name}/pages/{page}` | GET | PDF 指定页渲染为 PNG（需 PyMuPDF） |
| `/audit/files/{tid}/{name}/page-count` | GET | PDF 页数 |
| `/audit/rules/{tid}` | GET | 获取规则列表 |
| `/audit/rules/{tid}` | PUT | 替换规则列表 |
| `/audit/config/{tid}` | GET/PUT | 租户配置 |
| `/audit/query` | POST | 执行审核（SSE 流式返回） |

## 工作流程

1. **上传文档** — 拖拽/粘贴 PDF 或图片到上传区
2. **配置规则** — 侧边栏编辑自然语言规则（默认预置 7 条），可开关/增删
3. **开始审核** — 点击按钮或输入"开始审核"
4. **Claude 处理**:
   - 分析规则文本 → 推断涉及的文档类型
   - Read tool 读取所有上传文件（PDF 原生支持多页）
   - 将文件内容匹配到规则中的文档类型
   - 按规则动态提取字段、逐条比对
5. **输出结果**:
   - Chat 流式显示 Markdown 报告
   - 前端解析 `<!-- AUDIT_RESULT_JSON -->` 块，渲染对比卡片
   - 卡片按 PASS/FAIL/UNABLE 颜色编码，点击页码可预览 PDF 页面
6. **追问** — 审核完成后可在 Chat 中追问（如"规则3为什么不通过？"）

## Skill 设计要点

Skill 不硬编码任何规则或文档类型：

- **规则驱动**: 所有审核逻辑由 handler 从 `audit-rules.json` 动态注入 prompt
- **文档类型动态识别**: 由规则文本隐式定义（规则说"报价单"就找报价单）
- **字段动态提取**: 根据规则语义决定提取什么字段
- **结构化输出**: Markdown（人可读）+ JSON（前端可视化），JSON 解析失败时自动 fallback 到 Markdown

## 数据存储

```
agent-harness/data/tenants/{tenant_id}/
├── audit-files/          # 上传的文档
├── audit-rules.json      # 审核规则
└── audit-config.json     # 租户配置
```

## 对 agent-harness 的修改

仅 1 处微调（非侵入）：

- `api/services/agent_service.py`: 支持 `request.metadata["model"]` 和 `metadata["max_turns"]` 覆盖默认值。audit 插件用此机制将模型切换为 Sonnet 4.6（PDF/视觉识别更准确）。

## 配置 (plugins/config.json)

```json
{
  "audit": {
    "max_upload_size_mb": 20,
    "default_skill": "financial-audit",
    "session_timeout": 3600
  }
}
```

## 依赖

- **必须**: agent-harness 现有依赖（FastAPI, claude_agent_sdk, sse-starlette 等）
- **可选**: `PyMuPDF`（`pip install PyMuPDF`）— PDF 页面渲染为 PNG 预览

## 快速启动

```bash
# 1. 确保 audit 已在 plugins/config.json 的 enabled 列表中（已默认添加）

# 2. 可选：安装 PyMuPDF 用于 PDF 页面预览
pip install PyMuPDF

# 3. 启动 agent-harness
./run.sh restart

# 4. 打开浏览器
open http://localhost:9123/audit/
```
