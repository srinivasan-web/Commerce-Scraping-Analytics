# 🏗️ Complete System Architecture & Database Schema

## 📐 System Architecture Diagram

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     INTERNET / USERS                             │
└──────────────────────────────┬──────────────────────────────────┘
                               │
        ┌──────────────────────┴──────────────────────┐
        │                                             │
    ┌───▼────────────────────┐          ┌────────────▼─────┐
    │   FRONTEND LAYER       │          │  EXTERNAL APIs   │
    │   (Vercel/Docker)      │          │  (Amazon, etc)   │
    │                        │          │                  │
    │  ┌────────────────┐    │          └──────────────────┘
    │  │  Next.js 15    │    │
    │  │  React 19      │    │
    │  │  TypeScript    │    │
    │  └────────────────┘    │
    │                        │
    │  Components:           │
    │  ✓ Dashboard           │
    │  ✓ Job Tracker         │
    │  ✓ Analytics           │
    │  ✓ Export Tool         │
    └────────┬───────────────┘
             │ HTTP/REST
             │ Port 3000 (local) / HTTPS (prod)
    ┌────────▼───────────────────────────────────────┐
    │         API GATEWAY LAYER                       │
    │         (FastAPI + Uvicorn)                     │
    │                                                 │
    │  Endpoints:                                     │
    │  POST   /api/scrape                             │
    │  GET    /api/job/{id}/progress                  │
    │  GET    /api/admin/queue-status                 │
    │  GET    /api/admin/metrics                      │
    │  GET    /api/admin/storage-status               │
    │  GET    /health                                 │
    │                                                 │
    │  Middleware:                                    │
    │  ✓ CORS (Cross-Origin Resource Sharing)        │
    │  ✓ Error Handling                               │
    │  ✓ Request Logging                              │
    │  ✓ Rate Limiting (optional)                     │
    └────────┬────────────────────────────────────────┘
             │ Port 8000 (local) / HTTPS (prod)
    ┌────────▼────────────────────────────────────────────────┐
    │            BUSINESS LOGIC LAYER                          │
    │                                                          │
    │  ┌──────────────────────────────────────────┐            │
    │  │ JOB QUEUE MANAGER                        │            │
    │  │ ✓ Accept scraping requests               │            │
    │  │ ✓ Queue jobs (FIFO)                      │            │
    │  │ ✓ Track job status                       │            │
    │  │ ✓ Handle retries                         │            │
    │  └──────────────────────────────────────────┘            │
    │                                                          │
    │  ┌──────────────────────────────────────────┐            │
    │  │ SCRAPER ENGINE                           │            │
    │  │ ✓ Launch Playwright browsers             │            │
    │  │ ✓ Navigate to Amazon                     │            │
    │  │ ✓ Extract product data                   │            │
    │  │ ✓ Handle pagination                      │            │
    │  │ ✓ Retry on failure                       │            │
    │  └──────────────────────────────────────────┘            │
    │                                                          │
    │  ┌──────────────────────────────────────────┐            │
    │  │ PERFORMANCE MONITOR                      │            │
    │  │ ✓ Track extraction metrics               │            │
    │  │ ✓ Calculate success rates                │            │
    │  │ ✓ Monitor memory usage                   │            │
    │  │ ✓ Detect bottlenecks                     │            │
    │  └──────────────────────────────────────────┘            │
    │                                                          │
    │  ┌──────────────────────────────────────────┐            │
    │  │ CACHE MANAGER                            │            │
    │  │ ✓ Store frequently accessed data         │            │
    │  │ ✓ Reduce database queries                │            │
    │  │ ✓ TTL-based expiration                   │            │
    │  └──────────────────────────────────────────┘            │
    └────────┬────────────────────────────────────────────────┘
             │
    ┌────────┼─────────────────────────────────────┐
    │        │                                     │
    ▼        ▼                                     ▼
┌────────┐  ┌───────────────────┐          ┌─────────────┐
│        │  │   PostgreSQL DB   │          │   Redis     │
│Logs /  │  │   (Persistent)    │          │  (Cache)    │
│Output  │  │                   │          │             │
│        │  │  Tables:          │          │ Optional    │
└────────┘  │  ✓ app_jobs       │          │             │
            │  ✓ app_products   │          └─────────────┘
            │                   │
            │  ✓ JSONB storage  │
            │  ✓ Flexible schema│
            └───────────────────┘
