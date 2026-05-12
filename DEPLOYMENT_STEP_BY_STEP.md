# 🚀 Complete Deployment Guide - Step by Step

## Overview

```
┌──────────────┐
│   Frontend   │ ← Next.js React App (Port 3000)
│  (Docker)    │
└──────┬───────┘
       │
       ↓ API Calls (http://backend:8000)

┌──────────────┐
│   Backend    │ ← FastAPI Python App (Port 8000)
│  (Docker)    │
└──────┬───────┘
       │
       ↓ SQL Queries

┌──────────────┐
│ PostgreSQL   │ ← Database (Port 5432)
│  (Docker)    │
└──────────────┘
```

---

# PART 1: Local Development Setup (No Docker)

## Step 1: Setup Backend Locally

### 1.1 Navigate to Project

```bash
cd g:\amazon_bestseller_scraper
```

### 1.2 Create & Activate Virtual Environment

```bash
python -m venv venv
venv\Scripts\activate
```

### 1.3 Install Python Dependencies

```bash
pip install -r backend/requirements.txt
```

Expected output: `Successfully installed fastapi uvicorn playwright ...`

### 1.4 Install Playwright Browsers ⚠️ IMPORTANT

```bash
python -m playwright install
```

Wait for download to complete (~5 minutes, 300MB).

### 1.5 Start Backend Server

```bash
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Expected output:**

```
✅ INFO:     Uvicorn running on http://0.0.0.0:8000
✅ INFO:     Application startup complete
```

**Leave this terminal open!** Move to next step in a NEW terminal.

---

## Step 2: Setup Frontend Locally

### 2.1 Open New Terminal (Keep Backend Running!)

### 2.2 Navigate to Frontend

```bash
cd g:\amazon_bestseller_scraper\frontend
```

### 2.3 Install Node Dependencies

```bash
npm install
```

Or with pnpm:

```bash
pnpm install
```

### 2.4 Create Environment File

```bash
# Create file: frontend/.env.local
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### 2.5 Start Development Server

```bash
npm run dev
```

**Expected output:**

```
✅ Local:        http://localhost:3000
```

---

## Step 3: Test Application

### 3.1 Open Browser

- Backend: http://localhost:8000/health
- Frontend: http://localhost:3000
- API Docs: http://localhost:8000/docs

### 3.2 Test Scraping

1. Go to http://localhost:3000
2. Enter Amazon URL
3. Click "Start Scraping"
4. Monitor progress in real-time

### 3.3 Check Logs

```bash
# Backend logs in terminal
# Frontend logs in terminal
# Job logs in: logs/scraper.log
```

---

# PART 2: Docker Deployment

## Prerequisites

Install Docker Desktop from: https://www.docker.com/products/docker-desktop/

Verify installation:

```bash
docker --version
docker-compose --version
```

---

## Step 1: Prepare Environment Files

### 1.1 Create `.env` for Backend

```bash
# File: .env
PYTHONUNBUFFERED=1
DATABASE_URL=postgresql://scraper:scraper@postgres:5432/scraper
REDIS_URL=redis://redis:6379
CORS_ORIGINS=http://localhost:3000,http://localhost:3001
```

### 1.2 Create `.env.docker` for Frontend

```bash
# File: frontend/.env.local.docker
NEXT_PUBLIC_API_URL=http://backend:8000
```

---

## Step 2: Build Docker Images

### 2.1 Build Backend Image

```bash
cd g:\amazon_bestseller_scraper

docker build -f backend/Dockerfile -t amazon-scraper-backend:latest .
```

**Expected output:**

```
✅ Successfully tagged amazon-scraper-backend:latest
```

### 2.2 Build Frontend Image

```bash
docker build -f frontend/Dockerfile \
  --build-arg NEXT_PUBLIC_API_URL=http://backend:8000 \
  -t amazon-scraper-frontend:latest .
```

**Expected output:**

```
✅ Successfully tagged amazon-scraper-frontend:latest
```

### 2.3 Verify Images Built

```bash
docker images | findstr amazon-scraper
```

Should show:

```
amazon-scraper-backend   latest
amazon-scraper-frontend  latest
```

---

## Step 3: Start Entire Stack with Docker Compose

### 3.1 Start All Services

```bash
cd g:\amazon_bestseller_scraper

docker-compose up -d
```

**Expected output:**

