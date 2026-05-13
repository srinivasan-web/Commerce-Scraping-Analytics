# 🎯 Deployment Decision Tree & Quick Troubleshooting

## 📊 Deployment Method Decision Tree

```
START: Where do you want to deploy?
│
├─→ ON MY LOCAL MACHINE (Development)
│   ├─→ Want Database?
│   │   ├─ YES → Use Docker-Compose (full stack)
│   │   └─ NO  → Local Development (Python + Node only)
│   └─→ Commands:
│       └─ LOCAL DEV: 2 terminals (backend + frontend)
│       └─ DOCKER: 1 command (docker-compose up)
│
├─→ ON MY COMPANY SERVER/VPS
│   ├─→ Want Automatic Updates?
│   │   ├─ YES → Use Docker + Portainer
│   │   └─ NO  → Manual Docker or bare metal
│   └─→ Setup: SSH + Docker-Compose + Nginx Reverse Proxy
│
└─→ IN THE CLOUD (Production)
    ├─→ Which Platform?
    │   ├─ Render.com (RECOMMENDED) → Use Blueprint deployment
    │   ├─ Vercel + Heroku → Manual setup
    │   └─ AWS/Azure/GCP → Full control, more complex
    └─→ For This Project:
        ├─ Backend → Render (with Postgres)
        └─ Frontend → Vercel (free tier)
```

---

## ✅ Quick Start: Choose Your Path

### Path 1: I Want to Test Locally (Fastest)

**Time**: ~10 minutes | **No Database**

```bash
# Terminal 1: Backend
cd backend
pip install -r requirements.txt
python -m playwright install chromium
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: Frontend
cd frontend
pnpm install
pnpm dev

# Open: http://localhost:3000
```

**Storage**: In-memory (data lost on restart)

---

### Path 2: I Want Full Local Setup with Database

**Time**: ~20 minutes | **With PostgreSQL & Redis**

```bash
# One command to start everything
docker-compose up --build

# Wait for all services to start
# Open: http://localhost:3000
```

**Storage**: PostgreSQL (data persists)

---

### Path 3: I Want to Deploy to Production

**Time**: ~30 minutes (first time) | **Cloud Hosted**

**Step 1**: Connect GitHub to Render

```bash
git push origin main
# Go to render.com → Connect GitHub
```

**Step 2**: Deploy Backend

```
In Render Dashboard:
1. New → Blueprint
2. Select repository
3. Click Deploy
4. Wait 5-10 minutes
```

**Step 3**: Deploy Frontend

```
In Vercel Dashboard:
1. Import Project
2. Select /frontend folder
3. Set NEXT_PUBLIC_API_URL env var
4. Deploy
```

**Result**: Live application on the internet! 🌐

---

## 🔴 Troubleshooting Guide

### Backend Issues

#### ❌ Error: `ModuleNotFoundError: No module named 'playwright'`

```bash
# Solution
cd backend
python -m playwright install chromium
pip install -r requirements.txt
```

#### ❌ Error: `Port 8000 already in use`

```bash
# Solution 1: Kill existing process
# Windows:
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# Linux/Mac:
lsof -i :8000
kill -9 <PID>

# Solution 2: Use different port
python -m uvicorn app.main:app --port 8001
```

#### ❌ Error: `Database connection refused` (postgres://...)

```bash
# Solution 1: Start Docker
docker-compose up postgres

# Solution 2: Remove DATABASE_URL env var (use in-memory)
# Delete from .env or unset:
unset DATABASE_URL

# Solution 3: Check database credentials
# In docker-compose.yml:
# POSTGRES_USER: scraper
# POSTGRES_PASSWORD: scraper
# POSTGRES_DB: scraper
```

#### ❌ Error: `CORS error from frontend`

```json
// Error: "Access to XMLHttpRequest has been blocked by CORS policy"
```

**Solution**: Update backend `.env` or `docker-compose.yml`:

```bash
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,https://your-domain.com
```

#### ❌ Error: `Application startup complete` but nothing works

```bash
# Test the backend API directly
curl http://localhost:8000/health

# If it works, check frontend config
# Check frontend/.env.local:
NEXT_PUBLIC_API_URL=http://localhost:8000
```

#### ❌ Error: `Scraper not extracting products`

```bash
# Check if Playwright browsers are installed
python -m playwright install chromium

# Check logs
# Run scraper in debug mode - check backend logs for:
docker-compose logs -f backend | grep -i "product\|error"
```

