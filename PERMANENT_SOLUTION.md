# 🔧 PERMANENT SOLUTION - Backend & Scraping Issues

## Overview

This guide provides **three ways** to fix and start the backend:

1. **Automated (Easiest)** - Click a .bat file
2. **Semi-Automated** - Run commands one by one
3. **Manual** - Step-by-step troubleshooting

---

# METHOD 1: AUTOMATED (RECOMMENDED)

## One-Click Solution

1. **Open File Explorer**: `g:\amazon_bestseller_scraper`

2. **Double-click**: `COMPLETE_SETUP_AND_START.bat`

3. **The script will**:
   - ✅ Check Python installation
   - ✅ Create virtual environment
   - ✅ Install all dependencies
   - ✅ Install Playwright browsers
   - ✅ Check Node.js
   - ✅ Install npm packages
   - ✅ Ask how to start (Backend, Frontend, or Both)

4. **Choose option 1** to start both servers

5. **Wait for servers to start**, then:
   - Backend: http://localhost:8000
   - Frontend: http://localhost:3000

---

# METHOD 2: INDIVIDUAL SCRIPTS

## Start Only Backend

1. Open File Explorer: `g:\amazon_bestseller_scraper`

2. **Double-click**: `START_BACKEND.bat`

3. **Wait for**:

   ```
   INFO:     Uvicorn running on http://0.0.0.0:8000
   ```

4. **Keep this window open**

## Start Only Frontend

1. Open File Explorer: `g:\amazon_bestseller_scraper\frontend`

2. **Double-click**: `START_FRONTEND.bat`

3. **Wait for**:

   ```
   > ready started server on 0.0.0.0:3000
   ```

4. **Keep this window open**

---

# METHOD 3: MANUAL COMMANDS

## If scripts don't work, use these commands:

### Open PowerShell and navigate to project:

```powershell
cd g:\amazon_bestseller_scraper
```

### Setup Backend (One-time only):

```powershell
# Activate venv
.\venv\Scripts\Activate.ps1

# Upgrade pip
python -m pip install --upgrade pip

# Install dependencies
pip install -r backend/requirements.txt

# Install Playwright browsers (5-10 minutes)
python -m playwright install chromium

# Verify
python -m playwright --version
```

### Start Backend:

```powershell
# Activate venv
.\venv\Scripts\Activate.ps1

# Start server
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Setup Frontend (One-time only):

```powershell
# Navigate to frontend
cd frontend

# Install dependencies
npm install --legacy-peer-deps

# Create env file
@"
NEXT_PUBLIC_API_URL=http://localhost:8000
"@ | Out-File -Encoding UTF8 .env.local
```

### Start Frontend:

```powershell
cd frontend
npm run dev
```

---

# VERIFICATION CHECKLIST

After starting both servers, verify:

## ✅ Backend Health

```bash
curl http://localhost:8000/health
```

**Expected response:**

```json
{
  "status": "ok",
  "version": "2.0.0",
  "features": ["async-scraping", "job-queue", "performance-monitoring"]
}
```

## ✅ API Documentation

Open: http://localhost:8000/docs

Should show interactive Swagger UI with all endpoints

## ✅ Frontend Running

Open: http://localhost:3000

Should show the scraper web interface

## ✅ Test Scraping

1. Paste URL: `https://www.amazon.in/gp/bestsellers/sports/3404686031/...`
2. Click "Start Scraping"
3. Watch logs in backend terminal
4. Should complete with products extracted

---

# TROUBLESHOOTING

## Issue: "Python not found"

**Solution:**

```powershell
# Verify Python is installed
python --version

# If not, install from: https://www.python.org/downloads/
# Make sure to check "Add Python to PATH"
```

## Issue: "venv activation failed"

**Solution:**

```powershell
# Recreate venv
rmdir -r venv
python -m venv venv
.\venv\Scripts\Activate.ps1
```

## Issue: "Playwright install failed"

**Solution:**

```powershell
# Activate venv first
.\venv\Scripts\Activate.ps1

# Try installing with dependencies
python -m playwright install chromium --with-deps

# If still fails, try:
pip install --upgrade playwright
python -m playwright install
```

## Issue: "Port 8000 already in use"

