"""Main FastAPI application for AI Agent Service."""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv('.env')

# Configure logging BEFORE importing any modules that use logger
log_level = os.getenv('LOG_LEVEL', 'DEBUG')
logging.basicConfig(
    level=getattr(logging, log_level.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Import after logging is configured
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
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


# Create FastAPI app
app = FastAPI(
    title="AI Agent Service",
    description="Generic AI agent service with skill-based extensibility",
    version="1.0.0",
    lifespan=lifespan,
)

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
    raise exc


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

# Mount static files
static_path = Path(__file__).parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path), html=True), name="static")

# Mount knowledge base assets for image access
kb_assets_path = DATA_DIR / "kb" / "产品与交付知识" / "assets"
if kb_assets_path.exists():
    app.mount("/kb/assets", StaticFiles(directory=str(kb_assets_path)), name="kb_assets")
    logger.info(f"Mounted KB assets at /kb/assets -> {kb_assets_path}")

# Include API routers
app.include_router(router)  # Generic /api endpoints
app.include_router(plugins_router)  # Plugin management API
app.include_router(diagnosis_router)  # Diagnosis cases API
from api.routers.faq import router as faq_router
app.include_router(faq_router)
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