---

### Frontend Issues

#### ❌ Error: `Cannot find module 'next'`

```bash
# Solution
cd frontend
pnpm install
# or npm install
```

#### ❌ Error: `NEXT_PUBLIC_API_URL not set`

```bash
# Solution: Create .env.local
cd frontend
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local

# Restart frontend server
pnpm dev
```

#### ❌ Error: `Blank page at localhost:3000`

```bash
# Check browser console (F12 → Console tab)
# Common issues:
# 1. API URL is wrong
# 2. CORS not configured
# 3. Backend not running

# Test:
curl http://localhost:8000/health
# Should return JSON
```

#### ❌ Error: `pnpm: command not found`

```bash
# Solution: Install pnpm globally
npm install -g pnpm
pnpm --version

# Or use npm instead
npm install
npm run dev
```

---

### Docker Issues

#### ❌ Error: `Cannot connect to Docker daemon`

```bash
# Solution: Start Docker Desktop or daemon
# Windows: Open Docker Desktop app
# Linux: sudo systemctl start docker
# Mac: Open Docker.app from Applications
```

#### ❌ Error: `Service 'postgres' failed to start`

```bash
# Solution 1: Check if port 5432 is free
netstat -ano | findstr :5432

# Solution 2: Remove old volume
docker volume ls
docker volume rm amazon_bestseller_scraper_postgres_data

# Solution 3: Restart Docker
docker-compose restart postgres
```

#### ❌ Error: `Cannot bind to port 3000: Address already in use`

```bash
# Solution 1: Kill process on port 3000
netstat -ano | findstr :3000
taskkill /PID <PID> /F

# Solution 2: Use different port
docker-compose -f docker-compose.yml -p myport up
# Edit docker-compose.yml ports: ["3001:3000"]
```

#### ❌ Error: `Out of memory - container killed`

```bash
# Solution: Reduce concurrency in docker-compose.yml
environment:
  SCRAPER_MAX_WORKERS: "1"           # Reduce from 3
  SCRAPER_MAX_BROWSERS: "1"
  SCRAPER_KEEP_BROWSER_POOL: "0"
  SCRAPER_MAX_DETAIL_CONCURRENCY: "2"
  SCRAPER_MAX_VARIANT_CONCURRENCY: "1"
```

---

### Production (Render) Issues

#### ❌ Error: `Build failed: pip install failed`

```
Solution: Check requirements.txt for version conflicts
pip freeze > requirements.txt
# Rebuild in Render dashboard
```

#### ❌ Error: `Application crashed on startup`

```
Solution:
1. Check Render logs
2. Verify DATABASE_URL is set correctly
3. Check PLAYWRIGHT_BROWSERS_PATH environment variable
4. Ensure all dependencies are in requirements.txt
```

#### ❌ Error: `Frontend can't connect to backend`

```
Solution:
1. In Vercel: Set NEXT_PUBLIC_API_URL to Render backend URL
2. In Render backend: Check CORS_ORIGIN_REGEX includes your domain
3. Restart both services
```

#### ❌ Error: `Database shows as unavailable`

```
Solution:
1. In Render dashboard: Go to Database → Check status
2. Wait 5-10 minutes for database to initialize
3. Redeploy backend service
4. Check logs for connection errors
```

---

## 🧪 Testing & Validation

### Test Checklist

#### Backend Tests

```bash
# 1. Health check
curl http://localhost:8000/health
# Expected: {"status": "ok", "storage": "..."}

# 2. Docs available
curl http://localhost:8000/docs
# Expected: HTML page loads

# 3. Queue status
curl http://localhost:8000/api/admin/queue-status
# Expected: {"queue_length": 0, "active_jobs": ...}

# 4. Create scraping job
curl -X POST http://localhost:8000/api/scrape \
  -H "Content-Type: application/json" \
  -d '{"url":"https://www.amazon.com/s?k=bestsellers"}'
# Expected: {"job_id": "...", "status": "queued"}
```

#### Frontend Tests

```bash
1. Open http://localhost:3000
2. Page loads without errors
3. Input field visible
4. Submit button clickable
5. Real-time progress visible during scraping
6. Results display after completion
7. Export button works
```

#### Database Tests

```bash
# Check tables exist
docker-compose exec postgres psql -U scraper -d scraper -c "\dt"

# Check data
docker-compose exec postgres psql -U scraper -d scraper -c "SELECT COUNT(*) FROM app_jobs;"
docker-compose exec postgres psql -U scraper -d scraper -c "SELECT COUNT(*) FROM app_products;"
```

