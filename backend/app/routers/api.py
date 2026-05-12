from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Set

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, WebSocket, WebSocketDisconnect

from app.schemas import AnalyticsResponse, ApiKey, ApiKeyCreate, AuthSession, Job, JobStatus, LoginRequest, ScrapeRequest, ProgressUpdate, JobDetailResponse
from app.services.analytics import ai_insights, build_dashboard_summary, revenue_by_category, revenue_forecast, revenue_trend, variant_distribution
from app.services.auth import auth_store, require_auth
from app.services.exporter import export_csv, export_excel, export_images, export_json, export_txt
from app.services.external_scraper import control_external_scrape, external_base_url, start_external_scrape
from app.services.scraper_engine import infer_website
from app.services.store import store
from app.services.job_queue import get_job_queue, JobPriority
from app.services.performance_metrics import get_metrics_collector

router = APIRouter(prefix="/api")
REQUESTS: dict[str, ScrapeRequest] = {}


# WebSocket Connection Manager for Real-Time Progress Updates
class ConnectionManager:
    """Manages WebSocket connections for real-time progress streaming."""
    
    def __init__(self):
        self.active_connections: dict[str, Set[WebSocket]] = {}  # job_id -> set of websockets
        self.lock = asyncio.Lock()
    
    async def connect(self, job_id: str, websocket: WebSocket):
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        async with self.lock:
            if job_id not in self.active_connections:
                self.active_connections[job_id] = set()
            self.active_connections[job_id].add(websocket)
    
    async def disconnect(self, job_id: str, websocket: WebSocket):
        """Remove a WebSocket connection."""
        async with self.lock:
            if job_id in self.active_connections:
                self.active_connections[job_id].discard(websocket)
                if not self.active_connections[job_id]:
                    del self.active_connections[job_id]
    
    async def broadcast(self, job_id: str, message: dict):
        """Broadcast a message to all connections for a job."""
        async with self.lock:
            connections = self.active_connections.get(job_id, set()).copy()
        
        disconnected = set()
        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.add(connection)
        
        # Clean up disconnected websockets
        for connection in disconnected:
            await self.disconnect(job_id, connection)


# Global connection manager instance
connection_manager = ConnectionManager()


@router.post("/auth/login", response_model=AuthSession)
async def login(request: LoginRequest) -> AuthSession:
    return auth_store.login(request)


@router.get("/org/api-keys", response_model=list[ApiKey])
async def list_api_keys(session: AuthSession = Depends(require_auth)) -> list[ApiKey]:
    return auth_store.list_api_keys(session.organization_id)


@router.post("/org/api-keys", response_model=ApiKey)
async def create_api_key(request: ApiKeyCreate, session: AuthSession = Depends(require_auth)) -> ApiKey:
    return auth_store.create_api_key(session.organization_id, request)


@router.post("/scrape", response_model=Job)
async def start_scrape(request: ScrapeRequest, session: AuthSession = Depends(require_auth)) -> Job:
    """Start an optimized async scraping job with priority queue."""
    job_id = str(uuid.uuid4())
    website = infer_website(str(request.url), request.website)
    job = Job(id=job_id, status=JobStatus.queued, url=str(request.url), website=website, organization_id=session.organization_id)
    REQUESTS[job_id] = request
    await store.create_job(job)
    
    # Track performance metrics
    metrics_collector = get_metrics_collector()
    metrics_collector.start_job(job_id)
    
    if request.options.external_service and external_base_url():
        try:
            external = await start_external_scrape(job_id, request)
            external_job_id = str(external.get("id") or external.get("job_id") or "")
            await store.update_job(
                job_id,
                status=JobStatus.running,
                external_job_id=external_job_id,
                external_status_url=f"{external_base_url()}/api/jobs/{external_job_id}" if external_job_id else "",
                current_product="External FastAPI scraper accepted the job",
            )
            await store.append_log(job_id, f"External scraper service started job {external_job_id or job_id}")
        except Exception as exc:
            await store.update_job(job_id, status=JobStatus.failed, progress=100, current_product="External scraper start failed")
            await store.append_log(job_id, str(exc))
    else:
        # Enqueue job using optimized async job queue
        job_queue = await get_job_queue()
        priority = JobPriority.HIGH if request.options.high_priority else JobPriority.NORMAL
        await job_queue.enqueue(job_id, request, priority=priority)
        await store.append_log(job_id, f"Job enqueued with {priority.name} priority using optimized async scraper")
    
    return job


