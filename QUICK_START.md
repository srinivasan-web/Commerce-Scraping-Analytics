# ⚡ QUICK START - 5 MINUTE SETUP

## What to do RIGHT NOW

### Option 1: One-Click Solution (Easiest)

1. **Open**: `g:\amazon_bestseller_scraper`
2. **Find**: `COMPLETE_SETUP_AND_START.bat`
3. **Double-click**: It
4. **Choose**: Option 1 (Start Both)
5. **Wait**: 10-15 minutes for downloads
6. **Access**:
   - Backend: http://localhost:8000
   - Frontend: http://localhost:3000

### Option 2: Two-Step Solution

**Terminal 1 - Backend:**

```
Open: g:\amazon_bestseller_scraper
Double-click: START_BACKEND.bat
Wait for: "Uvicorn running on http://0.0.0.0:8000"
Keep open!
```

**Terminal 2 - Frontend:** (After backend starts)

```
Open: g:\amazon_bestseller_scraper
Double-click: START_FRONTEND.bat
Wait for: "ready started server on"
Keep open!
```

### Option 3: Manual PowerShell

**PowerShell Terminal 1:**

```powershell
cd g:\amazon_bestseller_scraper
.\venv\Scripts\Activate.ps1
python -m playwright install chromium
python -m uvicorn backend.app.main:app --port 8000 --reload
```

**PowerShell Terminal 2** (after backend starts):

```powershell
cd g:\amazon_bestseller_scraper\frontend
npm install --legacy-peer-deps
npm run dev
```

---

## What Gets Installed

| Component       | What               | Size  | Time  |
| --------------- | ------------------ | ----- | ----- |
| Python packages | Backend framework  | 50MB  | 1 min |
| Playwright      | Browser automation | 400MB | 5 min |
| Node packages   | Frontend framework | 300MB | 3 min |
| Chromium        | Browser executable | 200MB | 5 min |

**Total**: ~950MB, 10-15 minutes

---

## Verify It's Working

### Backend Health

```
curl http://localhost:8000/health
```

Should return:

```json
{"status":"ok","version":"2.0.0",...}
```

### Frontend

Open: http://localhost:3000

Should show scraper web interface

### Test Scraping

1. Paste: `https://www.amazon.in/gp/bestsellers/sports/...`
2. Click: "Start Scraping"
3. See: Products extracted in real-time

---

## Issues?

| Issue               | Fix                                            |
| ------------------- | ---------------------------------------------- |
| "Python not found"  | Install from python.org, add to PATH           |
| "Node not found"    | Install Node.js 18+ from nodejs.org            |
| "Playwright failed" | Rerun: `python -m playwright install chromium` |
| "Port 8000 in use"  | Stop other process or use `--port 8001`        |
| "npm install fails" | Run: `npm install --force`                     |

---

## Files You Need

- **COMPLETE_SETUP_AND_START.bat** ← Start here!
- **PERMANENT_SOLUTION.md** ← Detailed guide
- **START_BACKEND.bat** ← Backend only
- **START_FRONTEND.bat** ← Frontend only

---

## Access Points Once Running

| Service      | URL                          |
| ------------ | ---------------------------- |
| Scraper App  | http://localhost:3000        |
| Backend API  | http://localhost:8000        |
| API Docs     | http://localhost:8000/docs   |
| Health Check | http://localhost:8000/health |

---

## Logs Location

| Component | Log File           |
| --------- | ------------------ |
| Scraping  | `logs/scraper.log` |
| Backend   | Terminal window    |
| Frontend  | Terminal window    |

---

**🚀 You're ready! Execute one of the options above.**

For detailed troubleshooting, see: `PERMANENT_SOLUTION.md`
