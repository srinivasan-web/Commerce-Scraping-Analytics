# 🔧 Quick Deployment Reference

## Option 1: Local Development (Fastest)

```bash
# Terminal 1: Backend
cd g:\amazon_bestseller_scraper
venv\Scripts\activate
python -m playwright install  # First time only
python -m uvicorn backend.app.main:app --reload

# Terminal 2: Frontend
cd g:\amazon_bestseller_scraper\frontend
npm install  # First time only
npm run dev
```

**Access:** http://localhost:3000  
**Time:** 2-5 minutes setup

---

## Option 2: Docker (Recommended for Testing/Prod)

```bash
cd g:\amazon_bestseller_scraper

# One-time build
docker-compose up -d --build

# Next time just
docker-compose up -d
```

**Access:** http://localhost:3000  
**Time:** 3-10 minutes (first build)

---

## Option 3: Production (Azure/AWS)

### Prerequisites

- Docker Desktop installed
- Azure/AWS account configured
- CLI tools installed (az/aws)

### Deploy to Azure

```bash
$registryName = "amazonscraper"
$resourceGroup = "amazon-scraper-rg"

# Create and build
az group create --name $resourceGroup --location eastus
az acr create --resource-group $resourceGroup --name $registryName --sku Basic
az acr login --name $registryName

# Push images
az acr build --registry $registryName -f backend/Dockerfile -t backend:latest .
az acr build --registry $registryName -f frontend/Dockerfile -t frontend:latest .

# Deploy
az container create --registry $registryName --name amazon-scraper-app ...
```

**Access:** https://yourappname.azurewebsites.net  
**Time:** 10-20 minutes setup

---

## Status & Monitoring

### Check Running Services

```bash
# Local
python -m uvicorn backend.app.main:app

# Docker
docker-compose ps

# Docker logs
docker-compose logs -f backend
docker-compose logs -f frontend
```

### Health Checks

```bash
# Backend
curl http://localhost:8000/health

# Frontend
http://localhost:3000

# API Documentation
http://localhost:8000/docs

# Admin Panel
http://localhost:8000/api/admin/queue-status
```

---

## Database Setup

### Local (File-based SQLite by default)

No setup needed - database auto-creates on first run.

### Docker (PostgreSQL)

```bash
# Connect
docker exec -it amazon-bestseller-postgres psql -U scraper -d scraper

# Check tables
\dt

# See jobs
SELECT * FROM jobs LIMIT 5;
```

---

## Troubleshooting

### Backend Won't Start

```bash
# Playwright not installed
python -m playwright install

# Port 8000 in use
netstat -ano | findstr 8000
taskkill /PID <pid> /F
```

### Frontend Won't Build

```bash
# Clear cache
rm -r node_modules package-lock.json
npm install
npm run dev
```

### Docker Issues

```bash
# Logs
docker-compose logs

# Rebuild
docker-compose down -v
docker-compose up -d --build

# Clean everything
docker system prune -a
```

### Database Connection Failed

```bash
# Verify postgres running
docker-compose ps postgres

# Restart
docker-compose restart postgres

# Check logs
docker-compose logs postgres
```

---

## Files Structure

```
amazon_bestseller_scraper/
├── backend/                    # FastAPI Python backend
│   ├── Dockerfile             # Backend container recipe
│   ├── requirements.txt        # Python dependencies
│   └── app/
│       └── services/
│           ├── async_scraper.py
│           ├── job_queue.py
│           └── performance_metrics.py
│
├── frontend/                   # Next.js React frontend
│   ├── Dockerfile             # Frontend container recipe
│   ├── package.json           # Node dependencies
│   └── app/
│
├── docker-compose.yml         # Multi-container orchestration
├── database_schema.sql        # Database initialization
├── logs/                      # Log files
└── output/                    # Scraped data exports
```

---

## Environment Variables

### Backend (.env)

```
DATABASE_URL=postgresql://scraper:scraper@postgres:5432/scraper
REDIS_URL=redis://redis:6379
CORS_ORIGINS=http://localhost:3000
PYTHONUNBUFFERED=1
```

### Frontend (.env.local)

```
NEXT_PUBLIC_API_URL=http://localhost:8000
NODE_ENV=development
```

---

## Commands Cheat Sheet

| Task           | Command                                           |
| -------------- | ------------------------------------------------- |
| Start local    | `python -m uvicorn backend.app.main:app --reload` |
| Start Docker   | `docker-compose up -d`                            |
| Stop Docker    | `docker-compose down`                             |
| View logs      | `docker-compose logs -f`                          |
| Rebuild        | `docker-compose up -d --build`                    |
| Clean up       | `docker system prune -a`                          |
| Backend health | `curl http://localhost:8000/health`               |
| API docs       | `http://localhost:8000/docs`                      |
| Frontend       | `http://localhost:3000`                           |

---

## Performance Metrics

### Expected Startup Times

- **Local Backend:** 5-10 seconds
- **Local Frontend:** 3-5 seconds (dev mode)
- **Docker Stack:** 30-60 seconds
- **First Docker Build:** 5-10 minutes

### Expected Response Times

- **Health Check:** <100ms
- **Scrape Job Start:** <500ms
- **Product Extraction:** 60-90 seconds (per job)
- **Frontend Page Load:** <2 seconds

### Resource Requirements

- **Backend:** 512MB RAM minimum, 1GB recommended
- **Frontend:** 256MB RAM minimum
- **Database:** 512MB storage minimum
- **Total Docker:** 2GB RAM, 5GB disk recommended

---

**Full details:** See `DEPLOYMENT_STEP_BY_STEP.md`

**Choose your option and follow the steps!** 🚀