```
✅ Creating postgres ... done
✅ Creating redis ... done
✅ Creating backend ... done
✅ Creating frontend ... done
```

### 3.2 Verify Services Running

```bash
docker-compose ps
```

Should show:

```
NAME        STATUS      PORTS
postgres    Up 2 min    0.0.0.0:5432->5432/tcp
redis       Up 2 min    0.0.0.0:6379->6379/tcp
backend     Up 1 min    0.0.0.0:8000->8000/tcp
frontend    Up 1 min    0.0.0.0:3000->3000/tcp
```

### 3.3 Check Logs

```bash
# Backend logs
docker-compose logs backend -f

# Frontend logs
docker-compose logs frontend -f

# All logs
docker-compose logs -f
```

---

## Step 4: Test Dockerized Application

### 4.1 Health Checks

```bash
# Backend health
curl http://localhost:8000/health

# Should return:
# {"status":"ok","version":"2.0.0","features":["async-scraping",...]}
```

### 4.2 API Documentation

- Open: http://localhost:8000/docs
- Try: POST /scrape with test URL

### 4.3 Frontend Access

- Open: http://localhost:3000
- Test scraping job

### 4.4 Database

```bash
# Connect to postgres
docker exec -it amazon-bestseller-postgres psql -U scraper -d scraper

# List tables
\dt

# Check jobs
SELECT * FROM jobs LIMIT 5;
```

---

# PART 3: Production Deployment (Cloud)

## Option A: Deploy to Azure Container Instances

### A.1 Create Azure Container Registry

```bash
# Set variables
$resourceGroup = "amazon-scraper-rg"
$registryName = "amazonscraper"
$location = "eastus"

# Create resource group
az group create --name $resourceGroup --location $location

# Create registry
az acr create --resource-group $resourceGroup \
  --name $registryName --sku Basic
```

### A.2 Build & Push Images

```bash
# Login to registry
az acr login --name $registryName

# Build backend
az acr build --registry $registryName \
  --image amazon-scraper-backend:latest \
  -f backend/Dockerfile .

# Build frontend
az acr build --registry $registryName \
  --image amazon-scraper-frontend:latest \
  -f frontend/Dockerfile \
  --build-arg NEXT_PUBLIC_API_URL=https://yourappname.azurewebsites.net \
  .
```

### A.3 Deploy Container Group

```bash
# Create container group
az container create \
  --resource-group $resourceGroup \
  --name amazon-scraper-group \
  --image $registryName.azurecr.io/amazon-scraper-backend:latest \
  --registry-login-server $registryName.azurecr.io \
  --registry-username <username> \
  --registry-password <password> \
  --ip-address Public \
  --ports 8000 3000 \
  --environment-variables \
    DATABASE_URL=postgresql://scraper:scraper@postgres:5432/scraper \
    REDIS_URL=redis://redis:6379
```

---

## Option B: Deploy to AWS ECS

### B.1 Create ECR Repositories

```bash
# Backend
aws ecr create-repository --repository-name amazon-scraper-backend

# Frontend
aws ecr create-repository --repository-name amazon-scraper-frontend
```

### B.2 Build & Push Images

```bash
# Login
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com

# Build and push backend
docker build -f backend/Dockerfile -t <account-id>.dkr.ecr.us-east-1.amazonaws.com/amazon-scraper-backend:latest .
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/amazon-scraper-backend:latest

# Build and push frontend
docker build -f frontend/Dockerfile -t <account-id>.dkr.ecr.us-east-1.amazonaws.com/amazon-scraper-frontend:latest .
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/amazon-scraper-frontend:latest
```

### B.3 Create ECS Task Definition

```bash
# Create task-definition.json with container specs
aws ecs register-task-definition --cli-input-json file://task-definition.json
```

### B.4 Create ECS Service

```bash
aws ecs create-service \
  --cluster scraper-cluster \
  --service-name amazon-scraper-service \
  --task-definition amazon-scraper-task:1 \
  --desired-count 2 \
  --load-balancers targetGroupArn=arn:aws:elasticloadbalancing:...,containerName=backend,containerPort=8000
```

---

# PART 4: Manage Containers

## Common Docker Commands

### View Status

```bash
# All containers
docker-compose ps

# Specific service
docker-compose ps backend

# Logs
docker-compose logs backend -f --tail=100
```

