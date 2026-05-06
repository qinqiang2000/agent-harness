# FAQ 编辑器 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 提供 Vue3 + Vite + Element Plus 前端页面，实施人员录入 FAQ，审核人审核，审核通过后存入 PostgreSQL；由审核人手动触发或定时任务将已审核 FAQ 生成对应 Markdown 文件并 git commit。

**Architecture:** 后端新增 `/api/faq` FastAPI 路由，FAQ 数据存 PostgreSQL（`faq_items` 表）；前端独立 Vue3 项目在 `frontend/` 目录，打包产物放 `static/faq/`（不提交 git）；审核和生成 MD 操作需要 `FAQ_REVIEW_PASSWORD` 环境变量验证。

**Tech Stack:** FastAPI + asyncpg（后端）、PostgreSQL（存储）、Vue3 + Vite + Element Plus（前端）、APScheduler（定时任务，已有）、Python subprocess（git 操作）

---

## 背景知识

- FAQ Markdown 文件位于 `agent_cwd/.claude/skills/issue-diagnosis/kb/`，格式 `{分类}-faq.md`
- 现有分类：开票、收票、鉴权登录、接口参数、进项发票采集、性能超时、faq-newtimeai-invoice
- PG 连接信息在 `.env`：`POSTGRES_HOST/PORT/DATABASE/USER/PASSWORD`
- 项目已有 `asyncpg`，但 API 层尚无 PG 连接封装，需新建
- `app.py` 已有 `static/` 目录条件挂载（目录存在自动生效）
- 前端构建产物 `static/faq/` 加入 `.gitignore`，不提交 git

---

## Task 1: 数据库连接封装

**Files:**
- Create: `api/db.py`

**Step 1: 写失败测试**

创建 `tests/test_faq_db.py`：

```python
import pytest
import asyncio
from api.db import get_faq_pool

@pytest.mark.asyncio
async def test_pool_connects():
    pool = await get_faq_pool()
    async with pool.acquire() as conn:
        result = await conn.fetchval("SELECT 1")
    assert result == 1
```

**Step 2: 运行测试确认失败**

```bash
cd /Users/jinfan/code/get-master/agent-harness
source .venv/bin/activate && pytest tests/test_faq_db.py -v
```
Expected: FAIL（模块不存在）

**Step 3: 实现 `api/db.py`**

```python
"""PostgreSQL connection pool for FAQ service."""
import os
import asyncpg

_faq_pool: asyncpg.Pool | None = None


async def get_faq_pool() -> asyncpg.Pool:
    global _faq_pool
    if _faq_pool is None:
        _faq_pool = await asyncpg.create_pool(
            host=os.getenv("POSTGRES_HOST"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            database=os.getenv("POSTGRES_DATABASE", "postgres"),
            user=os.getenv("POSTGRES_USER"),
            password=os.getenv("POSTGRES_PASSWORD"),
            min_size=1,
            max_size=5,
        )
    return _faq_pool


async def close_faq_pool():
    global _faq_pool
    if _faq_pool:
        await _faq_pool.close()
        _faq_pool = None
```

**Step 4: 运行测试确认通过**

```bash
source .venv/bin/activate && pytest tests/test_faq_db.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add api/db.py tests/test_faq_db.py
git commit -m "feat: add PostgreSQL connection pool for FAQ service"
```

---

## Task 2: 数据库表初始化

**Files:**
- Create: `api/faq_schema.sql`
- Modify: `api/db.py`（新增 init_faq_table 函数）

**Step 1: 创建 `api/faq_schema.sql`**

```sql
CREATE TABLE IF NOT EXISTS faq_items (
    id          SERIAL PRIMARY KEY,
    category    VARCHAR(64)  NOT NULL,
    question    TEXT         NOT NULL,
    answer      TEXT         NOT NULL,
    submitter   VARCHAR(64)  NOT NULL,
    status      VARCHAR(16)  NOT NULL DEFAULT 'pending',  -- pending/approved/rejected
    reviewer    VARCHAR(64)  DEFAULT '',
    comment     TEXT         DEFAULT '',
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_faq_category ON faq_items(category);
CREATE INDEX IF NOT EXISTS idx_faq_status   ON faq_items(status);
```

**Step 2: 在 `api/db.py` 新增初始化函数**

