# 🔧 Backend Extraction Troubleshooting Guide

## Problem: "No Products Extracted" Error

When you see:

```
❌ No live product cards were extracted.
```

This means the backend loaded the Amazon page successfully, but couldn't find any product cards.

---

## 🔍 Root Causes & Solutions

### 1. **CAPTCHA or Bot Detection** (Most Common)

**Symptoms:**

- Extraction fails immediately or after first few attempts
- Same error for different URLs
- Works on one machine but not another

**Solutions:**

```
✅ Solution 1: Wait and Retry
   - Wait 5-10 minutes after first failure
   - Amazon temporarily blocks aggressive scraping
   - Click "Retry" button to try again

✅ Solution 2: Use External Service
   - Enable "External service" option
   - Falls back to more resilient external scraper
   - Has better anti-bot evasion

✅ Solution 3: Use Residential Proxy
   - Enable "Proxy" option (if configured)
   - Changes IP address to appear as residential user
   - Helps bypass datacenter IP blocks

✅ Solution 4: Reduce Frequency
   - Wait between scrapes
   - Don't scrape more than 1-2 URLs per minute
   - Avoid scraping during peak hours
```

**Check logs for CAPTCHA indicator:**

```
If logs contain: "Amazon CAPTCHA or robot-check page detected"
  → This confirms CAPTCHA is the issue
  → Use solutions above
```

---

### 2. **Amazon Page Structure Changed**

**Symptoms:**

- Used to work, now doesn't
- Only fails for specific category or URL
- Works for some products, not others

**Solutions:**

```
✅ Solution 1: Run Debug Script (BEST)
   python backend/app/services/debug_scraper.py "{URL}"

   This shows:
   - What selectors are finding products
   - Sample product structure
   - Why extraction might fail

✅ Solution 2: Check Page in Browser
   - Open URL in browser
   - Right-click → Inspect (DevTools)
   - Look for elements with class "p13n-sc-uncoverable-faceout"
   - Or look for [data-asin] attributes

   If you find them:
   → Contact support with screenshot
   → We'll update selectors

   If you don't find them:
   → Amazon changed the page completely
   → Extraction may not be possible

✅ Solution 3: Test with Simple Category
   - Try: https://amazon.in/gp/bestsellers/electronics
   - If this works → issue is category-specific
   - If this fails → broader issue
```

**Update selectors if needed:**
File: `backend/app/services/async_scraper.py`
Look for: `EXTRACT_SCRIPT` (around line 288)

The key selector to check:

```javascript
const candidates = Array.from(
  document.querySelectorAll(
    [
      "div.p13n-sc-uncoverable-faceout", // Main selector
      "li.zg-carousel-general-faceout",
      "div[data-asin]",
      "div.a-cardui",
    ].join(","),
  ),
);
```

If none match → add new selector that matches product divs.

---

### 3. **Page Not Rendering Properly**

**Symptoms:**

- Extraction works sometimes, fails other times
- Browser might need more time to load
- Rich content takes time to render

**Solutions:**

```
✅ Solution 1: Increase Wait Time
   - Edit: backend/app/services/async_scraper.py
   - Find: scroll_and_extract_async()
   - Change delays from 0.1-0.3s to 0.3-0.5s

   Before: await asyncio.sleep(random.uniform(0.1, 0.3))
   After:  await asyncio.sleep(random.uniform(0.3, 0.7))

✅ Solution 2: Add Extra Scroll Iterations
   - Edit: scroll_and_extract_async()
   - Change: for scroll_count in range(6):
   - To:     for scroll_count in range(10):

   More scrolls = more time for content to load

✅ Solution 3: Disable Headless Mode (for debugging)
   - Use debug script with --show flag:
     python backend/app/services/debug_scraper.py URL --show
   - Watch browser window to see if page loads correctly
```

---

### 4. **Regional/IP Restrictions**

**Symptoms:**

- Works from one network, not another
- Works from India, fails from other countries
- Error messages about location or access

**Solutions:**

```
✅ Solution 1: Use VPN
   - Connect VPN to India if outside
   - Amazon blocks non-India IPs sometimes

✅ Solution 2: Check Network
   - Ensure you can access amazon.in in browser
   - Try: curl https://amazon.in -I
   - Should return 200, not 403 or 429

✅ Solution 3: Check if URL is Region-Specific
   - URL like: amazon.in/gp/bestsellers/
   - Should work for India-based requests
   - Try simple category first

✅ Solution 4: Contact Administrator
   - If network blocks Amazon
   - Corporate firewalls sometimes block scrapers
   - Need to whitelist or use proxy
```

---

### 5. **Network or Connection Issues**

**Symptoms:**

- Timeout errors
- Connection refused
- Page loads but extraction hangs

**Solutions:**

