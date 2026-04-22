# Open API Channel 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 新增一个对外开放的 API 渠道插件（open_api），供第三方系统对接，提供鉴权、会话管理和问答接口。

**Architecture:** 参照智齿开放平台接口规范（https://developer.zhichi.com/pages/eb5065/），以 FastAPI 插件形式实现，复用现有 PluginSessionMapper 做会话管理，异步问答通过 asyncio.create_task + 内存字典存储任务结果实现。Token 鉴权采用 appid + app_key + 时间戳 MD5 签名，生成的 token 存内存，有效期 24 小时。

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, asyncio, hashlib(MD5)

---

## 接口清单

| # | 方法 | 路径 | 说明 |
|---|------|------|------|
| 1 | GET  | `/open-api/get_token` | 鉴权，获取 token |
| 2 | GET  | `/open-api/ask/ask_init` | 初始化会话，获取 session_id (ai_agent_cid) |
| 3 | POST | `/open-api/ask/answer_no_stream` | 同步问答（非流式，等待结果返回） |
| 4 | POST | `/open-api/ask/answer_async` | 异步问答（立即返回 task_id，结果轮询） |
| 4b| GET  | `/open-api/ask/answer_async/{task_id}` | 轮询异步任务结果 |
| 5 | POST | `/open-api/ask/end_session` | 结束会话，销毁 session |

所有接口（除 get_token）需在 Header 携带 `token`。

---

## 目录结构

```
plugins/bundled/open_api/
├── __init__.py
├── plugin.json
├── plugin.py          # 插件入口，路由定义
├── models.py          # Pydantic 请求/响应模型
├── handler.py         # 问答处理逻辑（复用 zhichi handler 模式）
└── token_manager.py   # Token 生成与校验
```

---

## Task 1: 创建插件目录和 plugin.json

**Files:**
- Create: `plugins/bundled/open_api/__init__.py`
- Create: `plugins/bundled/open_api/plugin.json`

**Step 1: 创建 `__init__.py`（空文件）**

```python
# 空文件
```

**Step 2: 创建 `plugin.json`**

```json
{
  "id": "open_api",
  "name": "Open API Channel",
  "version": "1.0.0",
  "description": "对外开放 API 渠道，供第三方系统对接",
  "type": "channel",
  "entry_point": "plugin:register",
  "config_schema": {
    "type": "object",
    "properties": {
      "app_id": {
        "type": "string",
        "description": "接口凭证 ID"
      },
      "app_key": {
        "type": "string",
        "description": "接口密钥"
      },
      "session_timeout": {
        "type": "integer",
        "default": 3600,
        "description": "会话超时时间（秒）"
      },
      "default_skill": {
        "type": "string",
        "default": "customer-service",
        "description": "默认使用的 skill 名称"
      },
      "async_task_ttl": {
        "type": "integer",
        "default": 300,
        "description": "异步任务结果保留时间（秒）"
      }
    }
  }
}
```

**Step 3: 在 `plugins/config.json` 中启用插件**

在 `enabled` 数组加入 `"open_api"`，在 `plugins` 对象加入：

```json
"open_api": {
  "app_id": "your_app_id",
  "app_key": "your_app_key",
  "session_timeout": 3600,
  "default_skill": "customer-service",
  "async_task_ttl": 300
}
```

---

## Task 2: 创建 token_manager.py

**Files:**
- Create: `plugins/bundled/open_api/token_manager.py`

Token 逻辑：
- 签名：`md5(appid + create_time + app_key)`
- 生成 token：`md5(appid + create_time + app_key + random_uuid)`，有效期 86400 秒
- 内存存储：`{token: expires_at}`

```python
"""Open API Token 管理器."""

import hashlib
import logging
import time
import uuid
from typing import Dict

logger = logging.getLogger(__name__)

TOKEN_EXPIRE_SECONDS = 86400


class TokenManager:
    def __init__(self, app_id: str, app_key: str):
        self.app_id = app_id
        self.app_key = app_key
        self._tokens: Dict[str, float] = {}  # token -> expires_at

    def _sign(self, create_time: str) -> str:
        raw = self.app_id + create_time + self.app_key
        return hashlib.md5(raw.encode()).hexdigest()

    def verify_sign(self, appid: str, create_time: str, sign: str) -> bool:
        if appid != self.app_id:
            return False
        return self._sign(create_time) == sign

    def generate_token(self) -> tuple[str, int]:
        """生成新 token，返回 (token, expires_in)."""
        self._cleanup_expired()
        raw = self.app_id + str(time.time()) + self.app_key + str(uuid.uuid4())
        token = hashlib.md5(raw.encode()).hexdigest()
        self._tokens[token] = time.time() + TOKEN_EXPIRE_SECONDS
        return token, TOKEN_EXPIRE_SECONDS

    def is_valid(self, token: str) -> bool:
        expires_at = self._tokens.get(token)
        if not expires_at:
            return False
        if time.time() > expires_at:
            del self._tokens[token]
            return False
        return True

    def _cleanup_expired(self) -> None:
        now = time.time()
        expired = [t for t, exp in self._tokens.items() if now > exp]
        for t in expired:
            del self._tokens[t]
```