```python
async def init_faq_table():
    """Create faq_items table if not exists."""
    from pathlib import Path
    sql = (Path(__file__).parent / "faq_schema.sql").read_text()
    pool = await get_faq_pool()
    async with pool.acquire() as conn:
        await conn.execute(sql)
```

**Step 3: 在 `app.py` lifespan 中调用**

在 `lifespan` 函数 `yield` 之前添加：
```python
from api.db import init_faq_table, close_faq_pool
await init_faq_table()
```
在 `yield` 之后（shutdown 阶段）添加：
```python
await close_faq_pool()
```

**Step 4: 启动服务验证表已创建**

```bash
./run.sh
# 检查 PG 中 faq_items 表是否存在
```

**Step 5: Commit**

```bash
git add api/faq_schema.sql api/db.py app.py
git commit -m "feat: add faq_items table schema and auto-init on startup"
```

---

## Task 3: 后端 FAQ CRUD API

**Files:**
- Create: `api/routers/faq.py`
- Create: `tests/test_faq_api.py`
- Modify: `app.py`（注册路由）
- Modify: `.env.example`（新增 FAQ_REVIEW_PASSWORD）

**Step 1: 写失败测试**

创建 `tests/test_faq_api.py`：

```python
import pytest
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)

def test_list_categories():
    resp = client.get("/api/faq/categories")
    assert resp.status_code == 200
    assert "开票" in resp.json()["categories"]

def test_submit_draft():
    resp = client.post("/api/faq/drafts", json={
        "category": "开票",
        "question": "测试问题",
        "answer": "测试答案",
        "submitter": "张三"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert data["status"] == "pending"

def test_submit_invalid_category():
    resp = client.post("/api/faq/drafts", json={
        "category": "不存在", "question": "Q", "answer": "A", "submitter": "张三"
    })
    assert resp.status_code == 400

def test_review_wrong_password():
    r = client.post("/api/faq/drafts", json={
        "category": "开票", "question": "Q2", "answer": "A2", "submitter": "李四"
    })
    draft_id = r.json()["id"]
    resp = client.post(f"/api/faq/drafts/{draft_id}/review", json={
        "action": "approve", "reviewer": "王五", "password": "wrong"
    })
    assert resp.status_code == 403
```

**Step 2: 运行测试确认失败**

```bash
source .venv/bin/activate && pytest tests/test_faq_api.py -v
```
Expected: FAIL

**Step 3: 实现 `api/routers/faq.py`**

