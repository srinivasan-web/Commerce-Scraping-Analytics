import time
from fake_useragent import UserAgent
from playwright.sync_api import sync_playwright

BASE_URL = "https://www.amazon.in/gp/bestsellers/sports/3403930031/ref=zg_bs_nav_sports_2_206211218031"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page(user_agent=UserAgent().random)
    
    print("Loading page...")
    page.goto(BASE_URL, wait_until="load")
    time.sleep(5)
    
    # Scroll
    for i in range(10):
        page.mouse.wheel(0, 2000)
        time.sleep(0.3)
    
    time.sleep(2)
    
    # Get page content
    print("Getting page HTML...")
    html = page.content()
    
    # Save to file
    with open("page_debug.html", "w", encoding="utf-8") as f:
        f.write(html)
    
    print(f"Saved {len(html)} bytes to page_debug.html")
    
    # Check for various selectors
    print(f"\nPage title: {page.title()}")
    print(f"URL: {page.url}")
    
    print("\n=== Selector Counts ===")
    print(f"a[href*='/dp/']: {len(page.query_selector_all('a[href*=\"/dp/\"]'))}")
    print(f"div[data-asin]: {len(page.query_selector_all('div[data-asin]'))}")
    print(f"div with class containing 'faceout': {len(page.query_selector_all('div[class*=\"faceout\"]'))}")
    print(f"span with rank (#1, #2...): {len(page.query_selector_all('span:has-text(\"#\")'))}")
    
    # Try to get text snippets
    print("\n=== Page Text (first 1000 chars) ===")
    text = page.locator("body").inner_text()
    print(text[:1000])
    
    browser.close()
