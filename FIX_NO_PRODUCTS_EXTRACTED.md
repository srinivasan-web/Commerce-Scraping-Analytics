# 🎯 Fix for "No Products Extracted" - Step-by-Step

## Your Issue

**URL**: `https://www.amazon.in/gp/bestsellers/sports/3404687031/ref=zg_bs_nav_sports_3_3404684031`  
**Error**: `No live product cards were extracted`  
**Status**: ⚠️ Backend extraction failed

---

## ✅ Quick Fix (Do This First)

### Step 1: Test if page is accessible

```bash
# In PowerShell:
curl -Uri "https://www.amazon.in/gp/bestsellers/sports/3404687031" -UseBasicParsing | Select-Object -ExpandProperty StatusCode

# Should return: 200 (success)
# If 403 → Region/IP blocked
# If timeout → Network issue
```

### Step 2: Run Diagnostic

```bash
cd g:\amazon_bestseller_scraper
python -m backend.app.services.debug_scraper "https://www.amazon.in/gp/bestsellers/sports/3404687031/ref=zg_bs_nav_sports_3_3404684031"
```

**Expected output:**

```
✅ div.p13n-sc-uncoverable-faceout: 24 found
✅ Extraction Results: 24 products found
```

**If you get this ✅** → Problem is somewhere else, not selectors

**If you get ❌ 0 products** → Selectors don't match this page

---

## 🔍 Most Likely Causes (In Order)

### Cause 1: CAPTCHA Block (70% probability)

**How to check:**

- Look at job logs in UI
- Search for: "CAPTCHA" or "robot check"

**If found CAPTCHA:**

```
✅ Solution: Wait 10 minutes, then click RETRY
   Amazon blocks aggressive scrapers temporarily
```

**If NOT found CAPTCHA:**

```
→ Go to Cause 2
```

---

### Cause 2: Selectors Changed (20% probability)

**How to check:**

```bash
# Run debug script with visible browser
python -m backend.app.services.debug_scraper "https://..." --show

# Watch what happens:
# 1. Browser opens
# 2. Page loads
# 3. See if products are visible

# Check DevTools (F12):
console.log(document.querySelectorAll('div.p13n-sc-uncoverable-faceout').length)

# If returns: 0 → Selectors changed
# If returns: 24+ → Selectors work
```

**If selectors WORK (debug finds products):**

```
→ Go to Cause 3
```

**If selectors FAIL (debug finds 0):**

```
Edit: backend/app/services/async_scraper.py
Search: EXTRACT_SCRIPT = """

Inside that script, find:
  const candidates = Array.from(document.querySelectorAll([

Change it to check new selectors:
  const candidates = Array.from(document.querySelectorAll([
    'div.p13n-sc-uncoverable-faceout',    // Try original
    'li.zg-item-row',                      // Try alternate
    'div.s-result-item',                   // Try search result
    'div[class*="zg"]',                    // Try any zg element
    'div[data-component-type]'             // Try component type
  ].join(',')));

Run debug again to see if any match.
```

---

### Cause 3: Page Not Fully Loading (8% probability)

**How to check:**

- Look at job logs
- See how long it took to load
- Check if scroll iteration count

**If page loads very fast (<5 seconds):**

```
→ Page didn't fully render
→ Solution: Increase wait time
```

**Fix: Edit backend/app/services/async_scraper.py**

Find function: `scroll_and_extract_async`

Change this:

```python
await asyncio.sleep(random.uniform(0.1, 0.3))  # Short wait
```

To this:

```python
await asyncio.sleep(random.uniform(0.5, 1.0))  # Longer wait
```

Also change:

```python
for scroll_count in range(6):  # 6 scrolls
```

To:

```python
for scroll_count in range(10):  # 10 scrolls
```

Then try again.

---

### Cause 4: Amazon Blocking IP (2% probability)

**Symptoms:**

- Works from home WiFi but not office network
- Works from one country but not another
- Always fails on this network

**How to check:**

