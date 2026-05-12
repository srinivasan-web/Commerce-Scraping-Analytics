# 🔧 Fix for "NotImplementedError" - Complete Step-by-Step Solution

## Problem Identified

```
04:41:21 Async extraction failed: NotImplementedError: NotImplementedError()
❌ No live product cards were extracted.
```

**Root Cause**: The `BrowserPool.get_page()` method has incomplete error handling or missing implementation that raises `NotImplementedError`.

---

# STEP-BY-STEP FIX

## STEP 1: Stop the Backend Server

If backend is running:

```bash
# Kill the process
taskkill /IM python.exe /F

# Or press Ctrl+C in the terminal
```

**Verify it's stopped:**

```bash
curl http://localhost:8000/health
# Should return: Connection refused
```

---

## STEP 2: Backup Current File

```bash
# Backup the current async_scraper.py
copy g:\amazon_bestseller_scraper\backend\app\services\async_scraper.py ^
     g:\amazon_bestseller_scraper\backend\app\services\async_scraper.py.backup
```

---

## STEP 3: Fix the BrowserPool.get_page() Method

**Problem in the code:** The `get_page()` method needs better error handling.

### Replace the BrowserPool class with fixed version:

Find and replace this section in [async_scraper.py](backend/app/services/async_scraper.py#L36-L120):

**OLD CODE (Lines 36-120):**

```python
class BrowserPool:
    """Manages browser instances and contexts for connection pooling."""

    def __init__(self, max_browsers: int = 3):
        self.max_browsers = max_browsers
        self.browsers: list[Browser] = []
        self.contexts: list[BrowserContext] = []
        self.semaphore = asyncio.Semaphore(max_browsers)
        self.lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self):
        """Initialize the browser pool."""
        if self._initialized:
            return
        self._initialized = True

    async def get_page(self) -> Page:
        """Get a page from the pool with semaphore control."""
        await self.semaphore.acquire()
        async with self.lock:
            if not self.contexts:
                # Create new browser and context
                playwright = await async_playwright().start()
                browser = await playwright.chromium.launch(
                    headless=True,
                    args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-dev-shm-usage"],
                )
                self.browsers.append(browser)
                context = await browser.new_context(
                    viewport={"width": 1440, "height": 1000},
                    user_agent=random.choice([
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                    ]),
                    locale="en-IN",
                    timezone_id="Asia/Kolkata",
                    extra_http_headers={"Accept-Language": "en-IN,en;q=0.9"},
                )
                self.contexts.append(context)

            context = self.contexts.pop() if self.contexts else None
            if not context:
                context = await self.browsers[0].new_context(
                    viewport={"width": 1440, "height": 1000},
                    user_agent=random.choice([
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                    ]),
                    locale="en-IN",
                    timezone_id="Asia/Kolkata",
                    extra_http_headers={"Accept-Language": "en-IN,en;q=0.9"},
                )

        page = await context.new_page()
        return page

    async def return_page(self, page: Page):
        """Return a page to the pool."""
        try:
            await page.close()
        except Exception:
            pass
        finally:
            self.semaphore.release()
```

**REPLACE WITH (Fixed version):**

```python
class BrowserPool:
    """Manages browser instances and contexts for connection pooling."""

    def __init__(self, max_browsers: int = 3):
        self.max_browsers = max_browsers
        self.browsers: list[Browser] = []
        self.contexts: list[BrowserContext] = []
        self.semaphore = asyncio.Semaphore(max_browsers)
        self.lock = asyncio.Lock()
        self._initialized = False
        self._playwright = None

    async def initialize(self):
        """Initialize the browser pool."""
        if self._initialized:
            return
        self._initialized = True
        # Pre-warm one browser instance
        try:
            self._playwright = await async_playwright().start()
        except Exception as e:
            print(f"⚠️  Playwright initialization warning: {e}")

    async def _ensure_playwright(self):
        """Ensure playwright is initialized."""
        if not self._playwright:
            self._playwright = await async_playwright().start()
        return self._playwright

    async def get_page(self) -> Page:
        """Get a page from the pool with semaphore control."""
        if not self._playwright:
            self._playwright = await self._ensure_playwright()

        # Wait for available slot
        await self.semaphore.acquire()

        try:
            async with self.lock:
                context = None

                # Try to reuse existing context
                if self.contexts:
                    context = self.contexts.pop()

                # Create new context if needed
                if not context:
                    if not self.browsers or len(self.browsers) < self.max_browsers:
                        # Create new browser if we have capacity
                        try:
                            browser = await self._playwright.chromium.launch(
                                headless=True,
                                args=[
                                    "--disable-blink-features=AutomationControlled",
                                    "--no-sandbox",
                                    "--disable-dev-shm-usage",
                                    "--disable-gpu",
                                ],
                            )
                            self.browsers.append(browser)
                        except Exception as e:
                            print(f"❌ Browser launch failed: {e}")
                            self.semaphore.release()
                            raise RuntimeError(f"Failed to launch browser: {e}")
                    else:
                        # Use existing browser
                        browser = self.browsers[0]

                    # Create context from browser
                    try:
                        context = await browser.new_context(
                            viewport={"width": 1440, "height": 1000},
                            user_agent=random.choice([
                                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                            ]),
                            locale="en-IN",
                            timezone_id="Asia/Kolkata",
                            extra_http_headers={"Accept-Language": "en-IN,en;q=0.9"},
                        )
                    except Exception as e:
                        print(f"❌ Context creation failed: {e}")
                        self.semaphore.release()
                        raise RuntimeError(f"Failed to create context: {e}")

            # Create page from context
            if not context:
                self.semaphore.release()
                raise RuntimeError("No context available")

            page = await context.new_page()
            page._pool_context = context  # Store context reference
            return page

        except Exception as e:
            self.semaphore.release()
            raise

    async def return_page(self, page: Page):
        """Return a page to the pool."""
        try:
            if hasattr(page, "_pool_context"):
                context = page._pool_context
                try:
                    await page.close()
                except Exception:
                    pass
                # Return context to pool
                if context and len(self.contexts) < self.max_browsers:
                    self.contexts.append(context)
                else:
                    try:
                        await context.close()
                    except Exception:
                        pass
            else:
                await page.close()
        except Exception:
            pass
        finally:
            self.semaphore.release()

    async def cleanup(self):
        """Clean up all browsers and contexts."""
        async with self.lock:
            for context in self.contexts:
                try:
                    await context.close()
                except Exception:
                    pass
            for browser in self.browsers:
                try:
                    await browser.close()
                except Exception:
                    pass

            if self._playwright:
                try:
                    await self._playwright.stop()
                except Exception:
                    pass

            self.browsers.clear()
            self.contexts.clear()
            self._initialized = False
            self._playwright = None
```

---

## STEP 4: Install Playwright Browsers (Critical!)

The error likely occurs because Playwright browser binaries are missing:

```bash
cd g:\amazon_bestseller_scraper

# Activate venv
venv\Scripts\activate

# Install Playwright browsers
python -m playwright install chromium

# Verify installation
python -m playwright --version

# Should show: Version X.X.X
```

**Expected output:**

```
Install pyright 1.1.306 for python 3.X
Downloading Chromium ...
```

Wait for download to complete (~5 minutes).

---

## STEP 5: Install Missing Dependencies

```bash
# Activate venv
venv\Scripts\activate

# Install/upgrade dependencies
pip install --upgrade playwright>=1.40 fastapi uvicorn pandas

# Verify Playwright
pip show playwright
# Should show version >= 1.40
```

---

## STEP 6: Test Backend Import

```bash
# Activate venv
venv\Scripts\activate

# Test Python imports
python -c "from backend.app.services.async_scraper import BrowserPool; print('✅ Import successful')"

# Should print: ✅ Import successful
```

---

## STEP 7: Start Backend Server

```bash
# Activate venv
cd g:\amazon_bestseller_scraper
venv\Scripts\activate

# Start backend
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

**Expected output:**

```
✅ INFO:     Application startup complete
✅ INFO:     Uvicorn running on http://0.0.0.0:8000
```

---

## STEP 8: Test Health Endpoint

**In NEW terminal:**

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

---

## STEP 9: Retry Scraping Job

1. Open frontend: http://localhost:3000
2. Enter URL: `https://www.amazon.in/gp/bestsellers/sports/3404686031/...`
3. Click "Start Scraping"
4. Monitor logs in backend terminal

**Expected logs:**

```
✅ Optimized async scrape started
✅ Scroll 1: Extracted 24 products
✅ Scroll 2: Extracted 28 products
✅ Enriched 28 product details in parallel
✅ Optimized scrape completed successfully
```

---

## STEP 10: Verify Extraction Success

**Check in frontend:**

- Job should show COMPLETED status
- Product count should be 20+
- Products should display with name, price, rating

**Check in backend logs:**

- No "NotImplementedError" messages
- Should show "Completed successfully"

---

# Troubleshooting

## Issue: Still getting NotImplementedError

**Check:**

```bash
# Verify Playwright installed
python -m playwright install chromium

# Check browser executable exists
dir "%APPDATA%\Local\ms-playwright"

# Should show: chromium-XXXX folder
```

## Issue: "Port 8000 already in use"

```bash
# Find and kill process
netstat -ano | findstr :8000

# Kill by PID
taskkill /PID <PID> /F

# Or use different port
python -m uvicorn backend.app.main:app --port 8001
```

## Issue: "BrowserPool initialization failed"

**Solution:**

```bash
# Reinstall Playwright from scratch
pip uninstall playwright -y
pip install playwright>=1.40
python -m playwright install --with-deps
```

---

# Success Criteria

✅ Backend starts without errors  
✅ Health endpoint returns 200  
✅ No NotImplementedError in logs  
✅ Scraping job completes  
✅ Products extracted > 0  
✅ No CAPTCHA messages

---

# Quick Reference

| Command                                 | Purpose             |
| --------------------------------------- | ------------------- |
| `python -m playwright install chromium` | Install browsers    |
| `python -m playwright --version`        | Verify installation |
| `curl http://localhost:8000/health`     | Test backend        |
| `docker-compose logs backend -f`        | View Docker logs    |
| `taskkill /IM python.exe /F`            | Kill backend        |

---

**After completing these steps, the NotImplementedError should be resolved!** 🚀

If still having issues, collect:

1. Full backend error message
2. Playwright version: `python -m playwright --version`
3. Browser location: `dir "%APPDATA%\Local\ms-playwright"`