```python
"""FAQ CRUD API."""
import logging
import os
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.db import get_faq_pool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/faq", tags=["faq"])

FAQ_CATEGORIES = [
    "开票", "收票", "鉴权登录", "接口参数", "进项发票采集", "性能超时", "faq-newtimeai-invoice"
]


class DraftSubmit(BaseModel):
    category: str
    question: str
    answer: str
    submitter: str


class DraftUpdate(BaseModel):
    question: str | None = None
    answer: str | None = None
    category: str | None = None


class DraftReview(BaseModel):
    action: Literal["approve", "reject"]
    reviewer: str
    password: str
    comment: str = ""


def _check_password(password: str):
    expected = os.getenv("FAQ_REVIEW_PASSWORD", "")
    if expected and password != expected:
        raise HTTPException(status_code=403, detail="审核密码错误")


def _row_to_dict(row) -> dict:
    return dict(row)


@router.get("/categories")
async def list_categories():
    return {"categories": FAQ_CATEGORIES}


@router.get("/drafts")
async def list_drafts(status: str = "", category: str = "", page: int = 1, page_size: int = 20):
    pool = await get_faq_pool()
    conditions = []
    args = []
    if status:
        args.append(status)
        conditions.append(f"status = ${len(args)}")
    if category:
        args.append(category)
        conditions.append(f"category = ${len(args)}")
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    offset = (page - 1) * page_size
    args += [page_size, offset]
    sql = f"""
        SELECT * FROM faq_items {where}
        ORDER BY created_at DESC
        LIMIT ${len(args)-1} OFFSET ${len(args)}
    """
    count_sql = f"SELECT COUNT(*) FROM faq_items {where}"
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *args)
        total = await conn.fetchval(count_sql, *args[:-2])
    return {"drafts": [_row_to_dict(r) for r in rows], "total": total, "page": page, "page_size": page_size}


@router.post("/drafts")
async def submit_draft(body: DraftSubmit):
    if body.category not in FAQ_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"无效分类，可选：{FAQ_CATEGORIES}")
    pool = await get_faq_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """INSERT INTO faq_items (category, question, answer, submitter)
               VALUES ($1, $2, $3, $4) RETURNING *""",
            body.category, body.question, body.answer, body.submitter
        )
    return _row_to_dict(row)


@router.put("/drafts/{draft_id}")
async def update_draft(draft_id: int, body: DraftUpdate):
    pool = await get_faq_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM faq_items WHERE id = $1", draft_id)
        if not row:
            raise HTTPException(status_code=404, detail="条目不存在")
        if row["status"] != "pending":
            raise HTTPException(status_code=400, detail="只能修改待审核条目")
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        if not updates:
            return _row_to_dict(row)
        set_clause = ", ".join(f"{k} = ${i+2}" for i, k in enumerate(updates))
        values = list(updates.values())
        row = await conn.fetchrow(
            f"UPDATE faq_items SET {set_clause}, updated_at = NOW() WHERE id = $1 RETURNING *",
            draft_id, *values
        )
    return _row_to_dict(row)


@router.delete("/drafts/{draft_id}")
async def delete_draft(draft_id: int, password: str = ""):
    _check_password(password)
    pool = await get_faq_pool()
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM faq_items WHERE id = $1", draft_id)
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="条目不存在")
    return {"ok": True}


@router.post("/drafts/{draft_id}/review")
async def review_draft(draft_id: int, body: DraftReview):
    _check_password(body.password)
    pool = await get_faq_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM faq_items WHERE id = $1", draft_id)
        if not row:
            raise HTTPException(status_code=404, detail="条目不存在")
        if row["status"] != "pending":
            raise HTTPException(status_code=400, detail="该条目已审核")
        row = await conn.fetchrow(
            """UPDATE faq_items
               SET status=$2, reviewer=$3, comment=$4, updated_at=NOW()
               WHERE id=$1 RETURNING *""",
            draft_id, body.action, body.reviewer, body.comment
        )
    return _row_to_dict(row)
```

**Step 4: 注册路由到 `app.py`**

```python
from api.routers.faq import router as faq_router
# ...
app.include_router(faq_router)
```

**Step 5: 更新 `.env.example`**

```
FAQ_REVIEW_PASSWORD=your_review_password
```

**Step 6: 运行测试确认通过**

```bash
source .venv/bin/activate && pytest tests/test_faq_api.py -v
```

**Step 7: Commit**

```bash
git add api/routers/faq.py tests/test_faq_api.py app.py .env.example
git commit -m "feat: add FAQ CRUD API with review and password protection"
```

---

## Task 4: 生成 Markdown 文件 + git commit

**Files:**
- Create: `api/services/faq_publisher.py`
- Modify: `api/routers/faq.py`（新增 publish 接口）
- Modify: `app.py`（注册定时任务）

**Step 1: 实现 `api/services/faq_publisher.py`**

