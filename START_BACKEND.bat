@echo off
REM ============================================================================
REM PERMANENT BACKEND & SCRAPING FIX - Complete Automation Script
REM ============================================================================
REM This script will:
REM 1. Activate virtual environment
REM 2. Install all dependencies
REM 3. Install Playwright browsers
REM 4. Verify installation
REM 5. Start backend server
REM ============================================================================

setlocal enabledelayedexpansion
cd /d g:\amazon_bestseller_scraper

echo.
echo ============================================================================
echo 🚀 PERMANENT BACKEND & SCRAPING FIX
echo ============================================================================
echo.

REM Check if Python is installed
echo [STEP 1] Checking Python installation...
python --version >nul 2>&1
if !errorlevel! neq 0 (
    echo ❌ Python not found. Please install Python 3.10+ from python.org
    pause
    exit /b 1
)
python --version
echo ✅ Python found
echo.

REM Check if venv exists
echo [STEP 2] Checking virtual environment...
if not exist "venv\Scripts\activate.bat" (
    echo ⚠️  Virtual environment not found. Creating new one...
    python -m venv venv
    if !errorlevel! neq 0 (
        echo ❌ Failed to create venv
        pause
        exit /b 1
    )
)
echo ✅ Virtual environment ready
echo.

REM Activate venv
echo [STEP 3] Activating virtual environment...
call venv\Scripts\activate.bat
if !errorlevel! neq 0 (
    echo ❌ Failed to activate venv
    pause
    exit /b 1
)
echo ✅ Virtual environment activated
echo.

REM Upgrade pip
echo [STEP 4] Upgrading pip...
python -m pip install --upgrade pip setuptools wheel --quiet
if !errorlevel! neq 0 (
    echo ⚠️  Pip upgrade had issues, continuing anyway...
)
echo ✅ Pip upgraded
echo.

REM Install backend requirements
echo [STEP 5] Installing Python dependencies...
echo Installing: fastapi, uvicorn, playwright, pandas, openpyxl, pydantic, python-multipart...
pip install -r backend/requirements.txt --quiet
if !errorlevel! neq 0 (
    echo ❌ Failed to install requirements
    pause
    exit /b 1
)
echo ✅ All Python packages installed
echo.

REM Install Playwright browsers
echo [STEP 6] Installing Playwright browsers (this may take 3-5 minutes)...
echo Downloading Chromium browser...
python -m playwright install chromium --with-deps
if !errorlevel! neq 0 (
    echo ❌ Failed to install Playwright browsers
    echo Retrying with simpler command...
    python -m playwright install chromium
    if !errorlevel! neq 0 (
        echo ❌ Playwright installation failed
        pause
        exit /b 1
    )
)
echo ✅ Playwright browsers installed
echo.

REM Verify Playwright
echo [STEP 7] Verifying Playwright installation...
python -m playwright --version
if !errorlevel! neq 0 (
    echo ❌ Playwright verification failed
    pause
    exit /b 1
)
echo ✅ Playwright verified
echo.

REM Check browser executable
echo [STEP 8] Checking browser executable...
if exist "%APPDATA%\Local\ms-playwright\chromium-*\chrome-win64\chrome.exe" (
    echo ✅ Chromium browser executable found
) else (
    echo ⚠️  Browser executable not found, will download on first run
)
echo.

REM Test Python imports
echo [STEP 9] Testing Python imports...
python -c "from backend.app.main import app; print('✅ Backend imports successful')"
if !errorlevel! neq 0 (
    echo ❌ Backend import failed
    pause
    exit /b 1
)
echo.

REM Test Playwright import
python -c "from playwright.async_api import async_playwright; print('✅ Playwright imports successful')"
if !errorlevel! neq 0 (
    echo ❌ Playwright import failed
    pause
    exit /b 1
)
echo.

REM All checks passed
echo ============================================================================
echo ✅ ALL CHECKS PASSED - STARTING BACKEND SERVER
echo ============================================================================
echo.
echo Backend will start in a few seconds...
echo Access at: http://localhost:8000
echo Health check: http://localhost:8000/health
echo API docs: http://localhost:8000/docs
echo.
echo Frontend will be at: http://localhost:3000
echo.
timeout /t 3

REM Start backend server
echo [STEP 10] Starting FastAPI backend server...
echo.
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
