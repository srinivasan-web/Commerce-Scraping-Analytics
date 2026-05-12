from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
from typing import Any

from backend.app.schemas import ScrapeRequest


def external_base_url() -> str:
    return os.getenv("EXTERNAL_SCRAPER_API_URL", "").rstrip("/")


def _request_json(method: str, url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read().decode("utf-8")
        return json.loads(body) if body else {}


async def start_external_scrape(job_id: str, request: ScrapeRequest) -> dict[str, Any]:
    base_url = external_base_url()
    if not base_url:
        raise RuntimeError("EXTERNAL_SCRAPER_API_URL is not configured")
    payload = {
        "client_job_id": job_id,
        "url": str(request.url),
        "website": request.website.value,
        "options": request.options.model_dump(),
    }
    try:
        return await asyncio.to_thread(_request_json, "POST", f"{base_url}/api/scrape", payload)
    except urllib.error.URLError as exc:
        raise RuntimeError(f"External scraper service is unreachable: {exc}") from exc


async def control_external_scrape(external_job_id: str, action: str) -> dict[str, Any]:
    base_url = external_base_url()
    if not base_url:
        raise RuntimeError("EXTERNAL_SCRAPER_API_URL is not configured")
    try:
        return await asyncio.to_thread(_request_json, "POST", f"{base_url}/api/jobs/{external_job_id}/{action}", None)
    except urllib.error.URLError as exc:
        raise RuntimeError(f"External scraper service is unreachable: {exc}") from exc