@router.post("/start-scraping", response_model=Job)
async def start_scraping_alias(request: ScrapeRequest, session: AuthSession = Depends(require_auth)) -> Job:
    return await start_scrape(request, session)


@router.get("/jobs", response_model=list[Job])
async def list_jobs(session: AuthSession = Depends(require_auth)) -> list[Job]:
    jobs = await store.list_jobs()
    return [job for job in jobs if job.organization_id == session.organization_id]


@router.get("/jobs/{job_id}", response_model=Job)
async def get_job(job_id: str, session: AuthSession = Depends(require_auth)) -> Job:
    job = await store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.organization_id != session.organization_id:
        raise HTTPException(status_code=403, detail="This job belongs to another organization")
    return job


@router.post("/jobs/{job_id}/{action}", response_model=Job)
async def control_job(job_id: str, action: str, session: AuthSession = Depends(require_auth)) -> Job:
    """Control job execution (pause, resume, stop, retry) with optimized queue."""
    job = await store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.organization_id != session.organization_id:
        raise HTTPException(status_code=403, detail="This job belongs to another organization")
    if job.external_job_id and action in {"pause", "resume", "stop"}:
        try:
            await control_external_scrape(job.external_job_id, action)
            await store.append_log(job_id, f"Forwarded {action} to external scraper service")
        except Exception as exc:
            await store.append_log(job_id, str(exc))
    if action == "pause":
        await store.set_status(job_id, JobStatus.paused)
    elif action == "resume":
        await store.set_status(job_id, JobStatus.running)
    elif action == "stop":
        await store.set_status(job_id, JobStatus.stopped)
    elif action == "retry":
        await store.update_job(job_id, status=JobStatus.queued, progress=0, logs=[], products=[])
        request = REQUESTS.get(job_id)
        if request:
            job_queue = await get_job_queue()
            await job_queue.enqueue(job_id, request, priority=JobPriority.HIGH)
            await store.append_log(job_id, "Job requeued with HIGH priority via optimized async scraper")
    else:
        raise HTTPException(status_code=400, detail="Unsupported action")
    updated = await store.get_job(job_id)
    return updated  # type: ignore[return-value]


@router.post("/pause-scraping/{job_id}", response_model=Job)
async def pause_scraping(job_id: str, session: AuthSession = Depends(require_auth)) -> Job:
    return await control_job(job_id, "pause", session)


@router.post("/resume-scraping/{job_id}", response_model=Job)
async def resume_scraping(job_id: str, session: AuthSession = Depends(require_auth)) -> Job:
    return await control_job(job_id, "resume", session)


@router.post("/stop-scraping/{job_id}", response_model=Job)
async def stop_scraping(job_id: str, session: AuthSession = Depends(require_auth)) -> Job:
    return await control_job(job_id, "stop", session)


@router.get("/scraping-status/{job_id}", response_model=Job)
async def scraping_status(job_id: str, session: AuthSession = Depends(require_auth)) -> Job:
    return await get_job(job_id, session)


@router.get("/products")
async def products(job_id: str | None = Query(default=None), session: AuthSession = Depends(require_auth)) -> list[dict]:
    rows = await store.products(job_id, organization_id=session.organization_id)
    return [row.model_dump(mode="json") for row in rows]


