# CLAUDE.md

该文件在本项目中为 Claude Code (claude.ai/code) 提供操作指南。

## Project Overview

这是一个使用 FastAPI 和 Claude Agent SDK 构建的 AI Agent 服务。它提供了一个基于 Skill 的可扩展 Agent 系统，具有两个主要集成点：

1. 通用的 `/api/query` 接口，用于程序化访问
2. 云之家 (Yunzhijia) 消息集成，用于企业聊天

系统采用多租户架构，并支持动态模型供应商切换 (Claude Official API, GLM-4, Claude Router)。

> Claude Router指的是[claude-code-router](https://github.com/musistudio/claude-code-router) ，简称ccr，可以将Claude Agent SDK的请求中转到其他LLM，比如: Claude Agent SDK --> ccr --> deepseek
>
> 使用Claude Router时，需每次启动程序运行：eval "$(ccr activate)"  ，具体参考[官方介绍](https://github.com/musistudio/claude-code-router/blob/main/README_zh.md)。

## Development Commands
### Python Environment

```bash
# Create virtual environment
python3 -m venv .venv

# Activate
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

```
### Start/Stop Service

```bash
# Start the API service (with auto-reload)
./run.sh start

# Stop the service
./run.sh stop

# Restart (default)
./run.sh
./run.sh restart
```

### Model Configuration

系统支持动态模型供应商切换：

```python
# Defined in api/services/config_service.py
PREDEFINED_CONFIGS = {
    "claude": ModelConfig(...),        # Claude Official API (官方 API)
    "glm": ModelConfig(...),           # GLM-4 (智谱清言)
    "claude-router": ModelConfig(...)  # Local Claude proxy
}

```

默认配置通过 `DEFAULT_MODEL_CONFIG` 环境变量设置。可在运行时通过 `ConfigService.switch_config()` 切换。

## Skill System

Skills 是从 `agent_cwd/.claude/skills/` 加载的 Claude Code 技能。样例的技能为：

**customer-service** - 发票云客服 Agent

* 处理售前（产品能力）、售后（故障排除）、API 集成等问题
* 知识库位于 `agent_cwd/data/kb/`：
  * `产品与交付知识/` - 产品/交付文档 (默认)
  * `营销知识库/` - 营销/销售材料
  * `API文档/` - API 文档
* 多产品消歧：当存在多个产品时，会阻断并询问用户

**operational-analytics** - 运营分析 Agent

* 处理 EOP（Enterprise Operation Platform，运营平台）数据库查询与分析
* 数据库表：
  * `t_ocm_kbc_order_settle` - 销售出库单/结算单（107K+ 记录）
  * `t_ocm_order_header` - 交易订单主表（109K+ 记录）
  * `t_ocm_order_lines` - 产品订单明细（114K+ 记录）
  * `t_ocm_tenant` - 租户表（35K+ 记录）
* 查询类型：订单查询、数据统计、趋势分析、报表生成
* 输出格式：Markdown 表格、SQL 透明化展示
* 安全机制：SELECT-only、表白名单、关键词黑名单、查询超时保护
* 触发词：EOP、运营平台、订单查询、租户数据、销售统计、t_ocm_*表

Skills 通过查询中的 `Skill` 工具调用。

### Skill Output Mechanism

**Skills 使用 Claude SDK 原生输出机制：**

- **最终输出**：直接输出内容，SDK 自动包装到 `ResultMessage.result` 字段
- **询问用户**：必须使用 `AskUserQuestion` 工具（禁止直接输出问题）
- **知识库链接**：使用 `kb_link.py` 工具将 KB 文件路径转换为可点击的 markdown 链接


## Directory Structure

- `AGENT_CWD` - Agent 工作目录（默认 `agent_cwd/`，可通过环境变量配置）
  - `agent_cwd/.claude/skills/` - Skills 定义
  - `agent_cwd/data/kb/` - 知识库
  - `agent_cwd/data/tenants/` - 租户数据

## Key Environment Variables

在 `.env` 中配置环境变量，具体参考 `.env.example`

关键变量：
- `AGENT_CWD=agent_cwd` - Agent 工作目录