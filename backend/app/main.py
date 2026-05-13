from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.api import router
from app.services.store import seed_store, store
from app.services.async_scraper import run_scrape_job_optimized, cleanup_browser_pool
from app.services.job_queue import initialize_job_queue, shutdown_job_queue, get_job_queue


def configure_windows_event_loop() -> None:
    """Use the Windows event loop that supports Playwright subprocesses."""
    if sys.platform != "win32" or not hasattr(asyncio, "WindowsProactorEventLoopPolicy"):
        return
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass


configure_windows_event_loop()


def cors_origins() -> list[str]:
    """Return allowed frontend origins for local and deployed dashboards."""
    defaults = [
        "http://localhost:3000", 
        "http://127.0.0.1:3000", 
        "http://localhost:3001",
        "https://commerce-scraping-analytics.onrender.com",
        "https://commerce-scraping-analytics.vercel.app"
    ]
    configured = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "").split(",") if origin.strip()]
    return [*defaults, *configured]


def cors_origin_regex() -> str:
    """Allow Vercel preview deployment URLs for this project."""
    return os.getenv(
        "CORS_ORIGIN_REGEX",
        r"https://commerce-scraping-analytics(?:-[a-z0-9]+)?(?:-git-main)?-srinivasan-webs-projects\.vercel\.app",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management with optimized async scraping."""
    # Startup
    print("Starting backend with optimized async scraping...")
    await seed_store()
    
    # Initialize job queue with async scraper
    print(f"Initializing job queue with {os.getenv('SCRAPER_MAX_WORKERS', '1')} worker(s)...")
    await initialize_job_queue(run_scrape_job_optimized)
    
    yield
    
    # Shutdown
    print("Shutting down gracefully...")
    await shutdown_job_queue()
    await cleanup_browser_pool()
    await store.close()
    print("Cleanup complete")


app = FastAPI(
    title="Commerce Intelligence Scraping API",
    version="2.0.0",
    description="FastAPI backend for scraping jobs, live progress, analytics, and exports with optimized async processing.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_origin_regex=cors_origin_regex(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
async def root() -> dict[str, str]:
    """Root endpoint - API info."""
    return {
        "name": "Commerce Intelligence Scraping API",
        "version": "2.0.0",
        "status": "running",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health")
async def health() -> dict[str, object]:
    """Health check endpoint."""
    return {
        "status": "ok",
        "version": "2.0.0",
        "storage": "postgres" if store.persistent else "memory",
        "features": ["async-scraping", "job-queue", "performance-monitoring", "database-store"],
    }


@app.get("/api/admin/queue-status")
async def get_queue_status() -> dict:
    """Get current job queue status."""
    queue = await get_job_queue()
    return queue.get_status()


@app.get("/api/admin/storage-status")
async def get_storage_status() -> dict:
    """Get current storage backend and row counts."""
    return await store.storage_status()


@app.get("/api/admin/metrics")
async def get_system_metrics() -> dict:
    """Get system-wide performance metrics."""
    from app.services.performance_metrics import get_metrics_collector
    
    collector = get_metrics_collector()
    return {
        "average_metrics": collector.get_average_metrics(),
        "timeline_analysis": collector.get_timeline_analysis(),
    }


@app.get("/api/admin/job/{job_id}/performance")
async def get_job_performance(job_id: str) -> dict:
    """Get performance metrics for a specific job."""
    from app.services.performance_metrics import get_metrics_collector
    
    collector = get_metrics_collector()
    report = collector.get_job_report(job_id)
    if not report:
        return {"error": "Job not found or not yet started"}
    return report
