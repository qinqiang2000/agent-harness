"""Main FastAPI application for AI Agent Service."""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv('.env')

# ── 日志配置（必须在任何 getLogger 调用之前）──────────────────────────────────
log_level = os.getenv('LOG_LEVEL', 'DEBUG')

_orig_factory = logging.getLogRecordFactory()


def _record_factory(*args, **kwargs):
    record = _orig_factory(*args, **kwargs)
    record.trace = "[rid=- sid=-]"
    return record


logging.setLogRecordFactory(_record_factory)


class _TraceFilter(logging.Filter):
    """将当前异步上下文的 rid/sid 注入每条日志 record。"""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            from api.utils.perf_timer import _current_timer, get_session_id
            timer = _current_timer.get()
            rid = timer.request_id if timer else "-"
            sid = get_session_id() or "-"
            record.trace = f"[rid={rid} sid={sid}]"
        except Exception:
            pass
        return True


logging.basicConfig(
    level=getattr(logging, log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(trace)s %(message)s'
)
_root = logging.getLogger()
_root.setLevel(getattr(logging, log_level.upper()))
_fmt = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(trace)s %(message)s')
_trace_filter = _TraceFilter()
if not _root.handlers:
    _root.addHandler(logging.StreamHandler())
for _h in _root.handlers:
    _h.setFormatter(_fmt)
    _h.addFilter(_trace_filter)
logging.getLogger("httpx").setLevel(logging.WARNING)
# ─────────────────────────────────────────────────────────────────────────────

logger = logging.getLogger(__name__)

# Patch claude_agent_sdk to tolerate missing 'signature' in thinking blocks
# (DeepSeek returns thinking blocks without this Anthropic-specific field)
try:
    from claude_agent_sdk._internal import message_parser as _mp
    _orig_parse = _mp.parse_message

    def _patched_parse(data):
        if isinstance(data, dict) and data.get("type") == "assistant":
            msg = data.get("message", {})
            for block in msg.get("content", []):
                if block.get("type") == "thinking":
                    sig = block.get("signature")
                    logger.debug(
                        f"[SDK patch] thinking block signature={'<missing>' if sig is None else repr(sig[:20]) if sig else '<empty>'}"
                    )
                    if sig is None:
                        block["signature"] = ""
        return _orig_parse(data)

    _mp.parse_message = _patched_parse
    logger.info("[SDK patch] message_parser patched for missing thinking signature")
except Exception as e:
    logger.warning(f"[SDK patch] failed to patch message_parser: {e}")

# Import after logging is configured
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import Message
from api.routers.agent import router
from api.routers.plugins import router as plugins_router
from api.routers.diagnosis import router as diagnosis_router
from api.constants import DATA_DIR, AGENT_CWD

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    import asyncio
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from api.dependencies import get_config_service, get_plugin_manager
    from api.services.apifox_sync import create_sync_services

    # uvicorn 在 app 启动后才完成自己的 handler 注册，这里统一补齐 formatter 和 filter
    _root = logging.getLogger()
    for _h in _root.handlers:
        _h.setFormatter(_fmt)
        if not any(isinstance(f, _TraceFilter) for f in _h.filters):
            _h.addFilter(_trace_filter)

    logger.info("Starting AI Agent Service")
    logger.info(f"Python process directory: {Path.cwd()}")
    logger.info(f"Agent working directory: {AGENT_CWD}")

    config_service = get_config_service()
    current_config = config_service.get_current_config()
    logger.info(f"Active model config: {config_service.get_current_config_name()}")
    logger.info(f"  - Base URL: {current_config.base_url}")
    logger.info(f"  - Model: {current_config.model or 'Default'}")

    # Initialize plugin system
    plugin_manager = get_plugin_manager()
    await plugin_manager.load_all(app)

    # 初始化 SDK 会话缓存
    from api.services.sdk_pool import init_cache
    cache = init_cache()
    await cache.start()

    # 初始化 FAQ 数据库表
    try:
        from api.db import init_faq_table, close_faq_pool
        await init_faq_table()
        logger.info("FAQ table initialized")
    except Exception:
        logger.warning("FAQ table init failed (PG may not be available)", exc_info=True)

    # APScheduler for Apifox sync
    scheduler = AsyncIOScheduler()
    sync_services = create_sync_services()

    if sync_services:
        interval_minutes_raw = os.getenv("APIFOX_SYNC_INTERVAL_MINUTES", "60")
        try:
            interval_minutes = int(interval_minutes_raw)
        except ValueError:
            logger.warning("Invalid APIFOX_SYNC_INTERVAL_MINUTES, using default 60")
            interval_minutes = 60

        async def _run_sync():
            for project_name, svc in sync_services:
                try:
                    result = await svc.sync(project_name=project_name)
                    logger.info("Apifox sync [%s] result: %s", project_name, result)
                except Exception:
                    logger.exception("Apifox sync [%s] failed", project_name)

        # 启动时立即同步一次（可通过 APIFOX_SYNC_ON_STARTUP=true 开启，默认关闭）
        if os.getenv("APIFOX_SYNC_ON_STARTUP", "false").lower() in ("1", "true", "yes"):
            loop = asyncio.get_event_loop()
            loop.create_task(_run_sync())
        else:
            logger.info("Apifox startup sync skipped (set APIFOX_SYNC_ON_STARTUP=true to enable)")
        scheduler.add_job(_run_sync, "interval", minutes=interval_minutes, id="apifox_sync")
        logger.info("Apifox sync scheduled every %d minutes for %d projects", interval_minutes, len(sync_services))

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

    # Daily report for issue-diagnosis
    if os.getenv("DAILY_REPORT_ENABLED", "false").lower() in ("1", "true", "yes"):
        from scripts.daily_report import generate_and_send as _gen_report

        async def _run_daily_report():
            from datetime import datetime, timedelta
            date_str = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
            try:
                result = await _gen_report(date_str)
                logger.info("Daily report sent: %s", result)
            except Exception:
                logger.exception("Daily report failed")

        report_hour = int(os.getenv("DAILY_REPORT_HOUR", "9"))
        scheduler.add_job(
            _run_daily_report,
            "cron",
            hour=report_hour,
            minute=0,
            id="daily_report",
        )
        logger.info("Daily report scheduled at %02d:00", report_hour)

    try:
        scheduler.start()
    except Exception:
        logger.exception("Failed to start APScheduler, Apifox sync disabled")

    yield

    # Shutdown
    scheduler.shutdown(wait=False)

    logger.info("Shutting down AI Agent Service")
    await plugin_manager.stop_all()

    try:
        from api.db import close_faq_pool
        await close_faq_pool()
    except Exception:
        pass

    from api.services.sdk_pool import get_cache
    cache = get_cache()
    if cache:
        await cache.stop()


class OpenApiLoggingMiddleware(BaseHTTPMiddleware):
    """记录 /open-api/ 请求参数和响应体."""

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/open-api/"):
            return await call_next(request)

        # 读取请求体
        body_bytes = await request.body()
        if body_bytes:
            try:
                import json as _json
                body_log = _json.loads(body_bytes)
            except Exception:
                body_log = body_bytes.decode("utf-8", errors="replace")
        else:
            body_log = None

        query_params = dict(request.query_params)
        # 隐藏敏感字段
        for key in ("sign", "token", "app_key", "appkey"):
            if key in query_params:
                query_params[key] = "***"

        logger.info(
            "[OpenAPI] REQUEST %s %s | params=%s | body=%s",
            request.method,
            request.url.path,
            query_params,
            body_log,
        )

        # 重新注入请求体（body 只能读一次）
        async def receive() -> Message:
            return {"type": "http.request", "body": body_bytes, "more_body": False}

        request._receive = receive

        # 捕获响应体
        response = await call_next(request)
        resp_body = b""
        async for chunk in response.body_iterator:
            resp_body += chunk

        try:
            import json as _json
            resp_log = _json.loads(resp_body)
        except Exception:
            resp_log = resp_body.decode("utf-8", errors="replace")[:500]

        logger.info(
            "[OpenAPI] RESPONSE %s %s | status=%d | body=%s",
            request.method,
            request.url.path,
            response.status_code,
            resp_log,
        )

        from starlette.responses import Response
        return Response(
            content=resp_body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )


# Create FastAPI app
app = FastAPI(
    title="AI Agent Service",
    description="Generic AI agent service with skill-based extensibility",
    version="1.0.0",
    lifespan=lifespan,
)

# OpenAPI request/response logging middleware
app.add_middleware(OpenApiLoggingMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if request.url.path.startswith("/open-api/"):
        errcode = "100003" if exc.status_code == 401 else str(exc.status_code)
        return JSONResponse(
            status_code=exc.status_code,
            content={"errcode": errcode, "description": exc.detail, "data": None},
        )
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    if request.url.path.startswith("/open-api/"):
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"errcode": "500000", "description": "服务内部错误，请稍后重试", "data": None},
        )
    raise exc


