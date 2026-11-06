import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from config import settings
from core.db import db_manager
from core.gemini_client import gemini_manager
from api.v1.router import api_v1_router

logging.basicConfig(
    level=settings.LOG_LEVEL.upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("make_ai_service")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Connect to MongoDB
    logger.info(f"Starting Make AI Service for instance: {settings.INSTANCE_NAME} (Port {settings.PORT})")
    await db_manager.connect()
    yield
    # Shutdown: Disconnect MongoDB
    logger.info("Shutting down Make AI Service...")
    await db_manager.disconnect()

app = FastAPI(
    title=f"Make AI Service ({settings.INSTANCE_NAME})",
    description="Backend microservice for 3D CAD Costing, 2D PDF Blueprint Intelligence, and Business Q&A.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API v1 routes (/api/v1/ai/...)
app.include_router(api_v1_router)

# Mount static uploads directory for blueprints, drawings, and CAD previews
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

@app.get("/health")
async def health_check():
    """Health check endpoint reporting connectivity to DBs and AI client."""
    erp_connected = db_manager.erp_db is not None
    sc_connected = db_manager.sc_db is not None
    mes_connected = db_manager.mes_db is not None
    gemini_ready = gemini_manager.client is not None

    return {
        "status": "healthy",
        "instance": settings.INSTANCE_NAME,
        "environment": settings.ENVIRONMENT,
        "port": settings.PORT,
        "services": {
            "erp_database": "connected" if erp_connected else "disconnected",
            "sc_database": "connected" if sc_connected else "disconnected",
            "mes_database": "connected" if mes_connected else "disconnected",
            "gemini_api": "ready" if gemini_ready else "key_missing_or_uninitialized",
            "quaoar_url": settings.QUAOAR_URL
        }
    }

@app.get("/")
async def root():
    return {
        "service": "Make AI Service",
        "instance": settings.INSTANCE_NAME,
        "docs": "/docs",
        "health": "/health",
        "endpoints": {
            "chat": "/api/v1/ai/chat",
            "chat_stream": "/api/v1/ai/chat/stream",
            "chat_stream_test": "/api/v1/ai/chat/stream/test"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host=settings.HOST, port=settings.PORT, reload=True)
