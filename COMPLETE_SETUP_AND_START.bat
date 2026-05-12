@echo off
REM ============================================================================
REM COMPLETE SETUP & STARTUP - Backend + Frontend
REM ============================================================================
REM This script automates:
REM 1. Environment setup (venv, dependencies, Playwright)
REM 2. Backend server startup
REM 3. Frontend server startup
REM ============================================================================

setlocal enabledelayedexpansion
cd /d g:\amazon_bestseller_scraper

echo.
echo ============================================================================
echo 🚀 COMPLETE AMAZON SCRAPER SETUP & STARTUP
echo ============================================================================
echo.
echo This will setup and start both Backend (FastAPI) and Frontend (Next.js)
echo.
echo PREREQUISITES:
echo - Python 3.10+ (installed)
echo - Node.js 18+ (installed)
echo - 5-10 GB free disk space
echo - 2 GB free RAM
echo.
echo Press any key to continue...
pause >nul
echo.

REM ============================================================================
REM BACKEND SETUP
REM ============================================================================
echo.
echo ============================================================================
echo [BACKEND SETUP]
echo ============================================================================
echo.

REM Check Python
echo Checking Python...
python --version
if !errorlevel! neq 0 (
    echo ❌ Python not found
    pause
    exit /b 1
)
echo ✅ Python OK
echo.

REM Create venv if needed
if not exist "venv\Scripts\activate.bat" (
    echo Creating virtual environment...
    python -m venv venv
)
echo ✅ venv ready
echo.

REM Activate venv
call venv\Scripts\activate.bat
echo ✅ venv activated
echo.

REM Keep local runs stable on Windows when __pycache__ files are locked.
set PYTHONDONTWRITEBYTECODE=1
set PYTHONUTF8=1

REM Install Python dependencies
echo Installing Python dependencies...
python -m pip install --upgrade pip --quiet 2>nul
pip install -r backend/requirements.txt --quiet
if !errorlevel! neq 0 (
    echo ❌ Failed to install requirements
    echo Trying again without quiet mode...
    pip install -r backend/requirements.txt
    if !errorlevel! neq 0 (
        echo ❌ Installation failed
        pause
        exit /b 1
    )
)
echo ✅ Python dependencies installed
echo.

REM Install Playwright
echo Installing Playwright browsers (this will take 3-5 minutes)...
python -m playwright install chromium
if !errorlevel! neq 0 (
    echo ⚠️  Playwright installation had issues
)
echo ✅ Playwright ready
echo.

echo Backend setup complete!
echo.

REM ============================================================================
REM FRONTEND SETUP
REM ============================================================================
echo.
echo ============================================================================
echo [FRONTEND SETUP]
echo ============================================================================
echo.

cd /d g:\amazon_bestseller_scraper\frontend

REM Check Node
echo Checking Node.js...
node --version
if !errorlevel! neq 0 (
    echo ❌ Node.js not found
    cd /d g:\amazon_bestseller_scraper
    pause
    exit /b 1
)
echo ✅ Node.js OK
echo.

REM Install dependencies if needed
if not exist "node_modules" (
    echo Installing Node.js dependencies (this will take 2-3 minutes)...
    npm install --legacy-peer-deps
    if !errorlevel! neq 0 (
        echo ⚠️  npm install had issues, continuing...
    )
)
echo ✅ Node.js dependencies ready
echo.

REM Create env file
if not exist ".env.local" (
    echo Creating environment variables...
    (
        echo NEXT_PUBLIC_API_URL=http://localhost:8000
    ) > .env.local
)
echo ✅ Environment variables set
echo.

echo Frontend setup complete!
echo.

REM ============================================================================
REM READY TO START
REM ============================================================================
cd /d g:\amazon_bestseller_scraper

echo ============================================================================
echo ✅ SETUP COMPLETE - READY TO START SERVERS
echo ============================================================================
echo.
echo.
echo Choose how to start:
echo.
echo Option 1: START BOTH (Recommended - requires 2 terminal windows)
echo Option 2: START BACKEND ONLY
echo Option 3: START FRONTEND ONLY
echo Option 4: EXIT
echo.
set /p choice="Enter option (1-4): "

if "!choice!"=="1" (
    echo.
    echo Starting backend in new window...
    start "Backend Server" cmd /k "cd /d g:\amazon_bestseller_scraper && call venv\Scripts\activate.bat && python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload"
    
    timeout /t 3
    
    echo Starting frontend in new window...
    start "Frontend Server" cmd /k "cd /d g:\amazon_bestseller_scraper\frontend && npm run dev"
    
    echo.
    echo ✅ Both servers starting in separate windows!
    echo.
    echo Backend: http://localhost:8000
    echo Frontend: http://localhost:3000
    echo API Docs: http://localhost:8000/docs
    echo.
    echo Keep these windows open. Press Ctrl+C to stop servers.
    echo.
    pause
    
) else if "!choice!"=="2" (
    echo.
    echo Starting backend server...
    cd /d g:\amazon_bestseller_scraper
    call venv\Scripts\activate.bat
    python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
    
) else if "!choice!"=="3" (
    echo.
    echo Starting frontend server...
    cd /d g:\amazon_bestseller_scraper\frontend
    npm run dev
    
) else (
    echo Exiting...
    exit /b 0
)