```
✅ Solution 1: Check Internet Connection
   - ping google.com
   - Should respond with latency <50ms
   - If not → fix network first

✅ Solution 2: Check if Amazon.in is Accessible
   - curl https://amazon.in
   - Should get HTML response
   - If 404/403 → regional block

✅ Solution 3: Increase Timeout
   - Edit: async_scraper.py
   - Find: await page.goto(url, wait_until="domcontentloaded", timeout=60000)
   - Change: timeout=60000 → timeout=120000 (2 minutes)

✅ Solution 4: Check DNS
   - nslookup amazon.in
   - Should resolve to IP address
   - If not → DNS issue
```

---

## 🧪 Debugging Steps

### Step 1: Run Debug Script

```bash
cd backend
python app/services/debug_scraper.py "https://amazon.in/gp/bestsellers/sports/..."
```

**Output tells you:**

- How many product containers found
- What CSS selectors are matching
- Sample product data
- Whether extraction works

### Step 2: Check Logs

```bash
# In UI, look at job logs
# Or check backend logs:
tail -f backend/logs/*.log
```

**Look for:**

```
✅ "Extracted N products" → extraction worked
✅ "Enriched N product details" → details fetched
❌ "CAPTCHA detected" → Amazon blocked request
❌ "Extraction failed" → script error
❌ "No candidates found" → wrong selectors
```

### Step 3: Visual Inspection

If debug script doesn't help:

```bash
# Run with visible browser
python app/services/debug_scraper.py "https://..." --show

# Watch browser window
# See if page loads
# See what content is visible
```

### Step 4: Check Page Source

```javascript
// Open browser DevTools (F12)
// Console tab
// Run:
console.log(
  document.querySelectorAll("div.p13n-sc-uncoverable-faceout").length,
);

// Should return > 0 if selector works
```

---

## 📋 Checklist When Extraction Fails

- [ ] Page loads successfully (check title in logs)
- [ ] No CAPTCHA message in logs
- [ ] Run debug script to check selectors
- [ ] Verify page isn't blocked by network
- [ ] Test with simple category (electronics)
- [ ] Try with headless=false to see browser
- [ ] Check if Amazon URL is still valid
- [ ] Verify authentication/region settings
- [ ] Wait 10 minutes and retry
- [ ] Use external service as fallback

---

## 🛠️ Common Fixes

### Fix 1: Amazon Changed Selectors

**Time to fix: 2-5 minutes**

1. Run debug script: See what selectors work
2. Update EXTRACT_SCRIPT in async_scraper.py
3. Test again

### Fix 2: CAPTCHA Block

**Time to fix: 5-60 minutes**

1. Wait 10 minutes
2. Retry once
3. If still blocked, use external service or proxy

### Fix 3: Page Not Loading

**Time to fix: 1-5 minutes**

1. Increase timeout in async_scraper.py
2. Add extra scroll iterations
3. Disable headless to debug

### Fix 4: IP Blocked

**Time to fix: 5-15 minutes**

1. Use VPN to India
2. Or use external service with proxy
3. Or wait for IP cooldown

---

## 📊 Success Indicators

You're on the right track when logs show:

```
✅ Loaded page title: "Amazon.in Bestsellers..."
✅ Browser extracted 24 candidate product cards
✅ Scroll 1: Extracted 24 products
✅ Enriched 24 product details in parallel
✅ Processed 24 products
✅ Completed
```

---

## 🆘 When to Contact Support

With information:

1. Full URL that's failing
2. Error message from logs
3. Debug script output
4. Screenshot showing what you see
5. Whether it ever worked

**Share:**

```
URL: https://...
Error: [exact error message]
Debug output: [debug_scraper.py results]
When it started: [date/time]
Affects: [1 URL, category, all URLs?]
```

---

## 🔗 Related Issues & Solutions

### Issue: "No products extracted" but debug shows 50+ products found

**Cause**: Products found but filtered out during processing
**Solution**: Check logs for filtering reason, might be missing required fields

### Issue: "Extraction works but no details"

**Cause**: Product cards found but detail pages fail
**Solution**: Check if detail enrichment is enabled, might timeout

### Issue: Different results on retry

**Cause**: Amazon returns different bestsellers at different times
**Solution**: This is normal, bestsellers change throughout day

### Issue: Works for 10 products, fails for 50

**Cause**: Timeout due to too much scrolling
**Solution**: Increase max_products gradually, or use paging

---

## 🚀 Quick Reference

| Error            | Cause           | Fix                  |
| ---------------- | --------------- | -------------------- |
| CAPTCHA detected | Bot block       | Wait 10min + retry   |
| No candidates    | Wrong selectors | Run debug script     |
| Timeout          | Slow page       | Increase timeout     |
| No link found    | Parsing error   | Check debug output   |
| Permission error | Windows admin   | Run as administrator |

---

**Last Updated**: May 10, 2026  
**Status**: For Backend v2.0 and above