@app.exception_handler(StarletteHTTPException)
async def starlette_http_exception_handler(request: Request, exc: StarletteHTTPException):
    if request.url.path.startswith("/open-api/"):
        errcode = "100003" if exc.status_code == 401 else str(exc.status_code)
        return JSONResponse(
            status_code=exc.status_code,
            content={"errcode": errcode, "description": str(exc.detail), "data": None},
        )
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    if request.url.path.startswith("/open-api/"):
        return JSONResponse(
            status_code=422,
            content={"errcode": "422", "description": "请求参数错误", "data": None},
        )
    return JSONResponse(status_code=422, content={"detail": exc.errors()})

# SPA fallback: /static/agent/* non-file requests return index.html for vue-router history mode
# Must be registered before app.mount("/static") so FastAPI route takes priority
from fastapi.responses import FileResponse as _FileResponse

@app.get("/static/agent/{full_path:path}")
async def agent_spa(full_path: str):
    agent_index = Path(__file__).parent / "static" / "agent" / "index.html"
    requested = Path(__file__).parent / "static" / "agent" / full_path
    if requested.exists() and requested.is_file():
        return _FileResponse(str(requested))
    return _FileResponse(str(agent_index))

# Mount static files
static_path = Path(__file__).parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path), html=True), name="static")