---

## Task 3: 创建 models.py

**Files:**
- Create: `plugins/bundled/open_api/models.py`

```python
"""Open API 请求/响应数据模型."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class BaseResp(BaseModel):
    ret_code: str = "000000"
    ret_msg: str = "操作成功"
    data: Optional[Any] = None


class TokenRespData(BaseModel):
    token: str
    expires_in: str  # 秒数字符串，与智齿文档一致


class InitRespData(BaseModel):
    ai_agent_cid: str
    biz_type: str = "AI_AGENT"


class AnswerReq(BaseModel):
    question: str
    ai_agent_cid: str
    uid: Optional[str] = None
    user_name: Optional[str] = None
    show_question: Optional[str] = None
    msg_type: Optional[str] = "TEXT"
    params: Optional[Dict[str, Any]] = None


class AnswerRespItem(BaseModel):
    answer: str
    robot_answer_type: str = "QA_DIRECT"
    robot_answer_message_type: str = "MESSAGE"
    ai_agent_cid: str
    roundid: Optional[str] = None
    transfer_result: Optional[str] = None


class AsyncAnswerRespData(BaseModel):
    task_id: str
    ai_agent_cid: str
    status: str = "PENDING"


class AsyncTaskResult(BaseModel):
    task_id: str
    status: str  # PENDING | DONE | ERROR
    ai_agent_cid: Optional[str] = None
    answer: Optional[str] = None
    robot_answer_type: str = "QA_DIRECT"
    transfer_result: Optional[str] = None


class EndSessionReq(BaseModel):
    ai_agent_cid: str
```

---

## Task 4: 创建 handler.py

**Files:**
- Create: `plugins/bundled/open_api/handler.py`

复用 zhichi handler 核心逻辑，去掉智齿特有字段。

```python
"""Open API 消息处理器."""

import json
import logging

from api.models.requests import QueryRequest
from api.plugins.session_mapper import PluginSessionMapper
from api.services.agent_service import AgentService
from api.services.session_service import SessionService

from plugins.bundled.open_api.models import AnswerReq

logger = logging.getLogger(__name__)


class OpenApiHandler:
    def __init__(self, agent_service: AgentService, session_service: SessionService, config: dict):
        self.agent_service = agent_service
        self.session_service = session_service
        self.default_skill = config.get("default_skill", "customer-service")
        self.session_mapper = PluginSessionMapper(
            timeout_seconds=config.get("session_timeout", 3600),
            channel_id="open_api",
        )

    async def get_answer(self, req: AnswerReq) -> tuple[str, bool]:
        """同步问答，返回 (answer, is_transfer)."""
        cid = req.ai_agent_cid
        self.session_mapper.cleanup_expired()
        agent_session_id = self.session_mapper.get_or_create(cid)

        prompt = req.question
        if agent_session_id:
            pending = self.session_mapper.get_and_clear_pending_questions(cid)
            if pending:
                prompt = f"用户回答: {req.question}\n请根据用户的回答继续处理。"

        request = QueryRequest(
            prompt=prompt,
            skill=self.default_skill,
            tenant_id="open_api",
            language="中文",
            session_id=agent_session_id,
        )

        answer = "抱歉，处理您的问题时出现错误，请稍后再试。"
        is_transfer = False

        async for event in self.agent_service.process_query(request):
            event_type = event.get("event")

            if event_type == "session_created":
                data = json.loads(event["data"])
                self.session_mapper.update_activity(cid, data["session_id"])

            elif event_type == "transfer_human":
                data = json.loads(event["data"])
                answer = data.get("reason", "正在为您转接人工客服，请稍候。")
                is_transfer = True
                break

            elif event_type == "ask_user_question":
                data = json.loads(event["data"])
                questions = data.get("questions", [])
                self.session_mapper.set_pending_questions(cid, questions)
                if agent_session_id:
                    await self.session_service.interrupt(agent_session_id)
                if questions:
                    q = questions[0]
                    lines = [q.get("question", "请选择"), ""]
                    for i, opt in enumerate(q.get("options", []), 1):
                        lines.append(f"{i}. {opt.get('label', '')}")
                    answer = "\n".join(lines)
                break

            elif event_type == "result":
                data = json.loads(event.get("data", "{}"))
                answer = data.get("result", answer)

            elif event_type == "error":
                data = json.loads(event.get("data", "{}"))
                answer = f"抱歉，处理时出现错误：{data.get('message', '未知错误')}"
                break

        return answer, is_transfer

    def remove_session(self, cid: str) -> None:
        self.session_mapper.remove(cid)

    def get_stats(self) -> dict:
        return self.session_mapper.get_stats()
```

