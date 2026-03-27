"""Main FastAPI application for AI Agent Service."""

import logging
import os
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

# Create FastAPI app
app = FastAPI(
    title="AI Agent Service",
    description="Generic AI agent service with skill-based extensibility",
    version="1.0.0"
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


@app.on_event("startup")
async def startup_event():
    """Application startup event."""
    from api.dependencies import get_config_service, get_plugin_manager

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


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown event."""
    from api.dependencies import get_plugin_manager

    logger.info("Shutting down AI Agent Service")

    plugin_manager = get_plugin_manager()
    await plugin_manager.stop_all()


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "9090"))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