```python
"""Generate FAQ markdown files from approved DB entries and git commit."""
import logging
import subprocess
from pathlib import Path

from api.constants import AGENT_CWD
from api.db import get_faq_pool

logger = logging.getLogger(__name__)

KB_DIR = AGENT_CWD / ".claude" / "skills" / "issue-diagnosis" / "kb"

FAQ_CATEGORIES = [
    "开票", "收票", "鉴权登录", "接口参数", "进项发票采集", "性能超时", "faq-newtimeai-invoice"
]

CATEGORY_HEADERS = {
    "开票": "# 开票类 FAQ\n\n> 涵盖：发票开具失败、开票报错、票种问题、开票状态异常、权益配置等。",
    "收票": "# 收票类 FAQ",
    "鉴权登录": "# 鉴权登录类 FAQ",
    "接口参数": "# 接口参数类 FAQ",
    "进项发票采集": "# 进项发票采集类 FAQ",
    "性能超时": "# 性能超时类 FAQ",
    "faq-newtimeai-invoice": "# 新时代通道发票 FAQ",
}


def _faq_filename(category: str) -> str:
    if category == "faq-newtimeai-invoice":
        return "faq-newtimeai-invoice.md"
    return f"{category}-faq.md"


async def publish_category(category: str) -> dict:
    """Regenerate one category's FAQ md file from approved DB entries."""
    pool = await get_faq_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM faq_items WHERE category=$1 AND status='approved' ORDER BY id",
            category
        )

    faq_file = KB_DIR / _faq_filename(category)
    if not faq_file.exists():
        return {"category": category, "ok": False, "error": f"文件不存在：{faq_file.name}"}

    header = CATEGORY_HEADERS.get(category, f"# {category} FAQ")
    lines = [header, "\n\n---\n"]
    for i, row in enumerate(rows, start=1):
        lines.append(f"\n## Q{i}: {row['question']}\n\n{row['answer']}\n\n---\n")

    # 保留文件末尾的"新时代通道日志分析"等固定 section
    original = faq_file.read_text(encoding="utf-8")
    marker = "\n## 新时代通道日志分析"
    suffix = ""
    if marker in original:
        suffix = original[original.index(marker):]

    content = "".join(lines) + suffix
    faq_file.write_text(content, encoding="utf-8")

    # 更新 published_at
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE faq_items SET published_at=NOW() WHERE category=$1 AND status='approved'",
            category
        )

    return {"category": category, "ok": True, "count": len(rows)}


async def publish_all() -> list[dict]:
    """Regenerate all FAQ md files and git commit."""
    results = []
    changed_files = []

    for category in FAQ_CATEGORIES:
        result = await publish_category(category)
        results.append(result)
        if result["ok"]:
            changed_files.append(str(KB_DIR / _faq_filename(category)))

    if changed_files:
        _git_commit(changed_files)

    return results


def _git_commit(files: list[str]):
    repo_root = KB_DIR
    try:
        subprocess.run(["git", "add"] + files, cwd=str(repo_root), check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "docs: regenerate FAQ markdown files from approved entries"],
            cwd=str(repo_root), check=True, capture_output=True
        )
        logger.info("FAQ markdown files committed")
    except subprocess.CalledProcessError as e:
        logger.warning("git commit failed: %s", e.stderr)
```

**Step 2: 在 `api/routers/faq.py` 新增 publish 接口**

```python
from api.services.faq_publisher import publish_all, publish_category as _publish_category

class PublishRequest(BaseModel):
    password: str
    category: str = ""  # 空表示全部


@router.post("/publish")
async def publish_faq(body: PublishRequest):
    _check_password(body.password)
    if body.category:
        if body.category not in FAQ_CATEGORIES:
            raise HTTPException(status_code=400, detail="无效分类")
        from api.services.faq_publisher import _git_commit
        result = await _publish_category(body.category)
        if result["ok"]:
            from api.constants import AGENT_CWD
            kb_dir = AGENT_CWD / ".claude" / "skills" / "issue-diagnosis" / "kb"
            faq_file = kb_dir / (body.category + "-faq.md" if body.category != "faq-newtimeai-invoice" else "faq-newtimeai-invoice.md")
            _git_commit([str(faq_file)])
        return result
    results = await publish_all()
    return {"results": results}
```

**Step 3: 在 `app.py` 注册定时发布任务（可选，默认关闭）**

在 `lifespan` 的 scheduler 配置区域添加：

```python
if os.getenv("FAQ_AUTO_PUBLISH", "false").lower() in ("1", "true", "yes"):
    from api.services.faq_publisher import publish_all as _faq_publish_all
    async def _run_faq_publish():
        try:
            results = await _faq_publish_all()
            logger.info("FAQ auto-publish: %s", results)
        except Exception:
            logger.exception("FAQ auto-publish failed")
    faq_interval = int(os.getenv("FAQ_PUBLISH_INTERVAL_HOURS", "24"))
    scheduler.add_job(_run_faq_publish, "interval", hours=faq_interval, id="faq_publish")
    logger.info("FAQ auto-publish scheduled every %d hours", faq_interval)
```

**Step 4: 更新 `.env.example`**

```
FAQ_AUTO_PUBLISH=false
FAQ_PUBLISH_INTERVAL_HOURS=24
```

**Step 5: Commit**

```bash
git add api/services/faq_publisher.py api/routers/faq.py app.py .env.example
git commit -m "feat: add FAQ markdown publisher with manual trigger and optional scheduler"
```

---