---

## Task 5: 创建 plugin.py

**Files:**
- Create: `plugins/bundled/open_api/plugin.py`

关键设计：
- Token 校验通过 `Depends` 注入
- 异步任务用 `asyncio.create_task` 后台执行，结果存 `_async_tasks` 字典
- 任务完成后记录 `_done_at`，TTL 到期后清理

```python
"""Open API Channel Plugin 入口."""

import asyncio
import logging
import time
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import JSONResponse

from api.plugins.api import PluginAPI
from api.plugins.channel import ChannelCapabilities, ChannelMeta, ChannelPlugin

from plugins.bundled.open_api.handler import OpenApiHandler
from plugins.bundled.open_api.models import (
    AnswerReq,
    AnswerRespItem,
    AsyncAnswerRespData,
    AsyncTaskResult,
    BaseResp,
    EndSessionReq,
    InitRespData,
    TokenRespData,
)
from plugins.bundled.open_api.token_manager import TokenManager

logger = logging.getLogger(__name__)


class OpenApiChannelPlugin(ChannelPlugin):
    def __init__(self, api: PluginAPI):
        self.api = api
        self.config = api.config
        self.token_manager = TokenManager(
            app_id=self.config.get("app_id", ""),
            app_key=self.config.get("app_key", ""),
        )
        self.handler = OpenApiHandler(
            agent_service=api.agent_service,
            session_service=api.session_service,
            config=self.config,
        )
        self._async_tasks: Dict[str, Any] = {}  # task_id -> {result, done_at}
        self._task_ttl: int = self.config.get("async_task_ttl", 300)

    def get_meta(self) -> ChannelMeta:
        return ChannelMeta(
            id="open_api",
            name="Open API Channel",
            webhook_path="/open-api",
            description="对外开放 API 渠道",
        )

    def get_capabilities(self) -> ChannelCapabilities:
        return ChannelCapabilities(
            send_text=False,
            send_images=False,
            send_cards=False,
            receive_webhook=True,
            session_management=True,
            transfer_human=False,
        )

    def _require_token(self, token: Optional[str] = Header(None)) -> str:
        if not token or not self.token_manager.is_valid(token):
            raise HTTPException(status_code=401, detail="token 无效或已过期")
        return token

    def _cleanup_tasks(self) -> None:
        now = time.time()
        expired = [
            tid for tid, entry in self._async_tasks.items()
            if entry["result"].status != "PENDING"
            and now - entry.get("done_at", now) > self._task_ttl
        ]
        for tid in expired:
            del self._async_tasks[tid]

    def create_router(self) -> APIRouter:
        router = APIRouter(tags=["open-api"])
        handler = self.handler
        token_manager = self.token_manager

        @router.get("/open-api/get_token")
        async def get_token(
            appid: str = Query(...),
            create_time: str = Query(...),
            sign: str = Query(...),
        ):
            if not token_manager.verify_sign(appid, create_time, sign):
                return JSONResponse(content=BaseResp(
                    ret_code="100001", ret_msg="签名验证失败"
                ).model_dump())
            token, expires_in = token_manager.generate_token()
            return BaseResp(data=TokenRespData(
                token=token, expires_in=str(expires_in)
            )).model_dump()

        @router.get("/open-api/ask/ask_init")
        async def ask_init(_token: str = Depends(self._require_token)):
            cid = uuid.uuid4().hex
            return BaseResp(data=InitRespData(ai_agent_cid=cid)).model_dump()

        @router.post("/open-api/ask/answer_no_stream")
        async def answer_no_stream(
            req: AnswerReq,
            _token: str = Depends(self._require_token),
        ):
            answer, is_transfer = await handler.get_answer(req)
            item = AnswerRespItem(
                answer=answer,
                ai_agent_cid=req.ai_agent_cid,
                transfer_result="TRANSFER" if is_transfer else "NO_ACTION",
            )
            return BaseResp(data=[item.model_dump()]).model_dump()

        @router.post("/open-api/ask/answer_async")
        async def answer_async(
            req: AnswerReq,
            _token: str = Depends(self._require_token),
        ):
            self._cleanup_tasks()
            task_id = uuid.uuid4().hex
            result = AsyncTaskResult(
                task_id=task_id,
                status="PENDING",
                ai_agent_cid=req.ai_agent_cid,
            )
            self._async_tasks[task_id] = {"result": result, "done_at": None}

            async def _run():
                try:
                    answer, is_transfer = await handler.get_answer(req)
                    result.answer = answer
                    result.transfer_result = "TRANSFER" if is_transfer else "NO_ACTION"
                    result.status = "DONE"
                except Exception as e:
                    logger.error(f"[OpenAPI] Async task {task_id} failed: {e}")
                    result.answer = "处理失败，请重试"
                    result.status = "ERROR"
                self._async_tasks[task_id]["done_at"] = time.time()

            asyncio.create_task(_run())
            return BaseResp(data=AsyncAnswerRespData(
                task_id=task_id,
                ai_agent_cid=req.ai_agent_cid,
            )).model_dump()

        @router.get("/open-api/ask/answer_async/{task_id}")
        async def get_async_result(
            task_id: str,
            _token: str = Depends(self._require_token),
        ):
            entry = self._async_tasks.get(task_id)
            if not entry:
                return JSONResponse(content=BaseResp(
                    ret_code="100002", ret_msg="任务不存在或已过期"
                ).model_dump())
            return BaseResp(data=entry["result"].model_dump()).model_dump()

        @router.post("/open-api/ask/end_session")
        async def end_session(
            req: EndSessionReq,
            _token: str = Depends(self._require_token),
        ):
            handler.remove_session(req.ai_agent_cid)
            return BaseResp(ret_msg="会话已结束").model_dump()

        @router.get("/open-api/stats")
        async def stats(_token: str = Depends(self._require_token)):
            return handler.get_stats()

        return router

    async def send_text(self, recipient_id: str, text: str, context=None) -> bool:
        return False

    async def on_start(self) -> None:
        logger.info("[OpenAPI] Plugin started")

    async def on_stop(self) -> None:
        logger.info("[OpenAPI] Plugin stopped")


def register(api: PluginAPI) -> OpenApiChannelPlugin:
    plugin = OpenApiChannelPlugin(api)
    router = plugin.create_router()
    api.register_router(router)
    logger.info("[OpenAPI] Plugin registered")
    return plugin
```