```

---

## 🗄️ Database Schema

### Table: `app_jobs`

```sql
CREATE TABLE app_jobs (
    id UUID PRIMARY KEY,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Job metadata
    url VARCHAR(2048) NOT NULL,
    status VARCHAR(50) NOT NULL,  -- queued, running, completed, failed

    -- Results
    total_products INTEGER,
    extracted_products INTEGER,
    failed_products INTEGER,

    -- Error tracking
    error_message TEXT,
    error_details JSONB,

    -- Performance metrics
    start_time TIMESTAMP,
    end_time TIMESTAMP,
    duration_seconds FLOAT,

    -- Settings & configuration
    config JSONB,  -- Scraper settings used for this job

    -- Additional data (flexible)
    metadata JSONB
);

Indexes:
- PRIMARY KEY (id)
- INDEX (status)
- INDEX (created_at DESC)
- INDEX (updated_at DESC)
```

### Table: `app_products`

```sql
CREATE TABLE app_products (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Relationship
    job_id UUID NOT NULL REFERENCES app_jobs(id) ON DELETE CASCADE,

    -- Product data (stored as JSONB for flexibility)
    payload JSONB NOT NULL,

    -- Indexes for search
    asin VARCHAR(50),
    title VARCHAR(500),
    price NUMERIC(10, 2),
    rating NUMERIC(3, 2),

    -- Extraction metadata
    extraction_time_ms INTEGER,
    extraction_status VARCHAR(50)
);

Indexes:
- PRIMARY KEY (id)
- INDEX (job_id)
- INDEX (asin)
- INDEX (created_at DESC)
- FULL TEXT SEARCH on (title)
```

### JSONB Payload Structure (app_products)

```json
{
  "asin": "B0ABCD1234",
  "title": "Product Name",
  "price": 29.99,
  "original_price": 39.99,
  "discount_percentage": 25,
  "rating": 4.5,
  "review_count": 1234,
  "availability": "In Stock",
  "prime": true,
  "brand": "Brand Name",
  "category": "Electronics",
  "url": "https://www.amazon.com/...",
  "image_url": "https://images-amazon.com/...",
  "description": "Product description...",
  "features": ["Feature 1", "Feature 2"],
  "variants": [
    {
      "name": "Color",
      "options": ["Black", "White", "Blue"]
    }
  ]
}
```

---

## 🔄 Data Flow Diagram

### Complete Request-Response Cycle

```
┌─────────────────────┐
│  USER (Frontend)    │
│  Opens browser to   │
│  http://localhost:3000
└──────────┬──────────┘
           │
           │ 1. User enters Amazon URL
           │ 2. Clicks "Start Scraping"
           ▼
┌──────────────────────────────────┐
│  Frontend (React Component)       │
│  - Validates URL                 │
│  - Shows loading spinner         │
│  - Sends POST request            │
└──────────┬───────────────────────┘
           │
           │ POST /api/scrape
           │ {
           │   "url": "https://amazon.com/..."
           │ }
           ▼
┌──────────────────────────────────┐
│  Backend API (FastAPI)           │
│  - CORS validation               │
│  - Input validation              │
│  - Create new Job                │
└──────────┬───────────────────────┘
           │
           │ Job ID: 550e8400-e29b-41d4-a716-446655440000
           ▼
┌──────────────────────────────────┐
│  Job Queue Manager               │
│  - Add job to queue              │
│  - Update status: queued         │
│  - Persist to database           │
└──────────┬───────────────────────┘
           │
           │ Return response to frontend:
           │ {
           │   "job_id": "550e8400-...",
           │   "status": "queued"
           │ }
           ▼
┌──────────────────────────────────┐
│  Frontend (React)                │
│  - Receive job_id                │
│  - Start polling: GET /api/job/{id}/progress
│  - Display: "Initializing..."    │
└──────────────────────────────────┘

─── Background: Async Worker ───

           │ Worker picks up job from queue
           ▼
┌──────────────────────────────────┐
│  Scraper Engine                  │
│  1. Launch Playwright browser    │
│  2. Navigate to URL              │
│  3. Wait for page load           │
│  4. Extract product list         │
└──────────┬───────────────────────┘
           │
           │ For each product:
           ▼
┌──────────────────────────────────┐
│  Product Extractor               │
│  1. Get ASIN, title, price       │
│  2. Get rating, reviews          │
│  3. Get images                   │
│  4. Get description              │
└──────────┬───────────────────────┘
           │
           │ Save product
           ▼
