# Apifox 文档同步开发指南

## 背景

`api/services/apifox_sync.py` 负责将 Apifox 项目里的文档同步到本地 KB（`agent_cwd/data/kb/接口文档/`），供 issue-diagnosis skill 检索使用。文档分两类：

- **接口文档（http 类型）**：通过 Apifox 开放 API 同步
- **说明文档（doc 类型）**：通过 Apifox 在线文档站 API 同步

---

## 接口文档同步

### 使用的 API

| 接口 | 说明 |
|------|------|
| `GET /api/v1/projects/{id}/api-folders` | 获取目录树结构 |
| `GET /api/v1/projects/{id}/http-apis` | 获取接口列表（含基本信息） |
| `GET /api/v1/projects/{id}/http-apis/{apiId}` | 获取单个接口详情（含请求体、响应） |
| `GET /api/v1/projects/{id}/data-schemas` | 获取数据模型（用于解析 `$ref`） |

Base URL：`https://api.apifox.com/api/v1`

### 关键点

1. **`$ref` 解析**：接口的 `requestBody` 和 `responses` 里的 JSON Schema 可能包含 `$ref: "#/definitions/{id}"` 引用，需要先拉取 `data-schemas` 建立映射表，再递归替换为实际内容。

2. **目录层级**：`api-folders` 返回扁平列表，通过 `parentId` 递归构建路径，映射为本地子目录。

3. **每接口一文件**：每个接口写一个 `.md` 文件，文件名为接口名，目录结构与 Apifox 一致。

4. **并发拉取详情**：接口详情需逐个请求，用 `asyncio.Semaphore(20)` 控制并发。

---

## Doc 文档同步

### 为什么不用开放 API

Apifox 开放 API（`/api/v1/projects/{id}/markdown-docs` 等）**不提供 doc 内容读取**，所有相关路径均返回 302 或空响应。Apifox 官方 MCP Server（`apifox-mcp-server`）也只暴露接口文档，不含 doc 内容。

### 正确的 API

doc 内容通过**在线文档站 API** 获取，`project_id` 与 `published-projects` ID 相同：

| 接口 | 说明 |
|------|------|
| `GET /api/v1/published-projects/{id}/http-api-tree` | 获取完整目录树（含 doc 节点） |
| `GET /api/v1/published-projects/{id}/doc/{docId}` | 获取单个 doc 的 markdown 内容 |

> 这两个接口来自 Apifox 网页端内部 API，通过分析 `cdn.apifox.com/docs-site/assets/root-*.js` 源码发现。

### 如何找到 doc 节点

`http-api-tree` 返回的树节点里，`type=doc` 的节点结构如下：

```json
{
  "key": "doc.3641866",
  "type": "doc",
  "name": "整体介绍",
  "children": [],
  "doc": {
    "id": 3641866,
    "name": "整体介绍"
  }
}
```

递归遍历树，收集所有 `type=doc` 节点，从 `node.doc.id` 取 ID，同时记录路径（父节点名称列表）用于构建本地目录。

### doc 内容响应格式

```json
{
  "success": true,
  "data": {
    "id": 3641866,
    "name": "整体介绍",
    "content": "# 介绍\n\n..."
  }
}
```

`content` 字段即为 markdown 原文。

---

## 鉴权

两类 API 使用相同的 Bearer Token：

```
Authorization: Bearer {APIFOX_TOKEN}
X-Apifox-Api-Version: 2024-03-28
```

Token 通过环境变量 `APIFOX_TOKEN` 配置（Apifox 账号设置 → API 访问令牌）。

---

## 配置

`.env` 里配置多项目，支持两种格式：

```
APIFOX_TOKEN=afxp_xxx

# 格式1：name:projectId（doc 同步用 projectId 作为 onlineId）
# 格式2：name:projectId:onlineId（显式指定 published-projects ID）
APIFOX_PROJECTS=发票云标准版:3958968,智能特性:3968900,星瀚旗舰版:111111:abcd-efgh-uuid

APIFOX_SYNC_INTERVAL_MINUTES=60
```

### onlineId 说明

`onlineId` 是 `published-projects` API 使用的 ID，用于 doc 文档同步。大多数项目的 `onlineId` 与 `projectId` 相同，但部分项目（如未发布在线文档站的项目）会返回 404，此时需要：

1. 打开项目在线文档 URL，如 `https://s.apifox.cn/{uuid}/doc-xxx`，其中 `{uuid}` 即为 `onlineId`
2. 在配置里显式指定：`name:projectId:onlineId`
3. 若项目没有在线文档，`published-projects` 接口会返回 404，doc 同步会跳过（不影响接口文档同步）

---

## 同步流程

```
sync(project_name)
├── 并发拉取 api-folders + http-apis + data-schemas
├── 构建 $ref 映射表
├── 清空项目目录（shutil.rmtree）
├── 并发拉取所有接口详情
├── 按目录层级写入接口 .md 文件
├── 写入 _sync_meta.json
└── _sync_docs_inner(base_dir)
    ├── 拉取 http-api-tree
    ├── 收集所有 type=doc 节点
    └── 并发拉取 doc 内容，按路径写入 .md 文件
```

---

## 踩坑记录

| 问题 | 原因 | 解决 |
|------|------|------|
| `GET /api/v1/projects/{id}/markdown-docs` 返回空 | 开放 API 不支持读取 doc 内容 | 改用 `published-projects` 内部 API |
| `sync_docs` 死锁 | `sync` 和 `sync_docs` 都持有同一个 `asyncio.Lock` | 提取 `_sync_docs_inner` 不加锁，由 `sync` 在锁内调用 |
| doc 文件写到错误目录 | 测试时未设置 `AGENT_CWD` 环境变量，`DATA_DIR` 指向项目根目录 | 运行时确保 `AGENT_CWD=agent_cwd` |
