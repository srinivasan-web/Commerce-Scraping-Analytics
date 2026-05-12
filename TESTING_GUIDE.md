# 🧪 Backend Testing & API Validation Guide

## Quick Start Tests

### Step 1: Start Backend

```bash
cd g:\amazon_bestseller_scraper
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Step 2: Access API Documentation

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

## 📋 Test Scenarios

### Scenario 1: Health Check

```bash
curl http://localhost:8000/health
```

✅ Expected: `{"status":"ok","version":"2.0.0",...}`

---

### Scenario 2: Start Scraping Job with Sliders

**Using Postman:**

```
POST http://localhost:8000/api/scrape
Authorization: Bearer test-token
Content-Type: application/json

{
  "url": "https://www.amazon.in/gp/bestsellers/sports/",
  "website": "amazon",
  "options": {
    "max_products": 50,
    "variant_depth": 3,
    "timeout_seconds": 60,
    "concurrent_products": 5,
    "max_pages": 2,
    "include_reviews": true,
    "include_variants": true,
    "high_priority": false
  }
}
```

**Using cURL:**

```bash
curl -X POST http://localhost:8000/api/scrape \
  -H "Authorization: Bearer test-token" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.amazon.in/gp/bestsellers/sports/",
    "website": "amazon",
    "options": {
      "max_products": 50,
      "variant_depth": 3,
      "timeout_seconds": 60,
      "concurrent_products": 5,
      "max_pages": 1
    }
  }'
```

✅ Expected: Returns job object with ID

---

### Scenario 3: Get Job Details with Real-Time Metrics

```bash
curl http://localhost:8000/api/jobs/{job_id}/details \
  -H "Authorization: Bearer test-token"
```

✅ Expected Response:

```json
{
  "job_id": "abc-123",
  "status": "running",
  "progress": 65,
  "current_step": 3,
  "stage": "extracting",
  "message": "🔍 Extracting product information...",
  "products_found": 97,
  "total_products": 150,
  "speed": 1.5,
  "avg_time_per_product": 2.5,
  "success_rate": 98.5,
  "started_at": "2026-05-12T10:30:00Z",
  "estimated_completion": "2026-05-12T10:45:00Z",
  "duration_seconds": 900
}
```

---

### Scenario 4: Dashboard Summary (System Health)

```bash
curl http://localhost:8000/api/analytics/dashboard/summary \
  -H "Authorization: Bearer test-token"
```

✅ Expected Response:

```json
{
  "total_jobs": 10,
  "completed_jobs": 8,
  "running_jobs": 1,
  "failed_jobs": 1,
  "success_rate": 80.0,
  "system_health": {
    "cpu_usage": 45,
    "memory_usage": 62,
    "database_connections": 5,
    "api_response_time_ms": 150
  },
  "weekly_activity": [...]
}
```

---

### Scenario 5: Timeline Analytics with Date Range

```bash
# Daily granularity
curl "http://localhost:8000/api/analytics/timeline?granularity=daily&start_date=2026-05-06&end_date=2026-05-12" \
  -H "Authorization: Bearer test-token"

# Hourly granularity
curl "http://localhost:8000/api/analytics/timeline?granularity=hourly" \
  -H "Authorization: Bearer test-token"
```

✅ Expected Response:

```json
{
  "data": [
    {
      "timestamp": "2026-05-12",
      "jobs_completed": 12,
      "products_extracted": 3600,
      "jobs_count": 15
    }
  ],
  "granularity": "daily"
}
```

---

### Scenario 6: WebSocket Real-Time Progress

**Python WebSocket Client:**

```python
import asyncio
import websockets
import json

async def monitor_progress(job_id):
    uri = f"ws://localhost:8000/api/ws/progress/{job_id}"
    print(f"Connecting to WebSocket: {uri}")

    try:
        async with websockets.connect(uri) as websocket:
            print("✅ Connected to progress stream\n")

            # Send ping to keep alive
            await websocket.send("ping")

            # Listen for updates
            while True:
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=30)
                    update = json.loads(message)

                    print(f"📊 Step {update['step']}/5")
                    print(f"   Stage: {update['stage']}")
                    print(f"   Message: {update['message']}")
                    print(f"   Progress: {update['progress']}%")
                    print(f"   Products: {update['products_found']}")
                    print(f"   Time: {update['timestamp']}\n")

                except asyncio.TimeoutError:
                    print("⏱️ Timeout - sending ping")
                    await websocket.send("ping")

    except Exception as e:
        print(f"❌ Error: {e}")

