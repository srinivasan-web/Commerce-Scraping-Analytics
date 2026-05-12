from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, WebSocket, WebSocketDisconnect

from backend.app.schemas import AnalyticsResponse, ApiKey, ApiKeyCreate, AuthSession, Job, JobStatus, LoginRequest, ScrapeRequest
from backend.app.services.analytics import ai_insights, build_dashboard_summary, revenue_by_category, revenue_forecast, revenue_trend, variant_distribution
from backend.app.services.auth import auth_store, require_auth
from backend.app.services.exporter import export_csv, export_excel, export_images, export_json, export_txt
from backend.app.services.external_scraper import control_external_scrape, external_base_url, start_external_scrape
from backend.app.services.scraper_engine import infer_website
from backend.app.services.store import store
from backend.app.services.job_queue import get_job_queue, JobPriority
from backend.app.services.performance_metrics import get_metrics_collector

router = APIRouter(prefix="/api")
REQUESTS: dict[str, ScrapeRequest] = {}


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