## Task 5: 前端 Vue3 项目初始化

**Files:**
- Create: `frontend/` 目录（Vue3 + Vite 项目）
- Modify: `.gitignore`

**Step 1: 初始化项目**

```bash
cd /Users/jinfan/code/get-master/agent-harness
npm create vite@latest frontend -- --template vue
cd frontend && npm install
npm install element-plus @element-plus/icons-vue axios
```

**Step 2: 配置 `frontend/vite.config.js`**

```js
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  base: '/static/faq/',
  build: {
    outDir: '../static/faq',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/api': 'http://localhost:9090',
    },
  },
})
```

**Step 3: 更新 `.gitignore`**

追加：
```
# FAQ 前端构建产物
static/faq/
```

**Step 4: Commit 前端源码骨架**

```bash
git add frontend/ .gitignore
git commit -m "feat: init Vue3 frontend skeleton for FAQ editor"
```

---

## Task 6: 前端页面实现

**Files:**
- Modify: `frontend/src/main.js`
- Create: `frontend/src/api.js`
- Create: `frontend/src/App.vue`
- Create: `frontend/src/components/SubmitForm.vue`
- Create: `frontend/src/components/ReviewList.vue`
- Create: `frontend/src/components/HistoryList.vue`
- Create: `frontend/src/components/PublishPanel.vue`

**Step 1: `frontend/src/main.js`**

```js
import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import App from './App.vue'

const app = createApp(App)
app.use(ElementPlus)
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}
app.mount('#app')
```

**Step 2: `frontend/src/api.js`**

```js
import axios from 'axios'

const http = axios.create({ baseURL: '/api/faq' })

export const getCategories = () => http.get('/categories')
export const getDrafts = (params = {}) => http.get('/drafts', { params })
export const submitDraft = (data) => http.post('/drafts', data)
export const updateDraft = (id, data) => http.put(`/drafts/${id}`, data)
export const deleteDraft = (id, password) => http.delete(`/drafts/${id}`, { params: { password } })
export const reviewDraft = (id, data) => http.post(`/drafts/${id}/review`, data)
export const publishFaq = (data) => http.post('/publish', data)
```

**Step 3: `frontend/src/App.vue`**

```vue
<template>
  <div style="max-width: 1000px; margin: 40px auto; padding: 0 20px">
    <h2 style="margin-bottom: 20px">FAQ 录入与审核</h2>
    <el-tabs v-model="activeTab">
      <el-tab-pane label="录入 FAQ" name="submit">
        <SubmitForm :categories="categories" />
      </el-tab-pane>
      <el-tab-pane label="审核队列" name="review">
        <ReviewList v-if="activeTab === 'review'" :categories="categories" />
      </el-tab-pane>
      <el-tab-pane label="历史记录" name="history">
        <HistoryList v-if="activeTab === 'history'" :categories="categories" />
      </el-tab-pane>
      <el-tab-pane label="发布 MD" name="publish">
        <PublishPanel v-if="activeTab === 'publish'" :categories="categories" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getCategories } from './api'
import SubmitForm from './components/SubmitForm.vue'
import ReviewList from './components/ReviewList.vue'
import HistoryList from './components/HistoryList.vue'
import PublishPanel from './components/PublishPanel.vue'

const activeTab = ref('submit')
const categories = ref([])
onMounted(async () => {
  const { data } = await getCategories()
  categories.value = data.categories
})
</script>
```

**Step 4: `frontend/src/components/SubmitForm.vue`**

```vue
<template>
  <el-form :model="form" label-width="90px" style="max-width: 700px; margin-top: 16px">
    <el-form-item label="分类">
      <el-select v-model="form.category" placeholder="选择分类">
        <el-option v-for="c in categories" :key="c" :label="c" :value="c" />
      </el-select>
    </el-form-item>
    <el-form-item label="问题标题">
      <el-input v-model="form.question" placeholder="例：开票报错「非法字符」怎么处理？" />
    </el-form-item>
    <el-form-item label="答案内容">
      <el-input v-model="form.answer" type="textarea" :rows="8"
        placeholder="详细描述原因和解决步骤，支持 Markdown..." />
    </el-form-item>
    <el-form-item label="提交人">
      <el-input v-model="form.submitter" placeholder="你的姓名" style="width: 200px" />
    </el-form-item>
    <el-form-item>
      <el-button type="primary" :loading="loading" @click="submit">提交审核</el-button>
    </el-form-item>
  </el-form>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { submitDraft } from '../api'

const props = defineProps({ categories: Array })
const loading = ref(false)
const form = ref({ category: '', question: '', answer: '', submitter: '' })

async function submit() {
  const { category, question, answer, submitter } = form.value
  if (!category || !question || !answer || !submitter) {
    ElMessage.warning('请填写所有字段'); return
  }
  loading.value = true
  try {
    await submitDraft(form.value)
    ElMessage.success('提交成功，等待审核！')
    form.value = { category: '', question: '', answer: '', submitter: '' }
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '提交失败')
  } finally {
    loading.value = false
  }
}
</script>
```