# Mount knowledge base assets for image access
kb_assets_path = DATA_DIR / "kb" / "产品与交付知识" / "assets"
if kb_assets_path.exists():
    app.mount("/kb/assets", StaticFiles(directory=str(kb_assets_path)), name="kb_assets")
    logger.info(f"Mounted KB assets at /kb/assets -> {kb_assets_path}")

# Mount daily reports directory
reports_path = Path(__file__).parent / "reports"
reports_path.mkdir(exist_ok=True)
app.mount("/reports", StaticFiles(directory=str(reports_path)), name="reports")

# Include API routers
app.include_router(router)  # Generic /api endpoints
app.include_router(plugins_router)  # Plugin management API
app.include_router(diagnosis_router)  # Diagnosis cases API
from api.routers.faq import router as faq_router
app.include_router(faq_router)
from api.routers.browser_action import router as browser_action_router
app.include_router(browser_action_router)
from api.routers.report import router as report_router
app.include_router(report_router)
# Note: Channel-specific routers (e.g. /yzj/*) are now registered by plugins at startup


@app.get("/")
async def root():
    """API service root endpoint."""
    return {
        "service": "AI Agent Service",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "docs": "/docs",
            "health": "/api/health",
            "plugins": "/api/plugins/"
        }
    }



if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "9090"))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