# Get job_id from a scraping job
job_id = "your-job-id-here"
asyncio.run(monitor_progress(job_id))
```

**JavaScript WebSocket Client:**

```javascript
function monitorProgress(jobId) {
  const ws = new WebSocket(`ws://localhost:8000/api/ws/progress/${jobId}`);

  ws.onopen = () => {
    console.log("✅ Connected to progress stream");
    ws.send("ping");
  };

  ws.onmessage = (event) => {
    const update = JSON.parse(event.data);
    console.log(`📊 Step ${update.step}/5`);
    console.log(`   Stage: ${update.stage}`);
    console.log(`   Message: ${update.message}`);
    console.log(`   Progress: ${update.progress}%`);
    console.log(`   Products: ${update.products_found}\n`);

    // Update UI
    updateProgressBar(update.progress);
    updateStatusMessage(update.message);
    updateProductCounter(update.products_found);
  };

  ws.onerror = (error) => console.error("❌ WebSocket error:", error);
  ws.onclose = () => console.log("❌ Connection closed");
}

// Usage
monitorProgress("your-job-id-here");
```

---

### Scenario 7: Job Control (Pause/Resume/Stop)

**Pause Job:**

```bash
curl -X POST http://localhost:8000/api/jobs/{job_id}/pause \
  -H "Authorization: Bearer test-token"
```

**Resume Job:**

```bash
curl -X POST http://localhost:8000/api/jobs/{job_id}/resume \
  -H "Authorization: Bearer test-token"
```

**Stop Job:**

```bash
curl -X POST http://localhost:8000/api/jobs/{job_id}/stop \
  -H "Authorization: Bearer test-token"
```

**Retry Job:**

```bash
curl -X POST http://localhost:8000/api/jobs/{job_id}/retry \
  -H "Authorization: Bearer test-token"
```

---

### Scenario 8: System Health Details

```bash
curl http://localhost:8000/api/health/detailed \
  -H "Authorization: Bearer test-token"
```

✅ Expected Response:

```json
{
  "status": "healthy",
  "timestamp": "2026-05-12T10:35:00Z",
  "version": "2.0.0",
  "components": {
    "api": { "status": "ok", "response_time_ms": 45 },
    "database": { "status": "ok", "connections": 5 },
    "cache": { "status": "ok", "memory_usage_mb": 150 },
    "scraper": { "status": "ok", "active_jobs": 3 }
  },
  "queue_status": {
    "active_jobs": 3,
    "queued_jobs": 2,
    "completed_jobs": 148,
    "failed_jobs": 2
  }
}
```

---

## 🎛️ Slider Validation Tests

### Test Min/Max Constraints:

```bash
# Test max_products slider (1-100)
curl -X POST http://localhost:8000/api/scrape \
  -H "Authorization: Bearer test-token" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.amazon.in/gp/bestsellers/",
    "options": {"max_products": 150}  # Will fail - max is 100
  }'
```

✅ Expected: Validation error

```bash
# Test timeout_seconds slider (10-120)
curl -X POST http://localhost:8000/api/scrape \
  -H "Authorization: Bearer test-token" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.amazon.in/gp/bestsellers/",
    "options": {"timeout_seconds": 5}  # Will fail - min is 10
  }'
```

✅ Expected: Validation error

---

## 🐛 Debugging

### Enable Verbose Logging:

```bash
python -m uvicorn backend.app.main:app --log-level debug
```

### Check WebSocket Connection:

```bash
# In browser console
const ws = new WebSocket('ws://localhost:8000/api/ws/progress/test-job');
ws.onopen = () => console.log('Connected');
ws.onerror = (e) => console.error(e);
```

### View Swagger Documentation:

Open: http://localhost:8000/docs

All endpoints are fully documented with:

- Request/response examples
- Parameter descriptions
- Schema definitions

---

## ✅ Validation Checklist

- [ ] Backend starts without errors
- [ ] Health endpoint returns OK
- [ ] Swagger docs load at /docs
- [ ] Can create scraping job
- [ ] Job details endpoint returns metrics
- [ ] Dashboard summary works
- [ ] Timeline analytics with filters works
- [ ] WebSocket connects and receives updates
- [ ] Job control endpoints work (pause/resume/stop)
- [ ] Slider validation works
- [ ] System health endpoint returns data

---

## 📞 Common Issues & Solutions

**Issue: WebSocket connection refused**

- Solution: Make sure backend is running and has WebSocket support enabled

**Issue: Authorization Bearer errors**

- Solution: Backend has auth support - use a test token or disable auth for testing

**Issue: Slider validation errors**

- Solution: Check parameter ranges - they have min/max constraints

**Issue: Progress not updating**

- Solution: Verify job is running and WebSocket is connected

---

## 🎯 Next: Frontend Integration

See `FRONTEND_INTEGRATION_GUIDE.md` for connecting these APIs to your Next.js dashboard!