### Rebuild Services

```bash
# Rebuild all
docker-compose up -d --build

# Rebuild specific service
docker-compose up -d --build backend
```

### Stop Services

```bash
# Stop all
docker-compose down

# Stop specific
docker stop amazon-scraper-backend

# Stop and remove volumes
docker-compose down -v
```

### Access Container Terminal

```bash
# Backend bash
docker exec -it amazon-scraper-backend bash

# Frontend bash
docker exec -it amazon-scraper-frontend bash

# Database psql
docker exec -it amazon-scraper-postgres psql -U scraper -d scraper
```

### Clean Up

```bash
# Remove stopped containers
docker container prune

# Remove unused images
docker image prune

# Remove unused volumes
docker volume prune

# Full cleanup
docker system prune -a --volumes
```

---

# PART 5: Monitoring & Troubleshooting

## Check Health

### Backend Health

```bash
curl http://localhost:8000/health
```

### Admin Endpoints

```bash
# Queue status
curl http://localhost:8000/api/admin/queue-status

# System metrics
curl http://localhost:8000/api/admin/metrics

# Job performance
curl http://localhost:8000/api/admin/job/{id}/performance
```

### Database Connection

```bash
# Inside backend container
docker exec amazon-scraper-backend \
  python -c "from backend.app.services.store import init_store; await init_store()"
```

### Frontend Build Status

```bash
# Check Next.js build
docker exec amazon-scraper-frontend \
  ls -la .next/standalone
```

## Common Issues & Fixes

### Issue: "Port 8000 already in use"

```bash
# Stop conflicting container
docker stop $(docker ps -a -q --filter "expose=8000")

# Or use different port
docker-compose -f docker-compose.yml -p new_port up -d
```

### Issue: "Database connection failed"

```bash
# Check postgres logs
docker-compose logs postgres

# Verify postgres is running
docker-compose ps postgres

# Restart postgres
docker-compose restart postgres
```

### Issue: "Playwright browser not found"

```bash
# Rebuild backend image
docker-compose build --no-cache backend

# The Dockerfile uses playwright/python image with browsers included
```

### Issue: "Frontend can't reach backend"

```bash
# Check network
docker network ls

# Inspect backend container
docker inspect amazon-scraper-backend

# Verify API_URL in frontend
docker exec amazon-scraper-frontend env | grep NEXT_PUBLIC_API_URL
```

---

# PART 6: Performance Tuning

## Backend Optimization

```yaml
# Update docker-compose.yml
backend:
  environment:
    MAX_WORKERS: 5 # More concurrent jobs
    MAX_BROWSERS: 5 # More browser instances
    CONNECTION_POOL_SIZE: 10 # Database connections
```

## Frontend Optimization

```yaml
frontend:
  environment:
    NODE_ENV: production
    NODE_OPTIONS: "--max-old-space-size=2048"
```

## Database Optimization

```bash
# Connect to database
docker exec -it amazon-scraper-postgres psql -U scraper -d scraper

# Create indexes
CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_created_at ON jobs(created_at);
```

---

# PART 7: Scaling for Production

## Multi-instance Backend

```yaml
services:
  backend:
    deploy:
      replicas: 3
    environment:
      INSTANCE_ID: "backend-1"
```

## Load Balancer

```yaml
services:
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
    depends_on:
      - backend
```

## Monitoring Stack

```yaml
services:
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3001:3000"
```

---

# Quick Start Commands

## Local Development

```bash
# Terminal 1: Backend
cd g:\amazon_bestseller_scraper
venv\Scripts\activate
python -m uvicorn backend.app.main:app --reload

# Terminal 2: Frontend
cd g:\amazon_bestseller_scraper\frontend
npm run dev
```

## Docker Development

```bash
cd g:\amazon_bestseller_scraper
docker-compose up -d
# Wait 30 seconds for containers to start
# Access: http://localhost:3000
```

## Docker Cleanup & Rebuild

```bash
docker-compose down -v
docker-compose up -d --build
```

---

## 📞 Support

- **Backend Docs**: http://localhost:8000/docs
- **Frontend**: http://localhost:3000
- **Logs**: `docker-compose logs -f`
- **Database**: `docker exec -it amazon-scraper-postgres psql ...`

---

**Ready to deploy? Start with Part 1 or Part 2 depending on your environment!** 🚀