┌──────────────────────────────────┐
│  Database (PostgreSQL)           │
│  - Insert into app_products      │
│  - Reference job_id              │
│  - Store JSONB payload           │
└──────────┬───────────────────────┘
           │
           │ Update job progress
           ▼
┌──────────────────────────────────┐
│  Job Status Manager              │
│  - Increment extracted_products  │
│  - Calculate progress %          │
│  - Update status: running        │
│  - Store in database             │
└──────────┬───────────────────────┘

─── Continuous Polling ───

           │ Frontend polling every 1-2 seconds
           │ GET /api/job/{id}/progress
           ▼
┌──────────────────────────────────┐
│  API Returns:                    │
│  {                               │
│    "job_id": "550e8400-...",     │
│    "status": "running",          │
│    "progress": 45,               │
│    "extracted": 45,              │
│    "total": 100                  │
│  }                               │
└──────────┬───────────────────────┘
           │
           │ Frontend updates UI in real-time
           ▼
┌──────────────────────────────────┐
│  User sees:                      │
│  Progress bar: ███░░░░░░░░ 45%   │
│  Status: Running...              │
│  Products: 45 / 100              │
└──────────────────────────────────┘

─── Scraping Complete ───

           │ All products extracted
           ▼
┌──────────────────────────────────┐
│  Scraper finishes                │
│  - Close browser                 │
│  - Update status: completed      │
│  - Record end_time               │
│  - Calculate duration            │
└──────────┬───────────────────────┘
           │
           ▼
┌──────────────────────────────────┐
│  Database Update                 │
│  - Status: completed             │
│  - total_products: 100           │
│  - duration_seconds: 45.3        │
└──────────┬───────────────────────┘
           │
           │ Frontend next poll sees status=completed
           ▼
┌──────────────────────────────────┐
│  Frontend (React)                │
│  - Stop polling                  │
│  - Fetch results                 │
│  - Display: 100 products         │
│  - Show success message          │
│  - Enable Export button          │
└──────────┬───────────────────────┘
           │
           │ User clicks "Export to Excel"
           ▼
┌──────────────────────────────────┐
│  Export Service                  │
│  - Query all products for job    │
│  - Convert to DataFrame          │
│  - Create Excel file             │
│  - Return as download            │
└──────────┬───────────────────────┘
           │
           │ .xlsx file downloaded
           ▼
┌──────────────────────────────────┐
│  User (Local File)               │
│  Opens:                          │
│  amazon_bestsellers_<date>.xlsx  │
│                                  │
│  Contains 100 rows of products   │
└──────────────────────────────────┘
```

---

## 🔌 API Endpoints

### 1. Submit Scraping Job

```
POST /api/scrape

Request:
{
  "url": "https://www.amazon.com/s?k=bestsellers",
  "max_pages": 5
}

Response:
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued",
  "created_at": "2026-05-13T10:30:00Z"
}

Status Codes:
- 202: Accepted (job queued)
- 400: Bad request (invalid URL)
- 429: Too many requests (rate limited)
- 500: Server error
```

### 2. Get Job Progress

```
GET /api/job/{job_id}/progress

Response:
{
  "job_id": "550e8400-...",
  "status": "running",
  "progress": 45,
  "extracted_products": 45,
  "total_products": 100,
  "elapsed_seconds": 30,
  "estimated_remaining_seconds": 37
}

Status: queued | running | completed | failed
```

### 3. Get Job Results

```
GET /api/job/{job_id}/results

Response:
{
  "job_id": "550e8400-...",
  "status": "completed",
  "products": [
    {
      "asin": "B0ABCD1234",
      "title": "Product 1",
      "price": 29.99,
      ...
    }
  ]
}
```

### 4. Export to Excel

```
GET /api/job/{job_id}/export?format=xlsx

Response:
- Binary Excel file
- Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
```

### 5. Admin Endpoints

#### Queue Status

```
GET /api/admin/queue-status

Response:
{
  "queue_length": 2,
  "active_jobs": 1,
  "workers": 1,
  "completed_jobs": 42
}
```

#### Storage Status

```
GET /api/admin/storage-status

Response:
{
  "persistent": true,
  "storage": "postgres",
  "job_count": 50,
  "product_count": 5000,
  "database": {
    "host": "localhost",
    "port": 5432,
    "pool_size": 5
  }
}
```

#### Performance Metrics

```
GET /api/admin/metrics