---

## Task 6: 更新 plugins/config.json

**Files:**
- Modify: `plugins/config.json`

在 `enabled` 加入 `"open_api"`，在 `plugins` 加入：

```json
"open_api": {
  "app_id": "your_app_id",
  "app_key": "your_app_key",
  "session_timeout": 3600,
  "default_skill": "customer-service",
  "async_task_ttl": 300
}
```

---

## Task 7: 验证

**Step 1: 启动服务**
```bash
./run.sh start
```

**Step 2: 获取 token**
```bash
# 计算签名：md5(appid + create_time + app_key)
python3 -c "
import hashlib, time
appid = 'your_app_id'
app_key = 'your_app_key'
ts = str(int(time.time()))
sign = hashlib.md5((appid + ts + app_key).encode()).hexdigest()
print(f'create_time={ts}')
print(f'sign={sign}')
"
curl "http://localhost:8000/open-api/get_token?appid=your_app_id&create_time=<ts>&sign=<sign>"
```

**Step 3: 初始化会话**
```bash
curl -H "token: <token>" "http://localhost:8000/open-api/ask/ask_init"
```

**Step 4: 同步问答**
```bash
curl -X POST -H "token: <token>" -H "Content-Type: application/json" \
  -d '{"question":"你好","ai_agent_cid":"<cid>"}' \
  http://localhost:8000/open-api/ask/answer_no_stream
```

**Step 5: 异步问答**
```bash
# 发起任务
curl -X POST -H "token: <token>" -H "Content-Type: application/json" \
  -d '{"question":"你好","ai_agent_cid":"<cid>"}' \
  http://localhost:8000/open-api/ask/answer_async

# 轮询结果（status: PENDING -> DONE）
curl -H "token: <token>" http://localhost:8000/open-api/ask/answer_async/<task_id>
```

**Step 6: 结束会话**
```bash
curl -X POST -H "token: <token>" -H "Content-Type: application/json" \
  -d '{"ai_agent_cid":"<cid>"}' \
  http://localhost:8000/open-api/ask/end_session
```

---

## 注意事项

1. **app_id / app_key** 在 `plugins/config.json` 中配置，不要硬编码
2. **异步任务结果** 存内存，服务重启后丢失，TTL 默认 300 秒
3. **Token** 存内存，服务重启后失效，客户端需重新获取
4. **ask_init** 只生成 cid，不预创建 agent session；agent session 在首次问答时由 AgentService 创建
5. **签名时间戳** 不做时效校验，如需防重放可加 ±5 分钟窗口校验
