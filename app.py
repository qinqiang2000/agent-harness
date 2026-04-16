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
logger = logging.getLogger(__name__)

# Import after logging is configured
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from api.routers.agent import router
from api.routers.plugins import router as plugins_router
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

        # 启动时立即同步一次
        loop = asyncio.get_event_loop()
        loop.create_task(_run_sync())
        scheduler.add_job(_run_sync, "interval", minutes=interval_minutes, id="apifox_sync")
        logger.info("Apifox sync scheduled every %d minutes for %d projects", interval_minutes, len(sync_services))

    try:
        scheduler.start()
    except Exception:
        logger.exception("Failed to start APScheduler, Apifox sync disabled")

    yield

    # Shutdown
    scheduler.shutdown(wait=False)

    logger.info("Shutting down AI Agent Service")
    await plugin_manager.stop_all()

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

# Mount static files
static_path = Path(__file__).parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

# Mount knowledge base assets for image access
kb_assets_path = DATA_DIR / "kb" / "产品与交付知识" / "assets"
if kb_assets_path.exists():
    app.mount("/kb/assets", StaticFiles(directory=str(kb_assets_path)), name="kb_assets")
    logger.info(f"Mounted KB assets at /kb/assets -> {kb_assets_path}")

# Include API routers
app.include_router(router)  # Generic /api endpoints
app.include_router(plugins_router)  # Plugin management API
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
