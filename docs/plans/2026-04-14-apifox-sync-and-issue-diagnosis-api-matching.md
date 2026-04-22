# Apifox 接口文档同步 + Issue Diagnosis 接口匹配 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 定时从 Apifox 同步接口文档到 `agent_cwd/data/kb/接口文档/`，并在 issue-diagnosis skill 中新增接口匹配能力，当用户描述接口问题时精确定位到具体接口。

**Architecture:** 新增独立的 `api/services/apifox_sync.py` 模块负责拉取 Apifox 数据并写入 KB 文件；在 `app.py` 启动时用 APScheduler 注册定时任务；在 issue-diagnosis SKILL.md 中新增 Step 1.6 接口识别分支，读取 KB 中的接口文档做语义匹配后再进入后续诊断流程。

**Tech Stack:** Python, APScheduler, httpx, FastAPI lifespan, Markdown

---

## 前置说明

### Apifox API 鉴权
Apifox 开放 API 需要 Personal Access Token，通过 `Authorization: Bearer <token>` 传递。
- 获取方式：Apifox → 账号设置 → API 访问令牌
- 环境变量名：`APIFOX_TOKEN`
- 项目 ID 环境变量：`APIFOX_PROJECT_ID`（在 Apifox 项目 URL 中可见）

### 目录约定
- 同步输出目录：`agent_cwd/data/kb/接口文档/`
- 每个接口分组生成一个 Markdown 文件，如 `查验接口.md`、`开票接口.md`
- 同步元数据文件：`agent_cwd/data/kb/接口文档/_sync_meta.json`（记录上次同步时间）

---

## Task 1: 添加依赖并配置环境变量

**Files:**
- Modify: `requirements.txt`
- Modify: `.env.example`

**Step 1: 在 requirements.txt 添加依赖**

打开 `requirements.txt`，在末尾添加：
```
apscheduler>=3.10.0
httpx>=0.27.0
```

**Step 2: 在 .env.example 添加 Apifox 配置**

在 `.env.example` 末尾添加：
```bash
# ===========================================
# Apifox 接口文档同步
# ===========================================
# Apifox Personal Access Token（账号设置 → API 访问令牌）
APIFOX_TOKEN=your-apifox-token

# Apifox 项目 ID（项目 URL 中可见，如 https://app.apifox.com/project/123456）
APIFOX_PROJECT_ID=your-project-id

# 同步间隔（分钟，默认 60）
APIFOX_SYNC_INTERVAL_MINUTES=60
```

**Step 3: 安装依赖**

```bash
cd /Users/jinfan/code/get-master/agent-harness
source .venv/bin/activate && pip install apscheduler httpx
```

Expected: 安装成功，无报错

**Step 4: Commit**

```bash
git add requirements.txt .env.example
git commit -m "chore: add apscheduler and httpx for apifox sync"
```

---

## Task 2: 实现 Apifox 同步服务

**Files:**
- Create: `api/services/apifox_sync.py`
- Test: `tests/test_apifox_sync.py`

**Step 1: 写失败测试**

创建 `tests/test_apifox_sync.py`：

```python
"""Tests for Apifox sync service."""
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock


def test_build_api_headers():
    """测试请求头构建包含 Authorization"""
    from api.services.apifox_sync import ApifoxSyncService
    svc = ApifoxSyncService(token="test-token", project_id="123")
    headers = svc._build_headers()
    assert headers["Authorization"] == "Bearer test-token"
    assert headers["X-Apifox-Api-Version"] == "2024-01-20"


def test_format_endpoint_to_markdown():
    """测试单个接口格式化为 Markdown"""
    from api.services.apifox_sync import ApifoxSyncService
    svc = ApifoxSyncService(token="t", project_id="p")
    endpoint = {
        "name": "查验发票",
        "method": "POST",
        "path": "/api/v1/invoice/verify",
        "description": "查验发票真伪",
        "status": "released",
    }
    md = svc._format_endpoint(endpoint)
    assert "查验发票" in md
    assert "POST" in md
    assert "/api/v1/invoice/verify" in md


def test_group_name_sanitize():
    """测试分组名称中的特殊字符被清理"""
    from api.services.apifox_sync import ApifoxSyncService
    svc = ApifoxSyncService(token="t", project_id="p")
    assert svc._sanitize_filename("查验/接口") == "查验_接口"
    assert svc._sanitize_filename("开票 接口") == "开票_接口"
```