---

## 📋 Configuration Reference

### Environment Variables

#### Backend (`backend/.env`)

```bash
# Database
DATABASE_URL=postgresql://scraper:scraper@localhost:5432/scraper

# Redis (optional)
REDIS_URL=redis://localhost:6379/0

# CORS
CORS_ORIGINS=http://localhost:3000,https://domain.com

# Scraper settings
SCRAPER_MAX_WORKERS=1              # Number of concurrent jobs
SCRAPER_MAX_BROWSERS=1             # Browsers per worker
SCRAPER_KEEP_BROWSER_POOL=0        # Keep browsers running? (0=no)
SCRAPER_MAX_DETAIL_CONCURRENCY=3   # Parallel detail fetches
SCRAPER_MAX_VARIANT_CONCURRENCY=2  # Parallel variant fetches

# Render.yaml Playwright
PLAYWRIGHT_BROWSERS_PATH=0         # Don't store in Git
```

#### Frontend (`frontend/.env.local`)

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## 🚀 Performance Tuning

### For Slow Scraping

```bash
# Increase concurrency (if memory allows)
SCRAPER_MAX_DETAIL_CONCURRENCY=5
SCRAPER_MAX_VARIANT_CONCURRENCY=3

# Enable caching
REDIS_URL=redis://localhost:6379/0
```

### For Memory Constraints (Render free tier)

```bash
SCRAPER_MAX_WORKERS=1
SCRAPER_MAX_BROWSERS=1
SCRAPER_MAX_DETAIL_CONCURRENCY=2
SCRAPER_MAX_VARIANT_CONCURRENCY=1
SCRAPER_KEEP_BROWSER_POOL=0
```

### For Production Stability

```bash
# Add timeouts
SCRAPER_TIMEOUT=30
SCRAPER_RETRY_ATTEMPTS=3
SCRAPER_RETRY_BACKOFF_FACTOR=2
```

---

## 📞 Support Resources

### Useful Commands

```bash
# View all running containers
docker-compose ps

# View all logs
docker-compose logs -f

# Stop all services
docker-compose down

# Remove everything (including data)
docker-compose down -v

# Restart specific service
docker-compose restart backend

# Execute command in running container
docker-compose exec backend python -c "import sys; print(sys.version)"

# Build and push to Docker registry
docker build -f backend/Dockerfile -t myregistry/backend:latest .
docker push myregistry/backend:latest
```

### Online Resources

- **FastAPI Docs**: https://fastapi.tiangolo.com/
- **Next.js Docs**: https://nextjs.org/docs
- **Playwright Docs**: https://playwright.dev/
- **Docker Docs**: https://docs.docker.com/
- **Render Docs**: https://render.com/docs
- **Vercel Docs**: https://vercel.com/docs

---

## 🎓 Architecture Deep Dive

### Request Flow

```
1. User submits URL in Frontend
   ↓
2. POST /api/scrape → Backend API
   ↓
3. Request routed to /routers/api.py
   ↓
4. Job created in Job Queue
   ↓
5. Async worker picks up job
   ↓
6. Scraper extracts products using Playwright
   ↓
7. Products stored in PostgreSQL
   ↓
8. Progress updates sent to frontend (WebSocket)
   ↓
9. Frontend displays real-time progress
   ↓
10. Scraping complete → Results displayed
   ↓
11. User can export to Excel
```

### Component Responsibilities

```
FRONTEND (Next.js)
├─ User interface
├─ Real-time progress updates
├─ Data visualization
└─ Export functionality

BACKEND (FastAPI)
├─ API endpoints
├─ Job queue management
├─ Scraper orchestration
├─ Performance monitoring
└─ Data persistence

DATABASE (PostgreSQL)
├─ Store jobs (status, metadata)
├─ Store products (JSONB for flexibility)
└─ Historical data & analytics

CACHE (Redis - optional)
├─ Speed up repeated requests
├─ Store temporary session data
└─ Reduce database load
```

---

## ✨ Summary

### 3 Ways to Get Running

1. **Fastest** (5 min): `pnpm dev` + `python -m uvicorn...`
2. **Full Stack** (20 min): `docker-compose up --build`
3. **Production** (30 min): Render Blueprint + Vercel

Choose based on your needs! 🚀

---

**Last Updated**: May 13, 2026
**Version**: 1.0