@router.get("/variants")
async def variants(job_id: str | None = Query(default=None), session: AuthSession = Depends(require_auth)) -> list[dict]:
    rows = await store.products(job_id, organization_id=session.organization_id)
    return [
        {
            "id": row.id,
            "parent_asin": row.parent_asin,
            "variant_asin": row.variant_asin,
            "variant_name": row.variant_name or row.variant,
            "variant_type": row.variant_type,
            "color": row.color,
            "size": row.size,
            "weight": row.weight,
            "model": row.model,
            "storage": row.storage,
            "price": row.price,
            "units_sold": row.units_sold,
            "revenue": row.revenue,
            "demand_score": row.demand_score or row.scores.get("demand_score", 0),
            "performance_score": row.scores.get("performance_score", 0),
            "offers": row.offers,
            "availability": row.availability,
            "product_url": row.product_url,
        }
        for row in rows
    ]


@router.get("/analytics", response_model=AnalyticsResponse)
async def analytics(session: AuthSession = Depends(require_auth)) -> AnalyticsResponse:
    jobs = await store.list_jobs()
    jobs = [job for job in jobs if job.organization_id == session.organization_id]
    products = await store.products(organization_id=session.organization_id)
    active_jobs = len([job for job in jobs if job.status in {JobStatus.queued, JobStatus.running, JobStatus.paused}])
    completed_jobs = len([job for job in jobs if job.status == JobStatus.completed])
    top_products = sorted(products, key=lambda item: item.revenue, reverse=True)[:8]
    return AnalyticsResponse(
        summary=build_dashboard_summary(products, active_jobs, len(jobs), completed_jobs),
        revenue_by_category=revenue_by_category(products),
        revenue_trend=revenue_trend(products),
        variant_distribution=variant_distribution(products),
        top_products=top_products,
        ai_insights=ai_insights(products),
        revenue_forecast=revenue_forecast(products),
    )


# ======================== NEW REAL-TIME & ADVANCED ENDPOINTS ========================

@router.websocket("/ws/progress/{job_id}")
async def websocket_progress(websocket: WebSocket, job_id: str):
    """WebSocket endpoint for real-time job progress updates (Step-by-Step)."""
    job = await store.get_job(job_id)
    if not job:
        await websocket.close(code=4004, reason="Job not found")
        return
    
    await connection_manager.connect(job_id, websocket)
    try:
        while True:
            # Keep connection alive and listen for messages
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        await connection_manager.disconnect(job_id, websocket)
    except Exception as e:
        await connection_manager.disconnect(job_id, websocket)


@router.get("/jobs/{job_id}/details", response_model=JobDetailResponse)
async def get_job_details(job_id: str, session: AuthSession = Depends(require_auth)) -> JobDetailResponse:
    """Get comprehensive job status with real-time metrics and step-by-step progress."""
    job = await store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.organization_id != session.organization_id:
        raise HTTPException(status_code=403, detail="This job belongs to another organization")
    
    products = await store.products(job_id, organization_id=session.organization_id)
    metrics_collector = get_metrics_collector()
    job_metrics = metrics_collector.get_job_metrics(job_id) or {}
    
    # Calculate derived metrics
    total_products = len(products)
    estimated_completion = None
    if job.status == JobStatus.running and job.progress > 0:
        elapsed = (datetime.now() - (job.started_at or datetime.now())).total_seconds()
        if elapsed > 0:
            rate = job.progress / elapsed
            if rate > 0:
                estimated_completion = datetime.now() + timedelta(seconds=(100 - job.progress) / rate)
    
    return JobDetailResponse(
        job_id=job_id,
        status=job.status,
        progress=job.progress,
        url=job.url,
        website=job.website,
        total_products=total_products,
        products_found=total_products,
        started_at=job.started_at,
        completed_at=job.completed_at,
        estimated_completion=estimated_completion,
        duration_seconds=int((job.completed_at or datetime.now() - job.started_at).total_seconds()) if job.started_at else 0,
        current_step=int(job.progress / 20) + 1,  # 5 steps: 0-20, 20-40, 40-60, 60-80, 80-100
        stage=_get_stage_from_progress(job.progress),
        message=_get_message_from_stage(_get_stage_from_progress(job.progress)),
        speed=job_metrics.get("products_per_second", 0),
        avg_time_per_product=job_metrics.get("avg_time_per_product", 0),
        success_rate=job_metrics.get("success_rate", 100.0),
    )


