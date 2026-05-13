# Render Database Deployment

This project now stores scrape jobs and product rows in Postgres when `DATABASE_URL`
is available. Without `DATABASE_URL`, the backend still runs locally with an
in-memory fallback.

## What Changed

1. `backend/app/services/store.py` now uses a database-backed `JobStore`.
2. `render.yaml` provisions `commerce-scraping-analytics-db`.
3. `DATABASE_URL` is injected into the backend from the Render Postgres internal
   connection string.
4. Product rows are stored in `app_products.payload` as JSONB so all scraper
   fields remain available for analytics and export.
5. Scraper concurrency is reduced for Render free-tier memory:
   `SCRAPER_MAX_DETAIL_CONCURRENCY=2` and `SCRAPER_MAX_VARIANT_CONCURRENCY=1`.

## Deployment Steps

1. Commit and push these changes.
2. In Render, open the Blueprint-backed service.
3. Click **Sync Blueprint**.
4. Confirm Render creates:
   - Web service: `commerce-scraping-analytics-backend`
   - Postgres database: `commerce-scraping-analytics-db`
5. Wait for the database to become available.
6. Redeploy the backend service.
7. Open `/health` on the backend URL and confirm:
   - `status` is `ok`
   - `storage` is `postgres`
8. Open `/api/admin/storage-status` and confirm:
   - `persistent` is `true`
   - `storage` is `postgres`
   - job/product counts are visible

## Local Development

Run without a database:

```bash
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Run with a local or hosted Postgres database:

```bash
cd backend
pip install -r requirements.txt
set DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DBNAME
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Memory Checklist

1. Keep `SCRAPER_MAX_WORKERS=1` on free/small Render instances.
2. Keep `SCRAPER_MAX_BROWSERS=1`.
3. Keep `SCRAPER_KEEP_BROWSER_POOL=0` so Chromium is released after each job.
4. Keep detail concurrency at `2` or lower for free tier.
5. Keep variant concurrency at `1` for free tier.
6. Use `/api/admin/storage-status` after deploy to verify the backend is not
   falling back to memory storage.
7. If memory emails continue after this patch, the next step is upgrading the
   Render instance or moving the Playwright scraper to a separate worker service.
