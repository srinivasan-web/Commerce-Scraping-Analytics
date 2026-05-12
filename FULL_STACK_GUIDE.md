# Commerce Intelligence Scraping Platform

This repository now contains a runnable full-stack scraping analytics platform:

- `backend/`: FastAPI API, Playwright scraping worker, WebSocket progress, analytics, exports.
- `frontend/`: Next.js 15 dashboard with React Query, Zustand, Tailwind, Framer Motion, Recharts, and typed API calls.
- `database_schema.sql`: PostgreSQL tables for jobs, products, and variants.
- `docker-compose.yml`: Backend, frontend, PostgreSQL, and Redis services.

## Local Backend

```bash
python -m venv venv
venv\Scripts\activate
pip install -r backend/requirements.txt
playwright install chromium
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

## Local Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. The backend API runs on `http://localhost:8000`.

## Docker

```bash
docker compose up --build
```

## API Routes

- `POST /api/scrape`: start a scraping job.
- `GET /api/jobs`: list scraping jobs.
- `GET /api/jobs/{job_id}`: get one job.
- `POST /api/jobs/{job_id}/pause`: pause a running job.
- `POST /api/jobs/{job_id}/resume`: resume a paused job.
- `POST /api/jobs/{job_id}/stop`: stop a job.
- `POST /api/jobs/{job_id}/retry`: retry the original request.
- `GET /api/products`: list scraped products.
- `GET /api/analytics`: dashboard analytics.
- `GET /api/export/xlsx|csv|json|txt`: export data.
- `WS /api/ws/jobs/{job_id}`: live progress, logs, current product, revenue, and captcha alerts.

## Deployment

Deploy `frontend/` to Vercel with `NEXT_PUBLIC_API_URL` pointing at your backend URL.

Deploy `backend/` to Render using the Dockerfile or:

```bash
uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT
```

For persistent production state, connect PostgreSQL and Redis using the schema in `database_schema.sql`. The current implementation keeps job state in memory for fast local runs and clean demos; the schema is ready for swapping the store layer to SQL persistence.