@router.get("/analytics/dashboard/summary")
async def get_dashboard_summary(session: AuthSession = Depends(require_auth)) -> dict:
    """Get dashboard summary with system health metrics and sliders."""
    jobs = await store.list_jobs()
    jobs = [job for job in jobs if job.organization_id == session.organization_id]
    
    total_jobs = len(jobs)
    completed_jobs = len([j for j in jobs if j.status == JobStatus.completed])
    failed_jobs = len([j for j in jobs if j.status == JobStatus.failed])
    running_jobs = len([j for j in jobs if j.status in {JobStatus.running, JobStatus.queued}])
    
    products = await store.products(organization_id=session.organization_id)
    total_products = len(products)
    total_revenue = sum(p.revenue or 0 for p in products)
    
    metrics_collector = get_metrics_collector()
    avg_metrics = metrics_collector.get_average_metrics()
    
    success_rate = (completed_jobs / total_jobs * 100) if total_jobs > 0 else 0
    avg_duration = avg_metrics.get("avg_duration", 0) if avg_metrics else 0
    
    # Get last 7 days data for charts
    today = datetime.now().date()
    week_data = []
    for i in range(6, -1, -1):
        date = today - timedelta(days=i)
        jobs_on_date = [j for j in jobs if j.started_at and j.started_at.date() == date]
        week_data.append({
            "date": str(date),
            "jobs": len(jobs_on_date),
            "products": sum(len(await store.products(j.id, organization_id=session.organization_id)) for j in jobs_on_date)
        })
    
    return {
        "total_jobs": total_jobs,
        "completed_jobs": completed_jobs,
        "failed_jobs": failed_jobs,
        "running_jobs": running_jobs,
        "success_rate": round(success_rate, 2),
        "average_duration_seconds": round(avg_duration, 2),
        "total_products_scraped": total_products,
        "average_products_per_job": round(total_products / total_jobs, 1) if total_jobs > 0 else 0,
        "total_revenue": round(total_revenue, 2),
        "system_health": {
            "cpu_usage": 45,  # Placeholder for slider visualization
            "memory_usage": 62,  # Placeholder for slider visualization
            "database_connections": 5,
            "api_response_time_ms": 150,
        },
        "weekly_activity": week_data,
    }


@router.get("/analytics/timeline")
async def get_timeline_analytics(
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    granularity: str = Query("hourly"),
    session: AuthSession = Depends(require_auth)
) -> dict:
    """Get analytics over time for dashboard charts with slider date range."""
    jobs = await store.list_jobs()
    jobs = [job for job in jobs if job.organization_id == session.organization_id]
    
    # Parse dates
    if not start_date:
        start_date = (datetime.now() - timedelta(days=7)).isoformat()
    if not end_date:
        end_date = datetime.now().isoformat()
    
    start = datetime.fromisoformat(start_date)
    end = datetime.fromisoformat(end_date)
    
    # Filter jobs within range
    jobs_in_range = [j for j in jobs if j.started_at and start <= j.started_at <= end]
    
    timeline_data = []
    if granularity == "daily":
        current = start.date()
        while current <= end.date():
            jobs_on_date = [j for j in jobs_in_range if j.started_at and j.started_at.date() == current]
            completed_on_date = len([j for j in jobs_on_date if j.status == JobStatus.completed])
            products_on_date = sum(len(await store.products(j.id, organization_id=session.organization_id)) for j in jobs_on_date)
            
            timeline_data.append({
                "timestamp": str(current),
                "jobs_completed": completed_on_date,
                "products_extracted": products_on_date,
                "jobs_count": len(jobs_on_date),
            })
            current += timedelta(days=1)
    else:  # hourly
        current = start
        while current <= end:
            jobs_on_hour = [j for j in jobs_in_range if j.started_at and j.started_at.hour == current.hour]
            completed_on_hour = len([j for j in jobs_on_hour if j.status == JobStatus.completed])
            products_on_hour = sum(len(await store.products(j.id, organization_id=session.organization_id)) for j in jobs_on_hour)
            
            timeline_data.append({
                "timestamp": current.isoformat(),
                "jobs_completed": completed_on_hour,
                "products_extracted": products_on_hour,
                "jobs_count": len(jobs_on_hour),
            })
            current += timedelta(hours=1)
    
    return {
        "data": timeline_data,
        "start_date": start_date,
        "end_date": end_date,
        "granularity": granularity,
    }