Response:
{
  "average_metrics": {
    "products_per_job": 98.2,
    "success_rate": 94.5,
    "avg_extraction_time_ms": 1234,
    "cache_hit_rate": 67.8
  },
  "timeline_analysis": {
    "hour": "metrics per hour",
    "day": "metrics per day"
  }
}
```

#### Health Check

```
GET /health

Response:
{
  "status": "ok",
  "version": "2.0.0",
  "storage": "postgres",
  "features": ["async-scraping", "job-queue", "performance-monitoring"]
}
```

---

## 🔐 Security Considerations

### Frontend Security

- ✓ CORS validation (only allowed origins)
- ✓ Input validation (URL format)
- ✓ XSS prevention (React escaping)
- ✓ HTTPS only (production)

### Backend Security

- ✓ CORS headers
- ✓ Input sanitization
- ✓ Rate limiting (optional)
- ✓ Error message obfuscation
- ✓ Database connection pooling
- ✓ Async/await for non-blocking I/O

### Database Security

- ✓ Unique credentials (not root)
- ✓ Connection pooling
- ✓ Prepared statements (SQL injection prevention)
- ✓ Data encryption at rest (optional)
- ✓ Backups enabled

### Deployment Security

- ✓ Environment variables (no secrets in code)
- ✓ HTTPS certificates (Let's Encrypt)
- ✓ Firewall rules
- ✓ API key authentication (optional)
- ✓ VPN access (for admin endpoints)

---

## 📊 Performance Optimization

### Database Optimization

```sql
-- Add indexes for common queries
CREATE INDEX idx_jobs_status ON app_jobs(status);
CREATE INDEX idx_jobs_created ON app_jobs(created_at DESC);
CREATE INDEX idx_products_job_id ON app_products(job_id);
CREATE INDEX idx_products_asin ON app_products(asin);

-- Analyze table statistics
ANALYZE app_jobs;
ANALYZE app_products;
```

### Query Optimization

```python
# Use database connection pooling
DB_POOL_SIZE = 5

# Use pagination for large result sets
ITEMS_PER_PAGE = 100

# Add caching for frequently accessed data
CACHE_TTL = 3600  # 1 hour
```

### Scraper Optimization

```python
# Parallel extraction
SCRAPER_MAX_DETAIL_CONCURRENCY = 3  # Fetch details in parallel

# Browser pool reuse
SCRAPER_MAX_BROWSERS = 1
SCRAPER_KEEP_BROWSER_POOL = 0  # Release after job

# Memory management
SCRAPER_MAX_WORKERS = 1  # One job at a time
```

---

## 📈 Scaling Considerations

### Vertical Scaling (Bigger Machine)

- Increase `SCRAPER_MAX_WORKERS` to 3-5
- Increase `SCRAPER_MAX_BROWSERS` to 2-3
- Increase `DATABASE_POOL_SIZE` to 10-20
- Use more CPU cores

### Horizontal Scaling (Multiple Machines)

```yaml
# Option 1: Multiple backend instances + Load Balancer
backend-1:
  - Handles jobs 1-100
backend-2:
  - Handles jobs 101-200
load-balancer:
  - Routes requests to available backend

# Option 2: Separate worker service
api-service:
  - Handles /api/scrape requests
  - Adds job to queue
worker-service:
  - Picks jobs from queue
  - Runs scrapers
  - Stores results
```

### Database Scaling

- Read replicas for analytics queries
- Sharding by job_id for very large tables
- Archive old jobs to cold storage

---

## 🎯 Deployment Checklist

### Pre-Deployment

- [ ] All tests passing
- [ ] Code reviewed and approved
- [ ] Dependencies updated
- [ ] Database migrations tested
- [ ] Performance tested
- [ ] Security audit passed
- [ ] Documentation updated

### Deployment

- [ ] Create backup of current database
- [ ] Run database migrations
- [ ] Deploy new backend code
- [ ] Deploy new frontend code
- [ ] Run smoke tests
- [ ] Monitor error rates

### Post-Deployment

- [ ] Verify all endpoints working
- [ ] Check database integrity
- [ ] Monitor performance metrics
- [ ] Verify backups created
- [ ] Update status page
- [ ] Notify users of changes

---

**Documentation Version**: 1.0
**Last Updated**: May 13, 2026
