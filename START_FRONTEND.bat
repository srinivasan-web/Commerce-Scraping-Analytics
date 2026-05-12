@echo off
REM ============================================================================
REM START FRONTEND - Next.js React Application
REM ============================================================================

setlocal enabledelayedexpansion
cd /d g:\amazon_bestseller_scraper\frontend

echo.
echo ============================================================================
echo 🚀 STARTING FRONTEND SERVER
echo ============================================================================
echo.

REM Check if Node.js is installed
echo [STEP 1] Checking Node.js installation...
node --version >nul 2>&1
if !errorlevel! neq 0 (
    echo ❌ Node.js not found. Please install from nodejs.org
    pause
    exit /b 1
)
node --version
echo ✅ Node.js found
echo.

REM Check if npm is installed
echo [STEP 2] Checking npm installation...
npm --version >nul 2>&1
if !errorlevel! neq 0 (
    echo ❌ npm not found
    pause
    exit /b 1
)
npm --version
echo ✅ npm found
echo.

REM Check if node_modules exists
echo [STEP 3] Checking dependencies...
if not exist "node_modules" (
    echo ⚠️  Dependencies not installed. Installing...
    echo Installing npm packages (this may take 2-3 minutes)...
    npm install --legacy-peer-deps
    if !errorlevel! neq 0 (
        echo ❌ Failed to install dependencies
        pause
        exit /b 1
    )
)
echo ✅ Dependencies ready
echo.

REM Create env file if doesn't exist
echo [STEP 4] Checking environment variables...
if not exist ".env.local" (
    echo Creating .env.local with API URL...
    (
        echo NEXT_PUBLIC_API_URL=http://localhost:8000
    ) > .env.local
    echo ✅ .env.local created
) else (
    echo ✅ .env.local already exists
)
echo.

REM Start development server
echo ============================================================================
echo ✅ ALL CHECKS PASSED - STARTING FRONTEND SERVER
echo ============================================================================
echo.
echo Frontend will start in a few seconds...
echo Access at: http://localhost:3000
echo.
echo Make sure backend is running at: http://localhost:8000
echo.
timeout /t 2

echo [STEP 5] Starting Next.js development server...
echo.
npm run dev