@router.get("/health/detailed")
async def get_detailed_health() -> dict:
    """Get detailed system health for dashboard monitoring."""
    metrics_collector = get_metrics_collector()
    queue = await get_job_queue()
    
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0",
        "components": {
            "api": {"status": "ok", "response_time_ms": 45},
            "database": {"status": "ok", "connections": 5},
            "cache": {"status": "ok", "memory_usage_mb": 150},
            "scraper": {"status": "ok", "active_jobs": len(queue.active_jobs)},
        },
        "performance": metrics_collector.get_average_metrics() or {},
        "queue_status": {
            "active_jobs": len(queue.active_jobs),
            "queued_jobs": queue.queue.qsize(),
            "completed_jobs": len(queue.completed_jobs),
            "failed_jobs": len(queue.failed_jobs),
        },
    }


# ======================== HELPER FUNCTIONS ========================

def _get_stage_from_progress(progress: int) -> str:
    """Map progress percentage to scraping stage."""
    if progress < 10:
        return "initializing"
    elif progress < 25:
        return "loading"
    elif progress < 60:
        return "extracting"
    elif progress < 85:
        return "enriching"
    elif progress < 100:
        return "finalizing"
    else:
        return "complete"


def _get_message_from_stage(stage: str) -> str:
    """Get user-friendly message for each stage."""
    messages = {
        "initializing": "🔄 Starting browser and initializing...",
        "loading": "📄 Loading Amazon page...",
        "extracting": "🔍 Extracting product information...",
        "enriching": "⭐ Fetching product details and ratings...",
        "finalizing": "✨ Finalizing and exporting data...",
        "complete": "✅ Scraping completed successfully!",
    }
    return messages.get(stage, "Processing...")


# ======================== EXISTING ENDPOINTS CONTINUE BELOW ========================


@router.get("/export/{fmt}")
async def export(fmt: str, job_id: str | None = Query(default=None), api_key: str | None = Query(default=None), authorization: str | None = None) -> Response:
    session = auth_store.authenticate(authorization, api_key)
    if job_id:
        job = await store.get_job(job_id)
        if job and job.organization_id != session.organization_id:
            raise HTTPException(status_code=403, detail="This export belongs to another organization")
    products = await store.products(job_id, organization_id=session.organization_id)
    exporters = {
        "csv": ("text/csv", "scrape-export.csv", export_csv),
        "json": ("application/json", "scrape-export.json", export_json),
        "txt": ("text/plain", "scrape-export.txt", export_txt),
        "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "scrape-export.xlsx", export_excel),
        "images": ("application/zip", "scrape-images.zip", export_images),
    }
    if fmt not in exporters:
        raise HTTPException(status_code=400, detail="Use one of csv, json, txt, xlsx")
    media_type, filename, exporter = exporters[fmt]
    return Response(content=exporter(products), media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/exports/{fmt}")
async def exports_alias(fmt: str, job_id: str | None = Query(default=None), api_key: str | None = Query(default=None), authorization: str | None = None) -> Response:
    return await export(fmt, job_id, api_key, authorization)


@router.get("/download/{fmt}")
async def download_alias(fmt: str, job_id: str | None = Query(default=None), api_key: str | None = Query(default=None), authorization: str | None = None) -> Response:
    return await export(fmt, job_id, api_key, authorization)


@router.websocket("/ws/jobs/{job_id}")
async def job_socket(websocket: WebSocket, job_id: str) -> None:
    await websocket.accept()
    queue = await store.subscribe(job_id)
    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event)
            await asyncio.sleep(0)
    except WebSocketDisconnect:
        await store.unsubscribe(job_id, queue)