**Step 2: 运行测试确认失败**

```bash
cd /Users/jinfan/code/get-master/agent-harness
source .venv/bin/activate && python -m pytest tests/test_apifox_sync.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'api.services.apifox_sync'`

**Step 3: 实现 ApifoxSyncService**

创建 `api/services/apifox_sync.py`：

```python
"""Apifox API documentation sync service.

Fetches API endpoints from Apifox and writes them as Markdown files
into agent_cwd/data/kb/接口文档/ for use by issue-diagnosis skill.
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

from api.constants import DATA_DIR

logger = logging.getLogger(__name__)

KB_API_DOC_DIR = DATA_DIR / "kb" / "接口文档"
SYNC_META_FILE = KB_API_DOC_DIR / "_sync_meta.json"

APIFOX_BASE_URL = "https://api.apifox.com/v1"


class ApifoxSyncService:
    """Syncs API documentation from Apifox to local KB Markdown files."""

    def __init__(self, token: str, project_id: str):
        self.token = token
        self.project_id = project_id

    def _build_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "X-Apifox-Api-Version": "2024-01-20",
            "Content-Type": "application/json",
        }

    def _sanitize_filename(self, name: str) -> str:
        """Replace characters unsafe for filenames."""
        return re.sub(r'[\s/\\:*?"<>|]', "_", name)

    def _format_endpoint(self, endpoint: dict) -> str:
        """Format a single endpoint dict as a Markdown section."""
        name = endpoint.get("name", "未命名接口")
        method = (endpoint.get("method") or "").upper()
        path = endpoint.get("path", "")
        description = endpoint.get("description") or ""
        status = endpoint.get("status", "")

        lines = [
            f"### {name}",
            "",
            f"- **方法**: `{method}`",
            f"- **路径**: `{path}`",
        ]
        if status:
            lines.append(f"- **状态**: {status}")
        if description:
            lines.append(f"- **描述**: {description}")
        lines.append("")
        return "\n".join(lines)

    def _write_group_file(self, group_name: str, endpoints: list[dict]) -> Path:
        """Write a group's endpoints to a Markdown file, return the path."""
        KB_API_DOC_DIR.mkdir(parents=True, exist_ok=True)
        safe_name = self._sanitize_filename(group_name)
        file_path = KB_API_DOC_DIR / f"{safe_name}.md"

        lines = [
            f"# {group_name} 接口文档",
            "",
            f"> 自动同步自 Apifox，最后更新：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
        ]
        for ep in endpoints:
            lines.append(self._format_endpoint(ep))

        file_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info(f"Written {len(endpoints)} endpoints to {file_path}")
        return file_path

    def _update_sync_meta(self, synced_files: list[str]):
        KB_API_DOC_DIR.mkdir(parents=True, exist_ok=True)
        meta = {
            "last_sync": datetime.now().isoformat(),
            "files": synced_files,
        }
        SYNC_META_FILE.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    async def sync(self) -> dict:
        """
        Fetch all API groups and endpoints from Apifox, write to KB.
        Returns summary dict with counts.
        """
        async with httpx.AsyncClient(timeout=30) as client:
            # 1. 获取接口分组树
            resp = await client.get(
                f"{APIFOX_BASE_URL}/projects/{self.project_id}/api-tree-list",
                headers=self._build_headers(),
            )
            resp.raise_for_status()
            data = resp.json()

        tree = data.get("data", [])
        groups: dict[str, list[dict]] = {}
        self._flatten_tree(tree, groups, parent_name="")

        synced_files = []
        total_endpoints = 0
        for group_name, endpoints in groups.items():
            if not endpoints:
                continue
            path = self._write_group_file(group_name, endpoints)
            synced_files.append(path.name)
            total_endpoints += len(endpoints)

        self._update_sync_meta(synced_files)
        logger.info(f"Apifox sync complete: {len(synced_files)} groups, {total_endpoints} endpoints")
        return {"groups": len(synced_files), "endpoints": total_endpoints}

    def _flatten_tree(self, nodes: list, groups: dict, parent_name: str):
        """Recursively flatten Apifox tree into {group_name: [endpoints]}."""
        for node in nodes:
            node_type = node.get("type")
            name = node.get("name", "未分组")
            full_name = f"{parent_name}/{name}" if parent_name else name

            if node_type == "apiDetailFolder":
                children = node.get("children", [])
                self._flatten_tree(children, groups, full_name)
            elif node_type == "apiDetail":
                api = node.get("api", {})
                groups.setdefault(parent_name or "未分组", []).append({
                    "name": api.get("name", name),
                    "method": api.get("method", ""),
                    "path": api.get("path", ""),
                    "description": api.get("description", ""),
                    "status": api.get("status", ""),
                })


def create_sync_service() -> Optional[ApifoxSyncService]:
    """Create ApifoxSyncService from environment variables, return None if not configured."""
    token = os.getenv("APIFOX_TOKEN", "")
    project_id = os.getenv("APIFOX_PROJECT_ID", "")
    if not token or not project_id:
        logger.warning("APIFOX_TOKEN or APIFOX_PROJECT_ID not set, skipping Apifox sync")
        return None
    return ApifoxSyncService(token=token, project_id=project_id)
```

