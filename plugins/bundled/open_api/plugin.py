"""Open API Channel Plugin 入口."""

import asyncio
import logging
import time
import uuid
from typing import Any, Dict, Optional

import httpx
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


def _safe_route(func):
    """捕获路由中未处理的异常，返回统一错误格式."""
    import functools

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except HTTPException:
            raise  # 交给 app 级 handler 处理
        except Exception as exc:
            logging.getLogger(__name__).error(f"[OpenAPI] Unhandled exception in {func.__name__}: {exc}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content=BaseResp(errcode="500000", description="服务内部错误，请稍后重试").model_dump(),
            )

    return wrapper


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
        self._async_tasks: Dict[str, Any] = {}  # task_id -> {result, done_at, created_at}
        self._task_ttl: int = self.config.get("async_task_ttl", 1800)
        self._task_pending_ttl: int = self.config.get("async_task_pending_ttl", 1800)
        self._cleanup_task: Any = None

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
            if (
                entry["result"].status != "PENDING"
                and now - (entry.get("done_at") or now) > self._task_ttl
            ) or (
                entry["result"].status == "PENDING"
                and now - entry.get("created_at", now) > self._task_pending_ttl
            )
        ]
        for tid in expired:
            del self._async_tasks[tid]
        if expired:
            logger.info(f"[OpenAPI] Cleaned {len(expired)} expired async tasks")

    def create_router(self) -> APIRouter:
        router = APIRouter(tags=["open-api"])
        handler = self.handler
        token_manager = self.token_manager

        @router.get("/open-api/get_token")
        @_safe_route
        async def get_token(
            appid: str = Query(...),
            create_time: str = Query(...),
            sign: str = Query(...),
        ):
            if not token_manager.verify_sign(appid, create_time, sign):
                return JSONResponse(content=BaseResp(
                    errcode="100001", description="签名验证失败"
                ).model_dump())
            token, expires_in = token_manager.generate_token()
            return BaseResp(data=TokenRespData(
                token=token, expires_in=str(expires_in)
            )).model_dump()

        @router.get("/open-api/ask/ask_init")
        @_safe_route
        async def ask_init(_token: str = Depends(self._require_token)):
            cid = uuid.uuid4().hex
            return BaseResp(data=InitRespData(ai_agent_cid=cid)).model_dump()

        @router.post("/open-api/ask/answer_no_stream")
        @_safe_route
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
        @_safe_route
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
            self._async_tasks[task_id] = {"result": result, "done_at": None, "created_at": time.time()}

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

                if req.callback_url:
                    try:
                        payload = BaseResp(data=result.model_dump()).model_dump()
                        async with httpx.AsyncClient(timeout=10) as client:
                            await client.post(req.callback_url, json=payload)
                        logger.info(f"[OpenAPI] Callback sent to {req.callback_url} for task {task_id}")
                    except Exception as e:
                        logger.error(f"[OpenAPI] Callback failed for task {task_id}: {e}")

            task = asyncio.create_task(_run())
            task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
            return BaseResp(data=AsyncAnswerRespData(
                task_id=task_id,
                ai_agent_cid=req.ai_agent_cid,
            )).model_dump()

        @router.get("/open-api/ask/answer_async/{task_id}")
        @_safe_route
        async def get_async_result(
            task_id: str,
            _token: str = Depends(self._require_token),
        ):
            entry = self._async_tasks.get(task_id)
            if not entry:
                return JSONResponse(content=BaseResp(
                    errcode="100002", description="任务不存在或已过期"
                ).model_dump())
            result = entry["result"]
            if result.status == "ERROR":
                return JSONResponse(
                    status_code=500,
                    content=BaseResp(
                        errcode="500001", description=result.answer or "任务处理失败，请重试"
                    ).model_dump(),
                )
            return BaseResp(data=result.model_dump()).model_dump()

        @router.post("/open-api/ask/end_session")
        @_safe_route
        async def end_session(
            req: EndSessionReq,
            _token: str = Depends(self._require_token),
        ):
            handler.remove_session(req.ai_agent_cid)
            return BaseResp(description="会话已结束").model_dump()

        @router.get("/open-api/stats")
        @_safe_route
        async def stats(_token: str = Depends(self._require_token)):
            return handler.get_stats()

        # ── Skill 版本管理 ────────────────────────────────────────────────────

        from api.services.skill_service import (
            get_managed_skills, format_version_key, parse_version_key,
            create_draft as _create_draft,
            update_draft as _update_draft,
            publish_draft as _publish_draft,
            rollback_to_version as _rollback_to_version,
        )
        from plugins.bundled.open_api.models import SkillFileIn, CreateDraftReq, UpdateDraftReq, RollbackReq

        def _check_managed(skill_name: str):
            if skill_name not in get_managed_skills():
                return JSONResponse(content=BaseResp(
                    errcode="100004", description=f"skill '{skill_name}' 不在受管理列表中"
                ).model_dump())

        def _fmt_version(row: dict) -> str:
            return format_version_key(row["skill_name"], row["version"])

        @router.get("/open-api/skills")
        @_safe_route
        async def list_skills(_token: str = Depends(self._require_token)):
            from api.db import skill_get_published, skill_get_files
            result = []
            for name in get_managed_skills():
                pub = await skill_get_published(name)
                if pub:
                    files = await skill_get_files(pub["id"])
                    result.append({
                        "skill_name": name,
                        "published_version": _fmt_version(pub),
                        "operator": pub["operator"],
                        "updated_at": pub["created_at"].isoformat() if pub["created_at"] else None,
                        "files": [{"filename": f["filename"], "filepath": f["filepath"]} for f in files],
                    })
                else:
                    result.append({
                        "skill_name": name,
                        "published_version": None,
                        "operator": None,
                        "updated_at": None,
                        "files": [],
                    })
            return BaseResp(data=result).model_dump()

        @router.get("/open-api/skills/{name}")
        @_safe_route
        async def get_skill(name: str, _token: str = Depends(self._require_token)):
            from api.db import skill_get_published, skill_get_files, skill_list_versions
            err = _check_managed(name)
            if err:
                return err
            pub = await skill_get_published(name)
            if not pub:
                return JSONResponse(content=BaseResp(
                    errcode="100005", description=f"skill '{name}' 尚无 published 版本"
                ).model_dump())
            files = await skill_get_files(pub["id"])
            versions = await skill_list_versions(name)
            data = {
                "skill_name": name,
                "published": {
                    "version": _fmt_version(pub),
                    "operator": pub["operator"],
                    "reason": pub["reason"],
                    "created_at": pub["created_at"].isoformat() if pub["created_at"] else None,
                    "files": [
                        {"filename": f["filename"], "filepath": f["filepath"], "content": f["content"]}
                        for f in files
                    ],
                },
                "history": [
                    {
                        "version": _fmt_version(v),
                        "status": v["status"],
                        "operator": v["operator"],
                        "reason": v["reason"],
                        "created_at": v["created_at"].isoformat() if v["created_at"] else None,
                    }
                    for v in versions
                ],
            }
            return BaseResp(data=data).model_dump()

        @router.get("/open-api/skills/{name}/drafts")
        @_safe_route
        async def list_drafts(name: str, _token: str = Depends(self._require_token)):
            from api.db import skill_list_drafts, skill_get_files
            err = _check_managed(name)
            if err:
                return err
            drafts = await skill_list_drafts(name)
            result = []
            for d in drafts:
                files = await skill_get_files(d["id"])
                result.append({
                    "version": _fmt_version(d),
                    "operator": d["operator"],
                    "reason": d["reason"],
                    "created_at": d["created_at"].isoformat() if d["created_at"] else None,
                    "files": [{"filename": f["filename"], "filepath": f["filepath"]} for f in files],
                })
            return BaseResp(data=result).model_dump()

        @router.post("/open-api/skills/{name}/drafts")
        @_safe_route
        async def create_draft_endpoint(name: str, body: CreateDraftReq, _token: str = Depends(self._require_token)):
            err = _check_managed(name)
            if err:
                return err
            files = [f.model_dump() for f in body.files] if body.files else None
            try:
                result = await _create_draft(skill_name=name, files=files, operator=body.operator, reason=body.reason)
            except Exception as e:
                return JSONResponse(content=BaseResp(errcode="400000", description=str(e)).model_dump())
            return BaseResp(data=result).model_dump()

        @router.put("/open-api/skills/{name}/drafts/{version}")
        @_safe_route
        async def update_draft_endpoint(name: str, version: str, body: UpdateDraftReq, _token: str = Depends(self._require_token)):
            err = _check_managed(name)
            if err:
                return err
            try:
                skill_name, version_num = parse_version_key(version)
                if skill_name != name:
                    return JSONResponse(content=BaseResp(errcode="400000", description="版本号中的 skill 名与路径不一致").model_dump())
                await _update_draft(skill_name=name, version_num=version_num, files=[f.model_dump() for f in body.files], operator=body.operator, reason=body.reason)
            except ValueError as e:
                return JSONResponse(content=BaseResp(errcode="400000", description=str(e)).model_dump())
            return BaseResp(description="更新成功").model_dump()

        @router.post("/open-api/skills/{name}/drafts/{version}/publish")
        @_safe_route
        async def publish_draft_endpoint(name: str, version: str, _token: str = Depends(self._require_token)):
            err = _check_managed(name)
            if err:
                return err
            try:
                skill_name, version_num = parse_version_key(version)
                if skill_name != name:
                    return JSONResponse(content=BaseResp(errcode="400000", description="版本号中的 skill 名与路径不一致").model_dump())
                await _publish_draft(skill_name=name, version_num=version_num)
            except ValueError as e:
                return JSONResponse(content=BaseResp(errcode="400000", description=str(e)).model_dump())
            return BaseResp(description=f"skill '{name}' 发布成功").model_dump()

        @router.post("/open-api/skills/{name}/rollback")
        @_safe_route
        async def rollback_endpoint(name: str, body: RollbackReq, _token: str = Depends(self._require_token)):
            err = _check_managed(name)
            if err:
                return err
            try:
                skill_name, version_num = parse_version_key(body.version)
                if skill_name != name:
                    return JSONResponse(content=BaseResp(errcode="400000", description="版本号中的 skill 名与路径不一致").model_dump())
                result = await _rollback_to_version(skill_name=name, target_version_num=version_num, operator=body.operator, reason=body.reason)
            except ValueError as e:
                return JSONResponse(content=BaseResp(errcode="400000", description=str(e)).model_dump())
            return BaseResp(data=result).model_dump()

        # ── Replay 回放重跑 ───────────────────────────────────────────────────

        from plugins.bundled.open_api.models import ReplayReq
        from plugins.bundled.open_api.replay import run_replay

        @router.post("/open-api/replay")
        @_safe_route
        async def replay_endpoint(body: ReplayReq, _token: str = Depends(self._require_token)):
            try:
                result = await run_replay(body, agent_service=self.api.agent_service)
            except ValueError as e:
                return JSONResponse(content=BaseResp(errcode="400000", description=str(e)).model_dump())
            return BaseResp(data=result).model_dump()

        return router

    async def send_text(self, recipient_id: str, text: str, context: Optional[Dict[str, Any]] = None) -> bool:
        return False

    async def on_start(self) -> None:
        self._cleanup_task = asyncio.create_task(self._background_cleanup())
        logger.info("[OpenAPI] Plugin started")

    async def on_stop(self) -> None:
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("[OpenAPI] Plugin stopped")

    async def _background_cleanup(self) -> None:
        while True:
            await asyncio.sleep(3600)
            self._cleanup_tasks()


def register(api: PluginAPI) -> OpenApiChannelPlugin:
    plugin = OpenApiChannelPlugin(api)
    router = plugin.create_router()
    api.register_router(router)
    logger.info("[OpenAPI] Plugin registered")
    return plugin