**Solution:**

```powershell
# Find process using port 8000
Get-NetTCPConnection -LocalPort 8000

# Kill process
Stop-Process -Id <PID> -Force

# Or use different port
python -m uvicorn backend.app.main:app --port 8001
```

## Issue: "Node not found"

**Solution:**

```powershell
# Install Node.js from: https://nodejs.org/
# Download LTS version

# Verify after installation
node --version
npm --version
```

## Issue: "npm install fails"

**Solution:**

```powershell
cd frontend

# Clear cache
npm cache clean --force

# Try again
npm install --legacy-peer-deps

# If still fails
npm install --force
```

## Issue: "NotImplementedError in backend"

**This is fixed!** The code has been updated.

**If you still see it:**

```powershell
# Verify you have the latest code
# Delete and re-download: backend/app/services/async_scraper.py

# Check Python syntax
python -m py_compile backend/app/services/async_scraper.py

# Restart backend
```

## Issue: "No products extracted"

**Check in order:**

1. ✅ Backend logs show errors? (Check terminal)
2. ✅ Browser installed? (`python -m playwright --version`)
3. ✅ CAPTCHA detected? (Check backend logs)
4. ✅ Try different Amazon URL
5. ✅ Wait 5 minutes and retry

---

# EXPECTED PERFORMANCE

| Action                    | Time      |
| ------------------------- | --------- |
| Python setup (first time) | 2-3 min   |
| Playwright install        | 5-10 min  |
| Node setup (first time)   | 2-3 min   |
| Backend startup           | 5-10 sec  |
| Frontend startup          | 10-20 sec |
| First scrape              | 60-90 sec |
| Second scrape             | 40-60 sec |

---

# QUICK REFERENCE

## Files Created for Easy Startup

1. **COMPLETE_SETUP_AND_START.bat** - Setup + Start everything (Recommended)
2. **START_BACKEND.bat** - Setup + Start backend only
3. **START_FRONTEND.bat** - Setup + Start frontend only

## One-Time Setup

```
COMPLETE_SETUP_AND_START.bat → Choose option 1
```

## Subsequent Starts

```
Terminal 1: START_BACKEND.bat
Terminal 2 (after 5 sec): START_FRONTEND.bat
```

## Access Points

- **Frontend**: http://localhost:3000
- **Backend**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

---

# COMMON WORKFLOWS

## Fresh Setup

```
1. Run: COMPLETE_SETUP_AND_START.bat
2. Choose: Option 1
3. Wait for both servers
4. Open: http://localhost:3000
```

## Daily Startup

```
1. Open Terminal 1: START_BACKEND.bat
2. Wait 5 seconds
3. Open Terminal 2: START_FRONTEND.bat
4. Use: http://localhost:3000
```

## Manual Startup (If scripts fail)

```
Terminal 1:
  cd g:\amazon_bestseller_scraper
  .\venv\Scripts\Activate.ps1
  python -m uvicorn backend.app.main:app

Terminal 2:
  cd g:\amazon_bestseller_scraper\frontend
  npm run dev
```

---

# PERMANENT FIXES APPLIED

## Code Changes

1. **async_scraper.py** - Fixed BrowserPool class
2. **Improved error handling** - Better exception messages
3. **Added context pooling** - Reuse browser contexts
4. **Proper cleanup** - Stop Playwright on shutdown

## Installation Requirements

1. **Python 3.10+** - For backend
2. **Node.js 18+** - For frontend
3. **Playwright browsers** - Chromium executable
4. **10 GB free space** - For all dependencies

## What Gets Installed

- **Backend**: fastapi, uvicorn, playwright, pandas, openpyxl, pydantic
- **Frontend**: next, react, tailwindcss
- **Browsers**: Chromium (~400MB)

---

# NEXT STEPS

**Choose one method above and execute:**

1. ✅ **Easiest**: Double-click `COMPLETE_SETUP_AND_START.bat`
2. ⚙️ **Manual**: Run `START_BACKEND.bat` then `START_FRONTEND.bat`
3. 🔧 **Advanced**: Follow METHOD 3 commands

---

**This should permanently solve your backend and scraping issues!** 🚀

If any step fails, check TROUBLESHOOTING section above.