**Step 4: 运行测试确认通过**

```bash
source .venv/bin/activate && python -m pytest tests/test_apifox_sync.py -v
```

Expected: 3 tests PASS

**Step 5: Commit**

```bash
git add api/services/apifox_sync.py tests/test_apifox_sync.py
git commit -m "feat: add ApifoxSyncService to fetch and write API docs to KB"
```

---

## Task 3: 在 app.py 注册定时任务

**Files:**
- Modify: `app.py`
- Test: `tests/test_apifox_scheduler.py`

**Step 1: 写失败测试**

创建 `tests/test_apifox_scheduler.py`：

```python
"""Tests for Apifox scheduler registration."""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock


def test_create_sync_service_returns_none_without_env(monkeypatch):
    """未配置环境变量时 create_sync_service 返回 None"""
    monkeypatch.delenv("APIFOX_TOKEN", raising=False)
    monkeypatch.delenv("APIFOX_PROJECT_ID", raising=False)
    # 重新 import 确保 env 生效
    import importlib
    import api.services.apifox_sync as m
    importlib.reload(m)
    assert m.create_sync_service() is None


def test_create_sync_service_returns_instance_with_env(monkeypatch):
    """配置环境变量后 create_sync_service 返回实例"""
    monkeypatch.setenv("APIFOX_TOKEN", "tok")
    monkeypatch.setenv("APIFOX_PROJECT_ID", "pid")
    import importlib
    import api.services.apifox_sync as m
    importlib.reload(m)
    svc = m.create_sync_service()
    assert svc is not None
    assert svc.token == "tok"
    assert svc.project_id == "pid"
```

**Step 2: 运行测试确认通过**

```bash
source .venv/bin/activate && python -m pytest tests/test_apifox_scheduler.py -v
```

Expected: 2 tests PASS

**Step 3: 修改 app.py，添加 lifespan 定时任务**

读取 `app.py` 当前内容，在文件顶部 import 区域添加：

```python
from contextlib import asynccontextmanager
```

然后在 `app = FastAPI(...)` 之前插入 lifespan 函数，并将 `app = FastAPI(...)` 改为传入 `lifespan=lifespan`：

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    import asyncio
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from api.services.apifox_sync import create_sync_service

    scheduler = AsyncIOScheduler()
    sync_svc = create_sync_service()

    if sync_svc:
        interval_minutes = int(os.getenv("APIFOX_SYNC_INTERVAL_MINUTES", "60"))

        async def _run_sync():
            try:
                result = await sync_svc.sync()
                logger.info(f"Apifox sync result: {result}")
            except Exception:
                logger.exception("Apifox sync failed")

        # 启动时立即同步一次
        asyncio.create_task(_run_sync())
        scheduler.add_job(_run_sync, "interval", minutes=interval_minutes, id="apifox_sync")
        logger.info(f"Apifox sync scheduled every {interval_minutes} minutes")

    scheduler.start()
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(
    title="AI Agent Service",
    description="Generic AI agent service with skill-based extensibility",
    version="1.0.0",
    lifespan=lifespan,
)
```

**Step 4: 验证 app 能正常导入**

```bash
source .venv/bin/activate && python -c "from app import app; print('OK')"
```

Expected: 输出 `OK`，无报错

**Step 5: Commit**

```bash
git add app.py tests/test_apifox_scheduler.py
git commit -m "feat: register Apifox sync as APScheduler interval job on app startup"
```

---

## Task 4: 更新 issue-diagnosis SKILL.md，添加接口匹配步骤

**Files:**
- Modify: `agent_cwd/.claude/skills/issue-diagnosis/SKILL.md`

**Step 1: 在专项场景识别表格末尾追加接口匹配行**

找到 SKILL.md 中的专项场景识别表格，在 `进项发票采集任务` 那行之后追加：

```markdown
| 接口问题定位 | 用户提到接口名称（如"查验接口"、"开票接口"、"收票接口"）或接口路径，且 `data/kb/接口文档/` 目录存在 | 执行 Step 1.6 接口匹配 |
```

**Step 2: 在 Step 1.5 章节结束后插入 Step 1.6**

在 `## Step 1.5：Instinct 检索` 章节末尾（`继续 Step 2，按标准流程执行` 之后）插入：

