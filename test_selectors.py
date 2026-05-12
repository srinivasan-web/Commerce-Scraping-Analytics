"""
Diagnostic script to find correct selectors for Amazon bestsellers page
"""
import time
from fake_useragent import UserAgent
from playwright.sync_api import sync_playwright

BASE_URL = "https://www.amazon.in/gp/bestsellers/sports/3403930031/ref=zg_bs_nav_sports_2_206211218031"

def test_selectors():
    ua = UserAgent()
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=100)
        context = browser.new_context(
            user_agent=ua.random,
            viewport={"width": 1400, "height": 900}
        )
        page = context.new_page()
        
        print("Opening URL...")
        page.goto(BASE_URL, timeout=60000)
        
        time.sleep(3)
        
        # Scroll to load content
        for i in range(5):
            page.mouse.wheel(0, 3000)
            time.sleep(1)
        
        # Try to find product containers
        selectors_to_test = [
            "div.p13n-sc-uncoverable-faceout",
            "div[data-component-type='s-search-result']",
            "div.s-result-item",
            "div[data-asin]",
            "li[data-asin]",
            "div.zg-grid-general-faceout",
            "div[class*='faceout']"
        ]
        
        print("\n=== Testing Product Container Selectors ===")
        for selector in selectors_to_test:
            count = page.locator(selector).count()
            print(f"{selector}: {count} items found")
        
        # Get the actual product container
        print("\n=== Page Content Analysis ===")
        print(f"Page Title: {page.title()}")
        
        # Try to get products with different approaches
        print("\nTrying to extract products...")
        
        # Get all divs with specific attributes
        products = page.locator("div[data-component-type='s-search-result']")
        product_count = products.count()
        print(f"Found {product_count} products with s-search-result selector")
        
        if product_count > 0:
            print("\nFirst product HTML:")
            first_product_html = products.first.inner_html()
            print(first_product_html[:500])  # Print first 500 chars
        
        # Alternative: Get all links
        links = page.locator("a[href*='/dp/']")
        print(f"\nFound {links.count()} product links")
        
        # Get page HTML to inspect structure
        print("\n=== Checking Category Name ===")
        category_selectors = [
            "#zg_banner_text",
            "h1",
            "span[data-feature-name='title']",
            "div.a-section.a-spacing-none"
        ]
        
        for selector in category_selectors:
            try:
                text = page.locator(selector).first.inner_text()
                if text:
                    print(f"{selector}: {text[:100]}")
            except:
                pass
        
        browser.close()

if __name__ == "__main__":
    test_selectors()