**Step 5: `frontend/src/components/ReviewList.vue`**

```vue
<template>
  <div style="margin-top: 16px">
    <el-empty v-if="!drafts.length" description="暂无待审核条目" />
    <el-card v-for="d in drafts" :key="d.id" style="margin-bottom: 16px">
      <template #header>
        <span style="font-weight:600">{{ d.question }}</span>
        <el-tag type="warning" size="small" style="margin-left:8px">待审核</el-tag>
        <span style="float:right;font-size:12px;color:#999">
          {{ d.category }} · {{ d.submitter }} · {{ d.created_at }}
        </span>
      </template>
      <pre style="white-space:pre-wrap;font-size:13px;margin:0 0 12px">{{ d.answer }}</pre>
      <el-row :gutter="8" align="middle">
        <el-col :span="5"><el-input v-model="d._reviewer" placeholder="审核人" size="small" /></el-col>
        <el-col :span="6"><el-input v-model="d._password" placeholder="审核密码" type="password" size="small" /></el-col>
        <el-col :span="7"><el-input v-model="d._comment" placeholder="备注（可选）" size="small" /></el-col>
        <el-col :span="6" style="display:flex;gap:6px">
          <el-button type="success" size="small" @click="doReview(d,'approve')">通过</el-button>
          <el-button type="danger" size="small" @click="doReview(d,'reject')">拒绝</el-button>
        </el-col>
      </el-row>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getDrafts, reviewDraft } from '../api'

const drafts = ref([])
onMounted(load)

async function load() {
  const { data } = await getDrafts({ status: 'pending' })
  drafts.value = data.drafts.map(d => ({ ...d, _reviewer: '', _password: '', _comment: '' }))
}

async function doReview(d, action) {
  if (!d._reviewer) { ElMessage.warning('请填写审核人姓名'); return }
  if (!d._password) { ElMessage.warning('请填写审核密码'); return }
  try {
    await reviewDraft(d.id, { action, reviewer: d._reviewer, password: d._password, comment: d._comment })
    ElMessage.success(action === 'approve' ? '已通过' : '已拒绝')
    await load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}
</script>
```

**Step 6: `frontend/src/components/HistoryList.vue`**

```vue
<template>
  <div style="margin-top:16px">
    <el-row :gutter="12" style="margin-bottom:16px">
      <el-col :span="6">
        <el-select v-model="filter.status" placeholder="状态" clearable @change="load">
          <el-option label="已通过" value="approve" />
          <el-option label="已拒绝" value="reject" />
        </el-select>
      </el-col>
      <el-col :span="6">
        <el-select v-model="filter.category" placeholder="分类" clearable @change="load">
          <el-option v-for="c in categories" :key="c" :label="c" :value="c" />
        </el-select>
      </el-col>
    </el-row>
    <el-empty v-if="!list.length" description="暂无记录" />
    <el-card v-for="d in list" :key="d.id" style="margin-bottom:12px">
      <template #header>
        <span style="font-weight:600">{{ d.question }}</span>
        <el-tag :type="d.status==='approve'?'success':'danger'" size="small" style="margin-left:8px">
          {{ d.status === 'approve' ? '已通过' : '已拒绝' }}
        </el-tag>
        <span style="float:right;font-size:12px;color:#999">
          {{ d.category }} · 提交：{{ d.submitter }} · 审核：{{ d.reviewer }} · {{ d.reviewed_at }}
        </span>
      </template>
      <pre style="white-space:pre-wrap;font-size:13px;margin:0">{{ d.answer }}</pre>
      <div v-if="d.comment" style="margin-top:8px;font-size:12px;color:#888">备注：{{ d.comment }}</div>
    </el-card>
    <el-pagination v-if="total>pageSize" layout="prev,pager,next" :total="total"
      :page-size="pageSize" v-model:current-page="page" @current-change="load" style="margin-top:16px" />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getDrafts } from '../api'

const props = defineProps({ categories: Array })
const filter = ref({ status: '', category: '' })
const list = ref([])
const page = ref(1)
const pageSize = 20
const total = ref(0)

onMounted(load)

async function load() {
  const params = { page: page.value, page_size: pageSize }
  if (filter.value.status) params.status = filter.value.status
  if (filter.value.category) params.category = filter.value.category
  const { data } = await getDrafts(params)
  list.value = data.drafts.filter(d => d.status !== 'pending')
  total.value = data.total
}
</script>
```