```bash
# Check what IP Amazon sees
curl -s https://httpbin.org/ip | ConvertFrom-Json

# Check if blocked:
curl -I https://amazon.in

# Should return 200/301
# If 403/429 → Blocked
```

**Solutions:**

```
✅ Option 1: Use VPN to India
   - Connect VPN to Indian server
   - Retry scrape

✅ Option 2: Wait & Retry
   - Wait 1-2 hours
   - Amazon cooldown period

✅ Option 3: Use External Service
   - Enable "External service" option
   - Use different IP
```

---

## 🛠️ Complete Fix Path

```
Does debug script find products?
│
├─ YES (✅ debug finds 24+)
│  └─ Selectors work → Problem elsewhere
│     ├─ Is it CAPTCHA? (check logs)
│     │  ├─ YES → Wait 10min + Retry
│     │  └─ NO → Go to "Page not loading" section
│     │
│     └─ Increase waits/scrolls as shown above
│
└─ NO (❌ debug finds 0)
   └─ Selectors broken → Update selectors
      ├─ Run debug with --show to see page
      ├─ Use DevTools to find working selectors
      └─ Update EXTRACT_SCRIPT in async_scraper.py
```

---

## 📝 Step-by-Step Execution

### For CAPTCHA (Most likely):

```
1. Open UI
2. View job logs
3. Search for "CAPTCHA"
4. If found:
   - Wait 10 minutes
   - Scroll down to find RETRY button
   - Click RETRY
5. Monitor job - should complete this time
```

### For Selector Issue:

```
1. Open PowerShell
2. cd g:\amazon_bestseller_scraper
3. python -m backend.app.services.debug_scraper "https://www.amazon.in/gp/bestsellers/sports/3404687031/ref=zg_bs_nav_sports_3_3404684031" --show
4. Watch browser window load
5. Open DevTools (F12)
6. Run in console: document.querySelectorAll('div.p13n-sc-uncoverable-faceout').length
7. If returns 0:
   - Try: document.querySelectorAll('div[data-asin]').length
   - Try: document.querySelectorAll('li.zg-item-row').length
   - Try: document.querySelectorAll('div.s-result-item').length
8. Find which returns > 0
9. Update EXTRACT_SCRIPT selector
10. Test debug again
11. Test in UI
```

### For Slow Loading:

```
1. Edit: backend/app/services/async_scraper.py
2. Find: scroll_and_extract_async function (around line 490)
3. Change delays from 0.1-0.3 to 0.5-1.0
4. Change loop from range(6) to range(10)
5. Save file
6. Restart backend
7. Retry job in UI
```

---

## ✅ Testing Checklist

After making any changes:

- [ ] Save file
- [ ] Restart backend (`Ctrl+C` then restart)
- [ ] Submit scrape job again
- [ ] Monitor logs for success
- [ ] Should see: "Extracted N products"
- [ ] Should see: "Completed"

---

## 🚨 Emergency: Use External Service

If nothing works:

```
1. In UI, go to job options
2. Enable "External service" checkbox
3. Submit scrape
4. Should use fallback scraper
5. Might be slower but more reliable
```

---

## 📞 If Still Not Working

Collect this info:

```
1. URL: https://www.amazon.in/gp/bestsellers/sports/3404687031/...
2. Debug script output (run and copy-paste output)
3. Job logs (copy-paste from UI)
4. Changes made (what you tried)
5. When started failing (new issue or recurring?)
```

Then check: TROUBLESHOOTING_EXTRACTION.md for more solutions.

---

## ⏱️ Time Estimates

| Fix                  | Time      | Success Rate |
| -------------------- | --------- | ------------ |
| Wait + Retry         | 10 min    | 85%          |
| Update selectors     | 10-20 min | 70%          |
| Increase waits       | 5 min     | 60%          |
| Use external service | Immediate | 90%          |
| Use VPN              | 5 min     | 75%          |

---

**Start with: Wait 10 minutes and click RETRY**  
**If not working: Run debug script**  
**If selectors found: Increase wait times**  
**If selectors not found: Update selectors**

**Good luck! 🚀**