```markdown
---

## Step 1.6：接口匹配（仅当用户描述含接口名称时执行）

**触发条件**：用户描述中含有接口名称关键词（如"查验接口"、"开票接口"、"收票接口"、"采集接口"等），且 `data/kb/接口文档/` 目录存在。

**执行步骤**：

1. 列出 `data/kb/接口文档/` 目录下所有 `.md` 文件（排除 `_sync_meta.json`）
2. 根据用户描述的关键词，选择最相关的 1-2 个文件读取
3. 在文件中搜索与用户描述最匹配的接口条目（按接口名称、路径、描述做语义匹配）
4. 将匹配到的接口信息（方法、路径、描述）作为上下文，带入后续 Step 3 日志查询：
   - 在 ELK 查询时，将接口路径作为额外关键词加入 `keywords`
   - 在 Step 6 输出结论时，注明"定位到接口：`{method} {path}`"

**未匹配到接口时**：继续 Step 2，不阻塞主流程。

**⚠️ 禁止**：不得因接口匹配失败而中断诊断流程；不得自行猜测接口路径（必须来自 KB 文件）。
```

**Step 3: 验证修改正确**

```bash
grep -n "Step 1.6" agent_cwd/.claude/skills/issue-diagnosis/SKILL.md
```

Expected: 输出包含 `Step 1.6` 的行号

**Step 4: Commit**

```bash
git add agent_cwd/.claude/skills/issue-diagnosis/SKILL.md
git commit -m "feat: add Step 1.6 API interface matching in issue-diagnosis skill"
```

---

## Task 5: 手动验证同步功能（需要真实 Apifox Token）

**Step 1: 配置 .env**

在 `.env` 文件中填入真实值：
```bash
APIFOX_TOKEN=<你的 Apifox Personal Access Token>
APIFOX_PROJECT_ID=<你的项目 ID>
```

**Step 2: 手动触发一次同步**

```bash
source .venv/bin/activate && python -c "
import asyncio, os
from dotenv import load_dotenv
load_dotenv('.env')
from api.services.apifox_sync import create_sync_service
svc = create_sync_service()
if svc:
    result = asyncio.run(svc.sync())
    print('Sync result:', result)
else:
    print('Service not configured - check APIFOX_TOKEN and APIFOX_PROJECT_ID in .env')
"
```

Expected: 输出 `Sync result: {'groups': N, 'endpoints': M}`，且 `agent_cwd/data/kb/接口文档/` 目录下生成 `.md` 文件

**Step 3: 检查生成的文件**

```bash
ls agent_cwd/data/kb/接口文档/
cat "agent_cwd/data/kb/接口文档/_sync_meta.json"
```

Expected: 看到各分组的 `.md` 文件和 `_sync_meta.json`

**Step 4: 验证 issue-diagnosis 接口匹配**

启动服务后，向 `/api/query` 发送：
```json
{
  "message": "查验接口报错了，返回参数不合法",
  "session_id": "test-001"
}
```

Expected: Agent 在诊断过程中读取 `data/kb/接口文档/` 并定位到查验相关接口路径，在结论中注明接口信息。

---

## 注意事项

1. **Apifox API 版本**：本计划使用 `X-Apifox-Api-Version: 2024-01-20`，如 Apifox 升级 API 版本需同步更新 `apifox_sync.py` 中的常量。
2. **定时任务冲突**：如果 `app.py` 已有 lifespan 定义，需合并而非替换，避免覆盖已有的启动逻辑。
3. **KB 文件写保护**：`agent_cwd/.claude/` 目录下的文件有写保护，`data/kb/` 目录不受此限制，可正常写入。
4. **接口文档更新频率**：默认 60 分钟同步一次，可通过 `APIFOX_SYNC_INTERVAL_MINUTES` 调整。