**Step 7: `frontend/src/components/PublishPanel.vue`**

```vue
<template>
  <div style="max-width:500px;margin-top:24px">
    <el-alert type="info" :closable="false" style="margin-bottom:20px"
      description="将数据库中已审核通过的 FAQ 重新生成对应 Markdown 文件并提交 git。" />
    <el-form label-width="90px">
      <el-form-item label="分类">
        <el-select v-model="form.category" placeholder="全部分类" clearable style="width:200px">
          <el-option v-for="c in categories" :key="c" :label="c" :value="c" />
        </el-select>
      </el-form-item>
      <el-form-item label="审核密码">
        <el-input v-model="form.password" type="password" style="width:200px" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :loading="loading" @click="publish">生成并提交 MD 文件</el-button>
      </el-form-item>
    </el-form>
    <el-table v-if="results.length" :data="results" style="margin-top:16px">
      <el-table-column prop="category" label="分类" />
      <el-table-column prop="count" label="条目数" width="80" />
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <el-tag :type="row.ok ? 'success' : 'danger'" size="small">
            {{ row.ok ? '成功' : '失败' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="error" label="错误信息" />
    </el-table>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { publishFaq } from '../api'

const props = defineProps({ categories: Array })
const loading = ref(false)
const form = ref({ category: '', password: '' })
const results = ref([])

async function publish() {
  if (!form.value.password) { ElMessage.warning('请填写审核密码'); return }
  loading.value = true
  try {
    const { data } = await publishFaq({ category: form.value.category, password: form.value.password })
    results.value = data.results || [data]
    ElMessage.success('生成完成')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '生成失败')
  } finally {
    loading.value = false
  }
}
</script>
```

**Step 8: 本地开发验证**

```bash
cd frontend && npm run dev
# 访问 http://localhost:5173
# 验证四个 Tab：录入、审核、历史、发布
```

**Step 9: Commit**

```bash
git add frontend/src/
git commit -m "feat: implement FAQ editor Vue3 frontend with 4 tabs"
```

---

## Task 7: 构建脚本

**Files:**
- Create: `scripts/build-faq-frontend.sh`

```bash
#!/bin/bash
set -e
cd "$(dirname "$0")/../frontend"
echo "Installing dependencies..."
npm install
echo "Building..."
npm run build
echo "Done. Output: static/faq/"
echo "Access: http://localhost:9090/static/faq/index.html"
```

```bash
chmod +x scripts/build-faq-frontend.sh
```

**构建并验证：**

```bash
./scripts/build-faq-frontend.sh
./run.sh
# 访问 http://localhost:9090/static/faq/index.html
```

**Commit:**

```bash
git add scripts/build-faq-frontend.sh
git commit -m "chore: add FAQ frontend build script"
```

---

## 完成标准

- [ ] `faq_items` 表自动创建
- [ ] CRUD 接口全部可用（提交/修改/删除/审核）
- [ ] 审核和删除需要密码，密码错误返回 403
- [ ] `POST /api/faq/publish` 生成 MD 文件并 git commit
- [ ] 定时发布可通过 `FAQ_AUTO_PUBLISH=true` 开启
- [ ] `static/faq/` 在 `.gitignore` 中
- [ ] 访问 `/static/faq/index.html` 四个 Tab 正常
- [ ] 所有后端测试通过

## 部署命令

```bash
./scripts/build-faq-frontend.sh && ./run.sh
```
