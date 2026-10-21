"""FastAPI application entry point for the LAN SaaS Cloud Controller."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import admin, dashboard, files, health
from app.auth import router as auth_router
from app.bootstrap_admin import bootstrap_from_env
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.db.init_db import create_all
from app.services.hdfs_service import build_hdfs_service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
logger = logging.getLogger("cloud_controller")

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_all()
    hdfs = build_hdfs_service(settings)
    app.state.hdfs = hdfs

    if settings.is_mock_hdfs:
        logger.warning("=" * 70)
        logger.warning("HDFS MOCK ADAPTER ACTIVE - local disk is used instead "
                       "of Apache Hadoop.")
        logger.warning("This is for UI development only. Set HDFS_ADAPTER="
                       "webhdfs for the real lab demonstration.")
        logger.warning("=" * 70)
    else:
        # Best-effort root directory creation. Failure must not stop the API:
        # the health endpoint will report the real problem instead.
        try:
            hdfs.ensure_dir(settings.hdfs_root)
            logger.info("HDFS root %s is available.", settings.hdfs_root)
        except Exception as exc:  # noqa: BLE001
            logger.error("HDFS root %s is not available: %s",
                         settings.hdfs_root, exc)

    bootstrap_from_env(settings)
    yield
    hdfs.close()


app = FastAPI(
    title=settings.app_name,
    description=(
        "Cloud Controller for a private, LAN-based SaaS cloud storage system. "
        "Metadata is stored in SQLite; file contents are stored in Apache "
        "Hadoop HDFS through WebHDFS."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# --- CORS: only the configured frontend origins ---------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["Content-Disposition", "Content-Length", "X-Content-SHA256"],
)

register_exception_handlers(app)


@app.middleware("http")
async def security_headers(request, call_next):  # noqa: ANN001
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


app.include_router(health.router)
app.include_router(auth_router.router)
app.include_router(files.router)
app.include_router(dashboard.router)
app.include_router(admin.router)

# --- Optional: serve the built React SPA from the same origin -------------
_static_root = Path(settings.static_dir).expanduser().resolve() if settings.static_dir else None
if _static_root and (_static_root / "index.html").is_file():
    assets = _static_root / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")
    logger.info("Serving built frontend from %s", _static_root)

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        if full_path.startswith(("api/", "docs", "redoc", "openapi.json")):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = (_static_root / full_path).resolve()
        if (full_path and candidate.is_file()
                and _static_root in candidate.parents):
            return FileResponse(candidate)
        return FileResponse(_static_root / "index.html")
else:
    @app.get("/", include_in_schema=False)
    def root():
        return {
            "app": settings.app_name,
            "status": "running",
            "docs": "/docs",
            "health": "/api/health",
            "note": "Frontend is not served by the controller "
                    "(set STATIC_DIR to enable single-origin mode).",
        }
