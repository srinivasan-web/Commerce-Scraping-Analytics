# 🚀 Complete Deployment Guide - Step by Step

## 📋 Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Prerequisites](#prerequisites)
3. [Local Development Setup](#local-development-setup)
4. [Docker-Compose Local Deployment](#docker-compose-local-deployment)
5. [Production Deployment (Render)](#production-deployment-render)
6. [Verification & Testing](#verification--testing)

---

## 🏗️ Architecture Overview

### Technology Stack

```
┌─────────────────────────────────────────────────────┐
│              FRONTEND (Next.js 15)                   │
│  - React 19 with TypeScript                         │
│  - Tailwind CSS for styling                         │
│  - Real-time job progress tracking                  │
│  - Charts & analytics visualization                 │
└──────────────────┬──────────────────────────────────┘
                   │ HTTP/WebSocket (Port 3000)
┌──────────────────▼──────────────────────────────────┐
│         BACKEND (FastAPI + Uvicorn)                  │
│  - Async Python scraping engine                     │
│  - Job queue management                             │
│  - Real-time metrics & monitoring                   │
│  - Postgres database integration                    │
│  - Redis caching (optional)                         │
└──────────────────┬──────────────────────────────────┘
                   │ Port 8000
       ┌───────────┴──────────────┐
       │                          │
   ┌───▼────┐             ┌──────▼───┐
   │POSTGRES│             │  REDIS   │
   │(DB)    │             │(Cache)   │
   └────────┘             └──────────┘
   Port 5432              Port 6379
```

### Data Flow

```
User Input (Frontend)
    ↓
API Request (/api/scrape)
    ↓
Job Queue Manager
    ↓
Async Scraper (Playwright)
    ↓
Database Storage (Products, Jobs)
    ↓
Real-time Progress (WebSocket)
    ↓
Frontend Display
```

---

## ✅ Prerequisites

### System Requirements

- **Windows/Linux/Mac** with Docker installed
- **Python 3.11+** (for local development)
- **Node.js 20+** (for frontend development)
- **pnpm** (Node package manager)
- **Git** (for version control)

### Installation Checklist

#### 1. Install Docker

- **Windows**: [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop)
- **Linux**: `sudo apt-get install docker.io`
- **Mac**: [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop)

Verify installation:

```bash
docker --version
docker-compose --version
```

#### 2. Install Python 3.11+

- **Windows**: [python.org](https://www.python.org/downloads/)
- **Linux**: `sudo apt-get install python3.11 python3.11-venv`
- **Mac**: `brew install python@3.11`

Verify:

```bash
python --version
```

#### 3. Install Node.js 20+

- Download from [nodejs.org](https://nodejs.org/)

Verify:

```bash
node --version
npm --version
```

#### 4. Install pnpm

```bash
npm install -g pnpm
pnpm --version
```

---

## 🛠️ Local Development Setup

### Step 1: Clone/Navigate to Project

```bash
cd g:\amazon_bestseller_scraper
# or wherever your project is located
```

### Step 2: Create Python Virtual Environment

```bash
# Create virtual environment
python -m venv venv

# Activate it
# On Windows:
venv\Scripts\activate
# On Linux/Mac:
source venv/bin/activate
```

### Step 3: Install Backend Dependencies

```bash
cd backend
pip install -r requirements.txt

# Install Playwright browsers
python -m playwright install chromium
cd ..
```

### Step 4: Install Frontend Dependencies

```bash
cd frontend
pnpm install
cd ..
```

### Step 5: Create Environment Files

**Backend Environment** (`backend/.env`):

```bash
# Database (optional for local dev - will use memory storage if not set)
DATABASE_URL=postgresql://scraper:scraper@localhost:5432/scraper

# Redis (optional)
REDIS_URL=redis://localhost:6379/0

# CORS origins
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000

# Scraper settings
SCRAPER_MAX_WORKERS=1
SCRAPER_MAX_BROWSERS=1
SCRAPER_KEEP_BROWSER_POOL=0
SCRAPER_MAX_DETAIL_CONCURRENCY=3
SCRAPER_MAX_VARIANT_CONCURRENCY=2
```

**Frontend Environment** (`frontend/.env.local`):

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### Step 6: Run Backend (Local - No Database)

```bash
# Terminal 1: Start Backend
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Expected Output:**

```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete
```

Test with:

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{
  "status": "ok",
  "version": "2.0.0",
  "storage": "memory",
  "features": [
    "async-scraping",
    "job-queue",
    "performance-monitoring",
    "database-store"
  ]
}
```

### Step 7: Run Frontend (Local Development)

```bash
# Terminal 2: Start Frontend
cd frontend
pnpm dev
```

**Expected Output:**

```
> Local:   http://localhost:3000
```

Visit: **http://localhost:3000**

---

## 🐳 Docker-Compose Local Deployment

This deployment includes Backend + Frontend + PostgreSQL + Redis, all running in containers.

### Step 1: Ensure Docker is Running

```bash
docker --version
docker-compose --version
```

### Step 2: Build and Start Services

Navigate to project root:

```bash
cd g:\amazon_bestseller_scraper
```

Start all services:

```bash
docker-compose up --build
```

**Services that will start:**

- **Backend**: http://localhost:8000
- **Frontend**: http://localhost:3000
- **PostgreSQL**: localhost:5432
- **Redis**: localhost:6379

### Step 3: Initialize Database Schema

```bash
# Docker automatically runs the schema on postgres startup
# Verify tables were created:
docker-compose exec postgres psql -U scraper -d scraper -c "\dt"
```

Expected output:

```
          List of relations
 Schema |      Name      | Type  | Owner
--------+----------------+-------+--------
 public | app_jobs       | table | scraper
 public | app_products   | table | scraper
(2 rows)
```

### Step 4: Verify All Services

#### Check Backend Health

```bash
curl http://localhost:8000/health
```

#### Check Storage Status

```bash
curl http://localhost:8000/api/admin/storage-status
```

Expected response:

```json
{
  "persistent": true,
  "storage": "postgres",
  "job_count": 0,
  "product_count": 0
}
```

#### Check Frontend

Open: **http://localhost:3000**

### Step 5: Test the Application

1. **In Frontend UI:**
   - Enter an Amazon URL
   - Click "Start Scraping"
   - Watch real-time progress

2. **Via API:**

```bash
curl -X POST http://localhost:8000/api/scrape \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.amazon.com/s?k=bestsellers"}'
```

### Step 6: View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f backend
docker-compose logs -f frontend
docker-compose logs -f postgres
```

### Step 7: Stop Services

```bash
docker-compose down

# To also remove volumes (database data)
docker-compose down -v
```

---

## ☁️ Production Deployment (Render)

Render is a modern cloud platform that supports Docker containers, databases, and auto-deployment.

### Step 1: Prepare for Render Deployment

#### 1a. Commit Changes to Git

```bash
git add .
git commit -m "Ready for Render deployment"
git push origin main
```

#### 1b. Verify render.yaml is in root

Check: `g:\amazon_bestseller_scraper\render.yaml`

The file should define:

- Backend web service
- Postgres database
- Environment variables

### Step 2: Create Render Account

1. Visit [render.com](https://render.com)
2. Sign up with GitHub account
3. Verify email

### Step 3: Connect GitHub Repository

1. Go to Render Dashboard
2. Click **"New +"**
3. Select **"Blueprint"**
4. Connect your GitHub account
5. Select your repository: `amazon_bestseller_scraper`
6. Click **"Connect"**

### Step 4: Deploy Blueprint

1. **Review the Blueprint:**
   - Render will read `render.yaml`
   - You'll see 2 services being created:
     - `commerce-scraping-analytics-backend` (Web Service)
     - `commerce-scraping-analytics-db` (PostgreSQL)

2. **Click "Deploy"**

3. **Wait for deployment:**
   - Backend build: ~3-5 minutes (first time)
   - Database initialization: ~1-2 minutes
   - Total: ~5-10 minutes

### Step 5: Monitor Deployment

1. **Check Backend Status:**
   - Go to Services → commerce-scraping-analytics-backend
   - Watch "Logs" tab for progress
   - Expected final log: `Application startup complete`

2. **Check Database Status:**
   - Go to Databases → commerce-scraping-analytics-db
   - Status should show as "Available"

### Step 6: Deploy Frontend (Vercel Recommended)

#### Option A: Deploy to Vercel (Recommended)

1. Go to [vercel.com](https://vercel.com)
2. Sign up with GitHub
3. Click **"Import Project"**
4. Select your repository
5. Configure:
   - **Framework**: Next.js
   - **Root Directory**: `./frontend`
   - **Environment Variables:**
     ```
     NEXT_PUBLIC_API_URL=https://commerce-scraping-analytics-backend-xxxxx.onrender.com
     ```
   - Replace `xxxxx` with your Render backend URL

6. Click **"Deploy"**

#### Option B: Deploy to Render

Add to `render.yaml`:

```yaml
- type: web
  name: commerce-scraping-analytics-frontend
  runtime: node
  plan: free
  rootDir: frontend
  buildCommand: pnpm install && pnpm build
  startCommand: pnpm start
  envVars:
    - key: NEXT_PUBLIC_API_URL
      value: https://commerce-scraping-analytics-backend-xxxxx.onrender.com
```

### Step 7: Verify Production Deployment

#### Check Backend Health

```bash
curl https://commerce-scraping-analytics-backend-xxxxx.onrender.com/health
```

#### Check Storage Status

```bash
curl https://commerce-scraping-analytics-backend-xxxxx.onrender.com/api/admin/storage-status
```

Expected response:

```json
{
  "persistent": true,
  "storage": "postgres",
  "job_count": 0,
  "product_count": 0
}
```

#### Visit Frontend

Open: `https://commerce-scraping-analytics.vercel.app`

### Step 8: Configure Custom Domain (Optional)

1. In Render Backend Service:
   - Settings → Custom Domain
   - Add your domain
   - Update Vercel with backend URL

2. In Vercel:
   - Settings → Domains
   - Add your custom domain

---

## ✅ Verification & Testing

### 1. Health Checks

#### Backend Health

```bash
# Local
curl http://localhost:8000/health

# Production
curl https://your-backend-url.onrender.com/health
```

Expected:

- `status`: "ok"
- `storage`: "postgres"

#### Frontend Load

- Local: http://localhost:3000
- Production: https://your-frontend-domain.vercel.app

### 2. Database Verification

#### Check Database Connection

```bash
# In Docker
docker-compose exec postgres psql -U scraper -d scraper -c "SELECT COUNT(*) FROM app_jobs;"

# Or from backend logs - should see:
# "Storage backend initialized: postgres"
```

#### Check Table Structure

```bash
docker-compose exec postgres psql -U scraper -d scraper -c "\d app_jobs"
docker-compose exec postgres psql -U scraper -d scraper -c "\d app_products"
```

### 3. Functional Testing

#### Test via Frontend UI

1. Open frontend
2. Enter Amazon URL: `https://www.amazon.com/s?k=bestsellers&i=aps`
3. Click "Start Scraping"
4. Observe real-time progress
5. Wait for completion
6. Check exported data

#### Test via API

```bash
# Create scraping job
curl -X POST http://localhost:8000/api/scrape \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.amazon.com/s?k=best+sellers",
    "max_pages": 1
  }' | jq '.'

# Check job status (use job_id from response)
curl http://localhost:8000/api/job/{job_id}/progress | jq '.'

# Check queue status
curl http://localhost:8000/api/admin/queue-status | jq '.'

# Check metrics
curl http://localhost:8000/api/admin/metrics | jq '.'
```

### 4. Performance Monitoring

#### Check Performance Metrics

```bash
curl http://localhost:8000/api/admin/metrics | jq '.'
```

Expected metrics:

- Average extraction time per product
- Total products extracted
- Success rate
- Cache hit rate

### 5. Export Verification

After scraping completes:

#### From Docker

```bash
docker-compose exec backend ls -lh /app/output/
```

#### From Frontend

- Click "Export to Excel"
- Verify file downloads
- Check data integrity

### 6. Log Analysis

#### View Backend Logs

```bash
# Local development
# Check terminal where you ran: python -m uvicorn...

# Docker
docker-compose logs -f backend

# Production (Render)
# Go to Service → Logs tab
```

#### Expected Log Patterns

```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete
INFO:     Starting backend with optimized async scraping...
INFO:     Initializing job queue with 1 worker(s)...
INFO:     Storage backend initialized: postgres
```

---

## 🔧 Troubleshooting

### Issue: Backend won't start

**Error**: `ModuleNotFoundError: No module named 'playwright'`

**Solution**:

```bash
cd backend
python -m playwright install chromium
```

### Issue: Database connection refused

**Error**: `psycopg2.OperationalError: could not connect to server`

**Solution**:

```bash
# Ensure Docker is running
docker-compose ps

# If postgres not running, restart
docker-compose restart postgres

# Wait 10 seconds for postgres to be ready
docker-compose logs postgres
```

### Issue: Frontend can't connect to backend

**Error**: `Failed to fetch from http://localhost:8000`

**Solution**:

1. Check backend is running: `curl http://localhost:8000/health`
2. Check CORS in backend: Should allow origin
3. Verify `NEXT_PUBLIC_API_URL` is set correctly

### Issue: Out of memory on Render free tier

**Error**: Container gets killed

**Solution**:
Set in `render.yaml`:

```yaml
envVars:
  - key: SCRAPER_MAX_WORKERS
    value: "1"
  - key: SCRAPER_MAX_BROWSERS
    value: "1"
  - key: SCRAPER_KEEP_BROWSER_POOL
    value: "0"
```

### Issue: Scraping is slow

**Solution**:

1. Increase concurrency (if memory allows):
   ```
   SCRAPER_MAX_DETAIL_CONCURRENCY=5
   SCRAPER_MAX_VARIANT_CONCURRENCY=3
   ```
2. Enable caching: Ensure REDIS_URL is set
3. Check network: Amazon might be rate-limiting

---

## 📊 Quick Reference URLs

### Local Development

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **Backend Docs**: http://localhost:8000/docs
- **PostgreSQL**: localhost:5432
- **Redis**: localhost:6379

### Production (Render + Vercel)

- **Frontend**: https://commerce-scraping-analytics.vercel.app
- **Backend API**: https://commerce-scraping-analytics-backend-xxxxx.onrender.com
- **Backend Health**: https://commerce-scraping-analytics-backend-xxxxx.onrender.com/health
- **Backend Docs**: https://commerce-scraping-analytics-backend-xxxxx.onrender.com/docs

---

## 🚀 Summary: Quick Start Commands

### Local Development (3 Terminals)

**Terminal 1: Backend**

```bash
cd backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2: Frontend**

```bash
cd frontend
pnpm dev
```

**Terminal 3: Database** (optional - use Docker)

```bash
docker-compose up postgres redis
```

### Docker Deployment (1 Command)

```bash
docker-compose up --build
```

### Production Deployment

1. Push to GitHub
2. Create Render Blueprint
3. Deploy Vercel frontend
4. Test endpoints

---

## 📝 Deployment Checklist

### Pre-Deployment

- [ ] All code committed to GitHub
- [ ] `.env` files configured (local only)
- [ ] Dependencies updated: `pip freeze`, `pnpm list`
- [ ] Tests pass locally
- [ ] Docker builds successfully

### Local Docker Testing

- [ ] `docker-compose up` completes without errors
- [ ] Backend: `curl http://localhost:8000/health` returns ok
- [ ] Frontend: http://localhost:3000 loads
- [ ] Database: Tables created successfully
- [ ] Scraping job completes successfully

### Production Deployment

- [ ] Render Blueprint created and synced
- [ ] Backend deployed and healthy
- [ ] Frontend deployed (Vercel or Render)
- [ ] Custom domain configured (optional)
- [ ] CORS origins updated
- [ ] Database auto-backup enabled (Render)
- [ ] Monitoring alerts configured

### Post-Deployment

- [ ] API health checks passing
- [ ] Real scraping job succeeds
- [ ] Frontend displays data correctly
- [ ] Database has persisted data
- [ ] Logs show no errors
- [ ] Performance metrics collected

---

## 🎯 Next Steps

1. **Choose Deployment Method:**
   - Local: Follow "Local Development Setup"
   - Docker: Follow "Docker-Compose Local Deployment"
   - Production: Follow "Production Deployment (Render)"

2. **Test Each Component:**
   - Backend API with curl
   - Frontend UI in browser
   - Database connections
   - Scraping functionality

3. **Monitor & Optimize:**
   - Watch logs for errors
   - Check performance metrics
   - Scale concurrency as needed
   - Enable caching for speed

4. **Set Up Automation:**
   - GitHub Actions for CI/CD
   - Render auto-deploy on push
   - Database auto-backups
   - Log monitoring & alerts

---

**Created**: May 13, 2026
**Status**: Complete & Ready for Deployment
