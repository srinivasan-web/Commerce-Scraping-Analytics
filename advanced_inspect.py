"""
Advanced diagnostic to find exact selectors
"""
import time
from fake_useragent import UserAgent
from playwright.sync_api import sync_playwright

BASE_URL = "https://www.amazon.in/gp/bestsellers/sports/3403930031/ref=zg_bs_nav_sports_2_206211218031"

def inspect_page():
    ua = UserAgent()
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=100)
        page = browser.new_page()
        
        print("Opening URL...")
        page.goto(BASE_URL, timeout=60000, wait_until="domcontentloaded")
        
        time.sleep(5)
        
        # Scroll
        for i in range(5):
            page.mouse.wheel(0, 3000)
            time.sleep(0.5)
        
        print("\n=== HTML Structure Analysis ===\n")
        
        # Get all elements with data-asin attribute
        asin_elements = page.locator("[data-asin]")
        print(f"Elements with data-asin: {asin_elements.count()}")
        
        # Get all divs with specific data attributes
        divs_with_data = page.locator("div[data-asin]")
        print(f"Divs with data-asin: {divs_with_data.count()}")
        
        # Get all product divs by checking for images in divs
        all_divs_with_img = page.locator("div:has(img)")
        print(f"Divs with images: {all_divs_with_img.count()}")
        
        # Check span elements
        spans = page.locator("span")
        print(f"Total spans: {spans.count()}")
        
        # Look for price-like elements
        prices = page.locator("[data-a-price]")
        print(f"Price elements: {prices.count()}")
        
        # Get a sample of link structure
        print("\n=== Sample Links (first 5) ===")
        links = page.locator("a[href*='/dp/']")
        print(f"Total product links: {links.count()}")
        
        for i in range(min(5, links.count())):
            link = links.nth(i)
            href = link.get_attribute("href")
            text = link.inner_text()[:50]
            print(f"{i+1}. {text}... -> {href[:80]}")
        
        # Check for bestseller badges
        print("\n=== Bestseller Indicators ===")
        badges = page.locator("span:has-text('#')")
        print(f"Badge elements: {badges.count()}")
        
        # Get page structure
        print("\n=== Page Structure ===")
        print(f"H1 text: {page.locator('h1').first.inner_text()}")
        
        # Check for product containers by looking for specific patterns
        print("\n=== Looking for Product Containers ===")
        
        # Option 1: Look for elements containing both image and link
        product_containers = page.evaluate("""
            () => {
                const containers = [];
                const divs = document.querySelectorAll('div[data-asin]');
                divs.forEach((div, idx) => {
                    if (idx < 3) {
                        containers.push({
                            asin: div.getAttribute('data-asin'),
                            html: div.innerHTML.substring(0, 200),
                            classes: div.className
                        });
                    }
                });
                return containers;
            }
        """)
        
        print(f"\nSample div[data-asin] structure:")
        for i, container in enumerate(product_containers):
            print(f"\n{i+1}. ASIN: {container.get('asin')}")
            print(f"   Classes: {container.get('classes')[:100]}")
        
        # Get all h2 elements (usually product titles)
        h2s = page.locator("h2")
        print(f"\n\nTotal H2 elements: {h2s.count()}")
        if h2s.count() > 0:
            print("First 3 H2 texts:")
            for i in range(min(3, h2s.count())):
                print(f"  {h2s.nth(i).inner_text()[:60]}")
        
        browser.close()

if __name__ == "__main__":
    inspect_page()
